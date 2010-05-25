#!/usr/bin/env python
"""Extract airspace data from Tim Newport-Peace format file."""

from simpleparse.dispatchprocessor import DispatchProcessor, dispatchList
from latlon import Latitude, Longitude

# EBNF grammar for TNP airspace format
TNP_DECL = r"""
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
    """Flight level class"""
    def __init__(self, fl_str):
        """Class initialisation"""
        self.level = int(fl_str[2:])

    def __str__(self):
        return "FL%03d" % self.level

    def __int__(self):
        return self.level * 100

class Height:
    """Height class"""
    def __init__(self, height_str):
        """Class initialisation"""
        if height_str == "SFC":
            self.height = 0
        else:
            self.height = int(height_str[:-3])

    def __str__(self):
        if self.height == 0:
            return "SFC"
        else:
            return "%dAGL" % self.height

    def __int__(self):
        return self.height

class Altitude:
    """Altitude class"""
    def __init__(self, altitude):
        self.altitude = int(altitude[:-3])

    def __str__(self):
        return "%dALT" % self.altitude

    def __int__(self):
        return self.altitude

class Unlimited:
    """Unlimited class"""
    def __str__(self):
        return "FL999"

    def __int__(self):
        return 99999

#-----------------------------------------------------------------------------
class TnpProcessor(DispatchProcessor):
    """TNP processor"""
    def __init__(self, output_processor):
        """Class initialisation"""
        self.output_processor = output_processor

    def _no_dispatch(self, (tag, begin, end, subtags), buf):
        """Do nothing"""
        pass

    def _dispatch_list(self, (_tag, _begin, _end, subtags), buf):
        """Dispatch a list"""
        dispatchList(self, subtags, buf)

    airspace = title = sub_header = airtype = airclass = radius = to = \
        level = _dispatch_list
    active = radio = width = awy = _no_dispatch

    def header(self, (_tag, _begin, _end, subtags), buf):
        """Process header"""
        self._base = self._tops = None
        dispatchList(self, subtags, buf)

    def body(self, (_tag, _begin, _end, subtags), buf):
        """Process body"""
        self._airlist = []
        dispatchList(self, subtags, buf)

        # ROC's airspace file uses "dummy" airspace (with TITLE=X) to define
        # airspace type/class
        if self._title != "X":
            self.output_processor.add_airspace(self._title, self._airclass,
                self._airtype, self._base, self._tops, self._airlist)

    def tops(self, (_tag, _begin, _end, subtags), buf):
        """Process TOPS statement"""
        dispatchList(self, subtags, buf)
        self._tops = self._level

    def base(self, (_tag, _begin, _end, subtags), buf):
        """Process BASE statement"""
        dispatchList(self, subtags, buf)
        self._base = self._level

    def centre(self, (_tag, _begin, _end, subtags), buf):
        """Process CENTRE statement"""
        dispatchList(self, subtags, buf)
        self._clat = self._lat
        self._clon = self._lon

    def point(self, (_tag, _begin, _end, subtags), buf):
        """Process POINT statement"""
        dispatchList(self, subtags, buf)
        self._airlist.append(Point(self._lat, self._lon))

    def circle(self, (_tag, _begin, _end, subtags), buf):
        """Process CIRCLE statement"""
        dispatchList(self, subtags, buf)
        self._airlist.append(Circle(self._lat, self._lon, self._radius))

    def cw_arc(self, (_tag, _begin, _end, subtags), buf):
        """Process CW_ARC statement"""
        dispatchList(self, subtags, buf)
        self._airlist.append(
            CwArc(self._lat, self._lon, self._clat, self._clon, self._radius))

    def ccw_arc(self, (_tag, _begin, _end, subtags), buf):
        """Process CCW_ARC statement"""
        dispatchList(self, subtags, buf)
        self._airlist.append(
            CcwArc(self._lat, self._lon, self._clat, self._clon, self._radius))

    def title_val(self, (_tag, begin, end, _subtags), buf):
        """Process TITLE value"""
        self._title = buf[begin:end].strip()

    def airtype_val(self, (_tag, _begin, _end, subtags), _buf):
        """Process AIRTYPE value"""
        self._airtype = subtags[0][0]

    def airclass_val(self, (_tag, begin, end, _subtags), buf):
        """Process AIRCLASS value"""
        self._airclass = buf[begin:end]

    def radius_val(self, (_tag, begin, end, _subtags), buf):
        """Process RADIUS value"""
        self._radius = buf[begin:end]

    def latitude_val(self, (_tag, begin, end, _subtags), buf):
        """Process LATITUDE value"""
        self._lat = Latitude(buf[begin:end])

    def longitude_val(self, (_tag, begin, end, _subtags), buf):
        """Process LONGITUDE value"""
        self._lon = Longitude(buf[begin:end])

    def fl_val(self, (_tag, begin, end, _subtags), buf):
        """Process FL value"""
        self._level = FlightLevel(buf[begin:end])

    def altitude_val(self, (_tag, begin, end, _subtags), buf):
        """Process ALTITUDE value"""
        self._level = Altitude(buf[begin:end])

    def height_val(self, (_tag, begin, end, _subtags), buf):
        """Process HEIGHT value"""
        self._level = Height(buf[begin:end])

    def unlimited_val(self, (_tag, _begin, _end, _subtags), _buf):
        """Process UNLIMITED value"""
        self._level = FlightLevel('FL999')
