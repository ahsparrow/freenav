#!/usr/bin/env python
"""Extract airspace data from Tim Newport-Peace format file."""
import math
from simpleparse.parser import Parser
from latlon import Latitude, Longitude

# EBNF grammar for TNP airspace format
decl = r"""
>file<          := (comment/nullline/exclude_block/include_yes/airspace/
                    airtype/class/end)*
airspace        := title,header,body
title           := 'TITLE',eq,title_val,eol
>header<        := (comment/nullline/class/airtype/base/tops/active)*
>body<          := (comment/nullline/point/circle/cw_arc/ccw_arc)*
<exclude_block> := include_no, -include_yes*, include_yes
<end>           := 'END',ts,eol*

point           := 'POINT',eq,latitude,ts,longitude,eol
circle          := 'CIRCLE',ts,radius,ts,centre,eol
cw_arc          := 'CLOCKWISE',ts,radius,ts,centre,ts,to,eol
ccw_arc         := 'ANTI-CLOCKWISE',ts,radius,ts,centre,ts,to,eol
airtype         := 'TYPE',eq,airtype_val,eol
base            := 'BASE',eq,level,eol
tops            := 'TOPS',eq,level,eol
class           := 'CLASS',eq,class_val,eol
active          := 'ACTIVE',eq,active_val,eol

radius          := 'RADIUS',eq,radius_val
centre          := 'CENTRE',eq,latitude,ts,longitude
to              := 'TO',eq,latitude,ts,longitude
level           := flight_level/altitude/height/unlimited

radius_val      := (digit+,'.',digit*)/digit+
latitude        := ('N'/'S'),digit,digit,digit,digit,digit,digit
longitude       := ('W'/'E'),digit,digit,digit,digit,digit,digit,digit
flight_level    := 'FL',digit+
altitude        := digit+,'ALT'
height          := (digit+,'AGL')/'SFC'
unlimited       := 'UNLTD'
title_val       := ('*',letter)/letter,-[#\n]*
airtype_val     := ctr/airways/restricted/prohibited/danger/other/training/
                   info/gsec/matz/tmz/boundary/unknown
class_val       := [A-GX]
active_val      := [A-Z]*

ctr             :='CTA/CTR'/'CTR'/'C'
airways         :='AIRWAYS'/'A'
restricted      :='RESTRICTED'/'R'
prohibited      :='PROHIBITED'/'P'
danger          :='DANGER'/'D'
other           :='OTHER'/'O'
training        :='TRAINING ZONE'/'Z'
info            :='TRAFFIC INFO'/'I'
gsec            :='GSEC'/'G'
matz            :='MATZ'/'M'
tmz             :='TMZ'/'T'
boundary        :='BOUNDARY'/'B'
unknown         :='X'/ts

<eol>           := (ts,comment)/nullline
<include_yes>   := 'INCLUDE',eq,'YES',ts,newline
<include_no>    := 'INCLUDE',eq,'NO',ts,newline
<comment>       := '#',-newline*,newline
<nullline>      := ts,newline
<eq>            := ts,'=',ts
<ts>            := [ \t]*
<digit>         := [0-9]
<letter>        := [A-Za-z]
<newline>       := '\n'/'\r\n'
"""

#------------------------------------------------------------------------------
# Airspace component classes

class Point:
    def __init__(self, lat_str, lon_str):
        self.lat = Latitude(lat_str)
        self.lon = Longitude(lon_str)

class Circle:
    def __init__(self, lat_str, lon_str, radius):
        self.centre = Point(lat_str, lon_str) 
        self.radius = float(radius)

class Arc:
    def __init__(self, lat_str, lon_str, clat_str, clon_str, radius):
        self.end = Point(lat_str, lon_str)
        self.centre = Point(clat_str, clon_str)
        self.radius = float(radius)

class CcwArc(Arc):
    pass

class CwArc(Arc):
    pass

#------------------------------------------------------------------------------
# Height classes
class Vertitude:
    def __str__(self):
        return self.fmt_str % self.level

    def __int__(self):
        return self.level

class FlightLevel(Vertitude):
    def __init__(self, fl_str):
        self.level = int(fl_str[2:])
        self.fmt_str = "FL%03d"

    def __int__(self):
        return self.level * 100

class Height(Vertitude):
    def __init__(self, height_str):
        if height_str=="SFC":
            self.level = 0
        else:
            self.level = int(height_str[:-3])
        self.fmt_str = "%dAGL"

    def __str__(self):
        if self.level==0:
            return "SFC"
        else:
            return Vertitude.__str__(self)

class Altitude(Vertitude):
    def __init__(self, altitude):
        self.level = int(altitude[:-3])
        self.fmt_str = "%dALT"

class Unlimited(Vertitude):
    def __init__(self):
        self.fmt_str = "FL999"

    def __int__(self):
        return 99999

#------------------------------------------------------------------------------
# TNP parsing class
class TnpProcessor:
    """Splits airspace into list of segments and class "virtual"
       add_airspace method. This class should be sub-classed with an
       application specific add_airspace method.

    """
    def __init__(self, data):
        self.data = data

    def process(self, production):
        """Process data from simpleparse and call add_airspace method."""
        if production:
            for tag, beg, end, parts in production:
                if tag == 'airspace':
                    self.airlist = []

                val = self.data[beg:end]
                self.process(parts)

                if tag == 'airspace':
                    self.add_airspace(self.title, self.airclass, self.airtype,
                                      self.base, self.tops, self.airlist)
                elif tag == 'point':
                    self.airlist.append(Point(self.lat, self.lon))
                elif tag == 'circle':
                    self.airlist.append(Circle(self.lat, self.lon, self.radius))
                elif tag == 'cw_arc':
                    self.airlist.append(CwArc(self.lat, self.lon, self.clat,
                                              self.clon, self.radius))
                elif tag == 'ccw_arc':
                    self.airlist.append(CcwArc(self.lat, self.lon, self.clat,
                                               self.clon, self.radius))
                elif tag == 'base':
                    self.base = self.level
                elif tag == 'tops':
                    self.tops = self.level
                elif tag == 'centre':
                    self.clat = self.lat
                    self.clon = self.lon
                elif tag == 'title_val':
                    self.title = val.strip()
                elif tag == 'latitude':
                    self.lat = val
                elif tag == 'longitude':
                    self.lon = val
                elif tag == 'radius_val':
                    self.radius = val
                elif tag == 'unlimited':
                    self.level = Unlimited("FL999")
                elif tag == 'altitude':
                    self.level = Altitude(val)
                elif tag == 'height':
                    self.level = Height(val)
                elif tag == 'flight_level':
                    self.level = FlightLevel(val)
                elif tag == 'airtype_val':
                    self.airtype = parts[0][0]
                elif tag == 'class_val':
                    self.airclass = val

if __name__ == '__main__':
    main()
