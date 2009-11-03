#!/usr/bin/env python
#
# Import airspace data from Tim Newport-Peace format file
#

import math
import getopt
import sys

from simpleparse.parser import Parser
import freenav.freedb
import freenav.projection
import freenav.tnp as tnp

MAX_LEVEL = 7000
NM_TO_M = 1852

# Airspace processor to generate data for freenav
class AirProcessor():
    def __init__(self, db, projection):
        self.db = db
        self.projection = projection
        self.id = 0

    def add_segments(self, id, x, y, airlist):
        if airlist:
            p = airlist[0]

            if isinstance(p, tnp.Point):
                x1, y1 = self.projection.forward(p.lat.radians(),
                                                 p.lon.radians())
                self.db.insert_airspace_line(id, x1, y1, x, y)
                xmin, ymin, xmax, ymax = \
                        min(x, x1), min(y, y1), max(x, x1), max(y, y1)
            elif isinstance(p, tnp.Arc):
                x1, y1 = self.projection.forward(p.end.lat.radians(),
                                                 p.end.lon.radians())
                xc, yc, = self.projection.forward(p.centre.lat.radians(),
                                                  p.centre.lon.radians())
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

    def add_airspace(self, name, airclass, airtype, base, tops, airlist):
        if int(base) <= MAX_LEVEL:
            self.id += 1
            id = 'A'+str(self.id)
            p = airlist[0]

            if isinstance(p, tnp.Circle):
                x, y = self.projection.forward(p.centre.lat.radians(),
                                               p.centre.lon.radians())
                radius = p.radius*NM_TO_M
                self.db.insert_airspace_circle(id, x, y, radius)
                xmin, ymin, xmax, ymax = x-radius, y-radius, x+radius, y+radius
            else:
                x, y = self.projection.forward(p.lat.radians(), p.lon.radians())
                xmin, ymin, xmax, ymax = \
                    self.add_segments(id, x, y, airlist[1:])
            self.db.insert_airspace_parent(id, name, str(base), str(tops),
                                           xmin, ymin, xmax, ymax)

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

    # Initialise data base
    db = freenav.freedb.Freedb()
    db.delete_airspace()

    # Initialise parser
    parser = Parser(tnp.tnp_decl, 'tnp_file')
    p = db.get_projection()
    proj = freenav.projection.Lambert(p['Parallel1'], p['Parallel2'],
                                      p['Ref_Lat'], p['Ref_Lon'])
    output_processor = AirProcessor(db, proj)
    tnp_processor = tnp.TnpProcessor(output_processor)

    # Read data and parse
    airdata = open(filename).read()
    success, parse_result, next_char = parser.parse(airdata,
                                                    processor=tnp_processor)

    # Report any syntax errors
    if not (success and next_char==len(airdata)):
        print "%s: Syntax error at (or near) line %d" % \
            (filename, len(airdata[:next_char].splitlines())+1)
        sys.exit(1)

    # Create indices and tidy up
    db.create_airspace_indices()
    db.commit()
    db.vacuum()

if __name__ == '__main__':
    main()
