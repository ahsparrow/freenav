#!/usr/bin/env python
#
# Extract airspace data from Tim Newport-Peace format file
#

decl = r'''
>file<          := (comment/nullline/exclude_block/include_yes/airspace/
                    airtype/class/end)*
airspace        := title,body
title           := 'TITLE',eq,title_val,eol
>body<          := (comment/nullline/include_yes/statement)*
>statement<     := point/circle/cw_arc/ccw_arc/airtype/base/tops/class/active
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
height          := (digit+,'AAL')/(digit+,'AGL')/'SFC'
unlimited       := 'UNLTD'
title_val       := (letter/'*'),-[#\n]*
airtype_val     := [A-Z/]*
class_val       := [A-GX]
active_val      := [A-Z]*

<eol>           := (ts,comment)/nullline
<include_yes>   := 'INCLUDE',eq,'YES',ts,'\n'
<include_no>    := 'INCLUDE',eq,'NO',ts,'\n'
<comment>       := '#',-'\n'*,'\n'
<nullline>      := ts,'\n'
<eq>            := ts,'=',ts
<ts>            := [ \t]*
<digit>         := [0-9]
<letter>        := [A-Za-z]
'''

from simpleparse.parser import Parser
import math

LEVEL_UNLIMITED = 50000

# Returns (initial) course from point1 to point2, degrees relative to North
# Return value will be in the range +/- 180 degrees
def tc(lat1, lon1, lat2, lon2):
    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)
    d1 = math.sin(lon2-lon1)*math.cos(lat2)
    d2 = math.cos(lat1)*math.sin(lat2)-\
         math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1)
    return math.degrees(math.atan2(d1, d2))

class Point:
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

class Circle:
    def __init__(self, lat, lon, radius):
        self.lat = lat
        self.lon = lon
        self.radius = radius

class Arc:
    def __init__(self, lat, lon, clat, clon, radius):
        self.lat = lat
        self.lon = lon
        self.clat = clat
        self.clon = clon
        self.radius = radius

class CcwArc(Arc):
    pass

class CwArc(Arc):
    pass

class TnpProcessor:
    def __init__(self, data):
        self.data = data

    # Splits airspace into lists of segments and calls "virtual" add_airspace
    # method. The class should be sub-classed with an application specific
    # add_airspace method
    def process(self, production):
        if production:
            for tag, beg, end, parts in production:
                if tag == 'airspace':
                    self.airlist = []

                val = self.data[beg:end]
                self.process(parts)

                if tag == 'airspace':
                    self.add_airspace(self.title, self.airtype, self.base,
                                      self.airlist)
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
                elif tag == 'centre':
                    self.clat = self.lat
                    self.clon = self.lon
                elif tag == 'title_val':
                    self.title = val.strip()
                elif tag == 'latitude':
                    self.lat =\
                        int(val[1:3])+int(val[3:5])/60.0+int(val[5:7])/3600.0
                    if val[0] == 'S':
                        self.lat = -self.lat
                elif tag == 'longitude':
                    self.lon = \
                        int(val[1:4])+int(val[4:6])/60.0+int(val[6:8])/3600.0
                    if val[0] == 'W':
                        self.lon = -self.lon
                elif tag == 'radius_val':
                    self.radius = float(val)
                elif tag == 'unlimited':
                    self.level = LEVEL_UNLIMITED
                elif tag == 'altitude':
                    self.level = int(val[:-3])
                elif tag == 'height':
                    if val == 'SFC':
                        self.level = 0
                    else:
                        self.level = int(val[:-3])
                elif tag == 'height':
                    self.level = int(val[:-3])
                elif tag == 'flight_level':
                    self.level = 100*int(val[2:])
                elif tag == 'airtype_val':
                    self.airtype = val.strip()


if __name__ == '__main__':
    main()
