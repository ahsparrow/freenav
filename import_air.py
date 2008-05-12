#!/usr/bin/env python
#
# Import airspace data from Tim Newport-Peace format file
#

import tnp
from simpleparse.parser import Parser
import freedb, projection
import math, sys
import getopt

MAX_LEVEL = 7000
NM_TO_M = 1852

# Airspace processor to generate data for navplot
class NavProcessor(tnp.TnpProcessor):
    def add_airspace(self, name, airtype, base, airlist):
        p = airlist[0]
        if base<=5000:
            print '# -b'
            if isinstance(p, tnp.Circle):
                rad = p.radius/60.0
                lon_scale = math.cos(math.radians(p.lat))
                for i in range(101):
                    ang = 2*math.pi*i/100.0
                    lat = p.lat + rad*math.sin(ang)
                    lon = p.lon + rad*math.cos(ang)/lon_scale
                    print '%f\t%f' % (lon, lat)
            else:
                self.add_segments(p.lat, p.lon, airlist[1:])

    def add_segments(self, lat, lon, airlist):
        print '%f\t%f' % (lon, lat)
        if airlist:
            p = airlist[0]

            if isinstance(p, tnp.Arc):
                radius = p.radius/60.0
                start = tnp.tc(p.clat, p.clon, lat, lon)
                end = tnp.tc(p.clat, p.clon, p.lat, p.lon)
                len = end - start

                # Kludge nasty 360 degree wrap-around problem
                if isinstance(p, tnp.CwArc):
                    if len < 0:
                        len += 360
                else:
                    if len > 0:
                        len -= 360

                # Draw arc using approx 3 degree segments
                n = int(abs(len)/3.0)
                lon_scale = math.cos(math.radians(p.clat))
                for i in range(n):
                    ang = math.radians(start + i*len/n)
                    lat = p.clat + radius*math.cos(ang)
                    lon = p.clon + radius*math.sin(ang)/lon_scale
                    print '%f\t%f' % (lon, lat)

            self.add_segments(p.lat, p.lon, airlist[1:])

# Airspace processor to generate data for freenav
class AirProcessor(tnp.TnpProcessor):
    def __init__(self, data, db, projection):
        tnp.TnpProcessor.__init__(self, data)
        self.db = db
        self.projection = projection
        self.id = 0

    def add_segments(self, id, x, y, airlist):
        if airlist:
            p = airlist[0]
            x1, y1 = self.projection.forward(p.lat, p.lon)

            if isinstance(p, tnp.Point):
                self.db.insert_airspace_line(id, x1, y1, x, y)
                xmin, ymin, xmax, ymax = \
                        min(x, x1), min(y, y1), max(x, x1), max(y, y1)
            elif isinstance(p, tnp.Arc):
                xc, yc, = self.projection.forward(p.clat, p.clon)
                radius = p.radius*NM_TO_M
                start = math.degrees(math.atan2(y-yc, x-xc))
                end = math.degrees(math.atan2(y1-yc, x1-xc))
                len = end-start
                if isinstance(p, tnp.CcwArc):
                    if len < 0:
                        len += 360
                else:
                    if len > 0:
                        len -= 360
                self.db.insert_airspace_arc(id, xc, yc, radius, start, len)
                xmin, ymin, xmax, ymax = \
                        xc-radius, yc-radius, xc+radius, yc+radius

            mm = self.add_segments(id, x1, y1, airlist[1:])
            return min(xmin, mm[0]), min(ymin, mm[1]), \
                   max(xmax, mm[2]), max(ymax, mm[3])
        else:
            return x, y, x, y

    def add_airspace(self, name, airtype, base, airlist):
        if base <= MAX_LEVEL:
            self.id += 1
            id = 'A'+str(self.id)
            p = airlist[0]

            x, y = self.projection.forward(p.lat, p.lon)
            if isinstance(p, tnp.Circle):
                radius = p.radius*NM_TO_M
                self.db.insert_airspace_circle(id, x, y, radius)
                xmin, ymin, xmax, ymax = x-radius, y-radius, x+radius, y+radius
            else:
                xmin, ymin, xmax, ymax = \
                    self.add_segments(id, x, y, self.airlist[1:])
            self.db.insert_airspace_parent(id, name, xmin, ymin, xmax, ymax)

def usage():
    print 'usage: import_air [options] input_file'
    print ''
    print 'Options:'
    print '    -n    Generate data for navplot'

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn')
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    # Get any options
    navFlag = False
    for o, a in opts:
        if o == '-h':
            usage()
            sys.exit()
        if o == '-n':
            navFlag = True

    # Get the input filename
    if len(args) != 1:
        usage()
        sys.exit(2)
    else:
        filename = args[0]

    airdata = file(filename).read()

    parser = Parser(tnp.decl, 'file')
    success, parse_result, next_char = parser.parse(airdata)
    assert success and next_char==len(airdata),\
        "Error - next char is %d" % next_char

    if not navFlag:
        db = freedb.Freedb()
        db.delete_airspace()

        air_processor = AirProcessor(airdata, db,
                                     projection.Lambert(*db.get_projection()))
        air_processor.process(parse_result)

        db.create_airspace_indices()
        db.commit()
        db.vacuum()
    else:
        air_processor = NavProcessor(airdata)
        air_processor.process(parse_result)


if __name__ == '__main__':
    main()
