#!/usr/bin/env python
"""Extract airspace data from Tim Newport-Peace format file."""

from simpleparse.parser import Parser
from simpleparse.dispatchprocessor import *
from latlon import Latitude, Longitude

# EBNF grammar for TNP airspace format
tnp_decl = r"""
tnp_file        := (exclude_block/include_yes/airspace/airtype/airclass/eol/
                    end)*
airspace        := title,eol*,header,body,(sub_header,body)*
header          := (airclass/airtype/base/tops/active/radio),
                   (airclass/airtype/base/tops/active/radio/eol)*
sub_header      := (base/tops/radio),(base/tops/radio/eol)*
body            := (point/circle),(point/cw_arc/ccw_arc/eol)*
<exclude_block> := include_no,-include_yes*,include_yes

title           := 'TITLE',eq,title_val,eol
airtype         := 'TYPE',eq,airtype_val,eol
airclass        := 'CLASS',eq,airclass_val,eol
active          := 'ACTIVE',eq,active_val,eol
radio           := 'RADIO',eq,radio_val,eol
tops            := 'TOPS',eq,level,eol
base            := 'BASE',eq,level,eol
point           := 'POINT',eq,latitude_val,ts,longitude_val,eol
cw_arc          := 'CLOCKWISE',ts,radius,ts,centre,ts,to,eol
ccw_arc         := 'ANTI-CLOCKWISE',ts,radius,ts,centre,ts,to,eol
circle          := 'CIRCLE',ts,radius,ts,centre,eol
width           := 'WIDTH',eq,width_val
awy             := 'AWY',eq,latitude_val,ts,longitude_val,eol
<end>           := 'END',eol

radius          := 'RADIUS',eq,radius_val
centre          := 'CENTRE',eq,latitude_val,ts,longitude_val
to              := 'TO',eq,latitude_val,ts,longitude_val
level           := fl_val/altitude_val/height_val/unlimited_val

title_val       := ('*',letter)/letter,-('#'/eol)*
airtype_val     := ctr/airways/restricted/prohibited/danger/other/training/
                   info/gsec/matz/tmz/boundary/unknown
airclass_val    := [A-GX]
active_val      := weekday/everyday/notam/weekend/unknown
radio_val       := letter/digit,-('#'/eol)*
radius_val      := (digit+,'.',digit*)/digit+
latitude_val    := ('N'/'S'),digit,digit,digit,digit,digit,digit
longitude_val   := ('W'/'E'),digit,digit,digit,digit,digit,digit,digit
fl_val          := 'FL',digit+
altitude_val    := digit+,'ALT'
height_val      := (digit+,'AGL'/'AAL')/'SFC'
unlimited_val   := 'UNLTD'
width_val       := digit+

ctr             := 'CTA/CTR'/'CTR'/'C'
airways         := 'AIRWAYS'/'A'
restricted      := 'RESTRICTED'/'R'
prohibited      := 'PROHIBITED'/'P'
danger          := 'DANGER'/'D'
other           := 'OTHER'/'O'
training        := 'TRAINING ZONE'/'Z'
info            := 'TRAFFIC INFO'/'I'
gsec            := 'GSEC'/'G'
matz            := 'MATZ'/'M'
tmz             := 'TMZ'/'T'
boundary        := 'BOUNDARY'/'B'
weekday         := 'WEEKDAY'
everyday        := 'EVERYDAY'
notam           := 'NOTAM'
weekend         := 'WEEKEND'
unknown         := 'X'/ts

<eol>           := (ts,comment)/null_line
<include_yes>   := 'INCLUDE',eq,'YES',ts,newline
<include_no>    := 'INCLUDE',eq,'NO',ts,newline
<comment>       := '#',-newline*,newline
<null_line>     := ts,newline
<eq>            := ts,'=',ts
<ts>            := [ \t]*
<digit>         := [0-9]
<letter>        := [A-Za-z]
<newline>       := '\x0a'/'\x0d\x0a'
"""

#------------------------------------------------------------------------------
class Point:
    """Point defined by latititude and longitude."""
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

class Circle:
    """Circle defined by centre and radius."""
    def __init__(self, lat, lon, radius):
        self.centre = Point(lat, lon) 
        self.radius = float(radius)

class Arc:
    """Arc (from a previous point) defined by center, end and radius."""
    def __init__(self, lat, lon, clat, clon, radius):
        self.end = Point(lat, lon)
        self.centre = Point(clat, clon)
        self.radius = float(radius)

class CcwArc(Arc):
    """Counter-clockwise arc."""
    pass

class CwArc(Arc):
    """Clockwise arc."""
    pass

#------------------------------------------------------------------------------
class FlightLevel:
    def __init__(self, fl_str):
        self.level = int(fl_str[2:])

    def __str__(self):
        return "FL%03d" % self.level

    def __int__(self):
        return self.level * 100

class Height:
    def __init__(self, height_str):
        if height_str=="SFC":
            self.height = 0
        else:
            self.height = int(height_str[:-3])

    def __str__(self):
        if self.height==0:
            return "SFC"
        else:
            return "%dAGL" % self.height

    def __int__(self):
        return self.height

class Altitude:
    def __init__(self, altitude):
        self.altitude = int(altitude[:-3])

    def __str__(self):
        return "%dALT" % self.altitude

    def __int__(self):
        return self.altitude

class Unlimited:
    def __str__(self):
        return "FL999"

    def __int__(self):
        return 99999

#-----------------------------------------------------------------------------
class TnpProcessor(DispatchProcessor):
    def __init__(self, output_processor):
        self.output_processor = output_processor

    def _no_dispatch(self, (tag, begin, end, subtags), buffer):
        pass

    def _dispatch_list(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)

    airspace = title = sub_header = airtype = airclass = radius = to =\
        level = _dispatch_list
    active = radio = width = awy = _no_dispatch

    def header(self, (tag, begin, end, subtags), buffer):
        self._base = self._tops = None
        dispatchList(self, subtags, buffer)

    def body(self, (tag, begin, end, subtags), buffer):
        self._airlist = []
        dispatchList(self, subtags, buffer)

        # ROC's airspace file uses "dummy" airspace (with TITLE=X) to define
        # airspace type/class
        if self._title != "X":
            self.output_processor.add_airspace(self._title, self._airclass,
                self._airtype, self._base, self._tops, self._airlist)

    def tops(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._tops = self._level

    def base(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._base = self._level

    def centre(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._clat = self._lat
        self._clon = self._lon

    def point(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._airlist.append(Point(self._lat, self._lon))

    def circle(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._airlist.append(Circle(self._lat, self._lon, self._radius))

    def cw_arc(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._airlist.append(
            CwArc(self._lat, self._lon, self._clat, self._clon, self._radius))

    def ccw_arc(self, (tag, begin, end, subtags), buffer):
        dispatchList(self, subtags, buffer)
        self._airlist.append(
            CcwArc(self._lat, self._lon, self._clat, self._clon, self._radius))

    def title_val(self, (tag, begin, end, subtags), buffer):
        self._title = buffer[begin:end].strip()

    def airtype_val(self, (tag, begin, end, subtags), buffer):
        self._airtype = subtags[0][0]

    def airclass_val(self, (tag, begin, end, subtags), buffer):
        self._airclass = buffer[begin:end]

    def radius_val(self, (tag, begin, end, subtags), buffer):
        self._radius = buffer[begin:end]

    def latitude_val(self, (tag, begin, end, subtags), buffer):
        self._lat = Latitude(buffer[begin:end])

    def longitude_val(self, (tag, begin, end, subtags), buffer):
        self._lon = Longitude(buffer[begin:end])

    def fl_val(self, (tag, begin, end, subtags), buffer):
        self._level = FlightLevel(buffer[begin:end])

    def altitude_val(self, (tag, begin, end, subtags), buffer):
        self._level = Altitude(buffer[begin:end])

    def height_val(self, (tag, begin, end, subtags), buffer):
        self._level = Height(buffer[begin:end])

    def unlimited_val(self, (tag, begin, end, subtags), buffer):
        self._level = FlightLevel('FL999')

class TestProcessor:
    def add_airspace(self, title, airclass, airtype, base, tops, airlist):
        print "%s, %s, %s, %s, %s" % (title, airclass, airtype, base, tops)

if __name__ == '__main__':
    import sys
    tnp_filename = sys.argv[1]

    output_processor = TestProcessor()
    tnp_processor = TnpProcessor(output_processor)

    parser = Parser(tnp_decl, "tnp_file")
    airdata = open(tnp_filename).read()
    (success, parse_result, next_char) = parser.parse(airdata,
                                                      processor=tnp_processor)

    # Report any syntax errors
    if not (success and next_char==len(airdata)):
        print "%s: Syntax error at line %d" % \
            (tnp_filename, len(airdata[:next_char].splitlines())+1)

