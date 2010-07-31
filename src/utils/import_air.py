#!/usr/bin/env python
"""Import airspace data from Tim Newport-Peace format file.

Airspace data is imported in lat/lon format from a TNP file. Data is
converted to X-Y via a Lambert projection and store in the freeflight
data base.

Positive X coordinates are Eastwards
Positive Y coordinates are Northwards
Angles are relative to the X-axis with positive angles towards the Y axis,
i.e. anti-clockwise

"""

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
                # Insert an airspace line
                lat, lon = p.lat.radians(), p.lon.radians()
                x1, y1 = self.projection.forward(lat, lon)

                self.db.insert_airspace_line(id, x1, y1, x, y)

                # Extent of the newly inserted line
                extent = min(x, x1), min(y, y1), max(x, x1), max(y, y1)

            elif isinstance(p, tnp.Arc):
                # Insert an airspace arc
                lat, lon = p.end.lat.radians(), p.end.lon.radians()
                x1, y1 = self.projection.forward(lat, lon)

                lat, lon = p.centre.lat.radians(), p.centre.lon.radians()
                xc, yc, = self.projection.forward(lat, lon)

                radius = p.radius * NM_TO_M
                start = math.atan2(y - yc, x - xc)
                end = math.atan2(y1 - yc, x1 - xc)

                len = end - start
                if isinstance(p, tnp.CcwArc):
                    if len < 0:
                        len += 2 * math.pi
                else:
                    if len > 0:
                        len -= 2 * math.pi

                self.db.insert_airspace_arc(id, xc, yc, radius, start, len)

                # Extent (sort of) of newly inserted arc
                extent = xc - radius, yc - radius, xc + radius, yc + radius

            # Recursively add remaining segments
            mm = self.add_segments(id, x1, y1, airlist[1:])

            return (min(extent[0], mm[0]),
                    min(extent[1], mm[1]),
                    max(extent[2], mm[2]),
                    max(extent[3], mm[3]))
        else:
            return x, y, x, y

    def add_airspace(self, name, airclass, airtype, base, tops, airlist):
        """Add a new airspace volume"""
        if int(base) <= MAX_LEVEL:
            # Increment internal ID
            self.id += 1
            id = 'A'+str(self.id)

            # Get the first part of the boundary
            p = airlist[0]
            if isinstance(p, tnp.Circle):
                # Circle is a special case - it defines the boundary in a
                # single segment
                x, y = self.projection.forward(p.centre.lat.radians(),
                                               p.centre.lon.radians())
                radius = p.radius * NM_TO_M
                self.db.insert_airspace_circle(id, x, y, radius)

                # Calculate maximum X/Y extents
                extent = (x - radius, y - radius, x + radius, y + radius)

            else:
                # If it isn't a circle it must be a point
                x, y = self.projection.forward(p.lat.radians(), p.lon.radians())
                extent = self.add_segments(id, x, y, airlist[1:])

            self.db.insert_airspace(id, name, str(base), str(tops), *extent)

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
    parser = Parser(tnp.TNP_DECL, 'tnp_file')
    p = db.get_projection()
    proj = freenav.projection.Lambert(p['parallel1'], p['parallel2'],
                                      p['latitude'], p['longitude'])
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
    db.commit()
    db.vacuum()

if __name__ == '__main__':
    main()
