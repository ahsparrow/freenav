#!/usr/bin/env python
"""Convert (sensibly formatted) TNP format airspace into (barking) Openair
   format
"""
import sys
from simpleparse.parser import Parser
from optparse import OptionParser

import tnp

open_air_colours = """* Class B
AC B
SP 0,2,255,0,0
SB -1,-1,-1
* Class C
AC C
SP 0,1,255,255,255
SB -1,-1,-1
* Class D
AC D
SP 0,1,0,0,255
SB -1,-1,-1
* Class E
AC E
SP 0,2,255,255,255
SB -1,-1,-1
* Danger
AC Q
SP 0,1,255,0,0
SB -1,-1,-1
* Restricted
AC R
SP 0,1,255,0,0
SB -1,-1,-1
* Prohibited
AC P
SP 0,1,255,0,0
SB -1,-1,-1
* CTR
AC CTR
SP 0,1,128,128,128
SB -1,-1,-1
"""

def fmt_lat(lat):
    """Return string with latitude in Openair format."""
    return "%(deg)02d:%(min)02d:%(sec)02d%(ns)s" % lat.dms()

def fmt_lon(lon):
    """Return string with longitude in Openair format."""
    return "%(deg)03d:%(min)02d:%(sec)02d%(ew)s" % lon.dms()

class OpenairProcessor(tnp.TnpProcessor):
    """Class to convert TNP to Openair format."""
    def __init__(self, data, file_name, max_level):
        tnp.TnpProcessor.__init__(self, data)
        self.max_level = max_level

        self.f = open(file_name, 'w')
        self.f.write(open_air_colours)

    def add_airspace(self, name, air_class, air_type, base, tops, air_list):
        if int(base)>self.max_level:
            return

        # Map TNP airspace class/type onto single Openair airspace class. Note
        # WinPilot doesn't have class A user airspace - how crap is that?
        if air_type=='danger':
            openair_type = 'Q'
        elif air_type=='matz':
            openair_type = 'CTR'
        elif air_type=='restricted':
            openair_type = 'R'
        elif air_type== 'prohibited':
            openair_type = 'P'
        elif air_type=='gsec':
            if air_class=='C':
                openair_type = 'W'
            elif air_class == 'X':
                openair_type = 'Q'
            elif air_class == 'A':
                openair_type = 'B'
            elif air_class == 'D':
                openair_type = 'D'
            else:
                print "Unknown airspace type for "+name
                openair_type = 'Q'
        elif air_type=='airways':
            openair_type = 'B'
        elif air_type=='ctr':
            if air_class=='A':
                openair_type = 'B'
            elif air_class=='D':
                openair_type = 'D'
            elif air_class=='E':
                openair_type = 'E'
            else:
                openair_type = 'Q'
        else:
            print "Unknown airspace type for "+name
            openair_type = 'Q'

        self.f.write('*\n')
        self.f.write('AC %s\n' % openair_type)
        self.f.write('AN %s\n' % name)
        self.f.write('AL %s\n' % base)
        self.f.write('AH %s\n' % tops)

        for seg in air_list:
            if isinstance(seg, tnp.Circle):
                self.f.write('V X=%s %s\n' % (fmt_lat(seg.centre.lat),
                                              fmt_lon(seg.centre.lon)))
                self.f.write('DC %.1f\n' % seg.radius)

            if isinstance(seg, tnp.Point):
                self.f.write('DP %s %s\n' % (fmt_lat(seg.lat),
                                             fmt_lon(seg.lon)))
                self.prev_lat = seg.lat
                self.prev_lon = seg.lon

            if isinstance(seg, tnp.Arc):
                if isinstance(seg, tnp.CcwArc):
                    self.f.write('V D=-\n')
                else:
                    self.f.write('V D=+\n')

                self.f.write('V X=%s %s\n' % (fmt_lat(seg.centre.lat),
                                              fmt_lon(seg.centre.lon)))
                self.f.write('DB %s %s, %s %s\n' %
                    (fmt_lat(self.prev_lat), fmt_lon(self.prev_lon),
                     fmt_lat(seg.end.lat), fmt_lon(seg.end.lon)))
                self.prev_lat = seg.end.lat
                self.prev_lon = seg.end.lon

def main():
    usage = "usage: %prog [options] tnp_file openair_file"
    parser = OptionParser(usage=usage)
    parser.set_defaults(max_level=99999)
    parser.add_option("-m", "--max_level", type='int',
                      help="Max. level cut-off")
    options, args = parser.parse_args()

    # Get filenames
    if len(args) != 2:
        parser.print_help()
        sys.exit(2)
    else:
        tnp_filename = args[0]
        openair_filename = args[1]

    # Read and parse input file
    airdata = open(tnp_filename).read()
    parser = Parser(tnp.decl, 'file')
    (success, parse_result, next_char) = parser.parse(airdata)

    # Report any syntax errors
    if not (success and next_char==len(airdata)):
        print "%s: Syntax error at line %d" % \
            (in_filename, len(airdata[:next_char].splitlines())+1)
        sys.exit(1)

    # Process the parsed data
    air_processor = OpenairProcessor(airdata, openair_filename,
                                     options.max_level)
    air_processor.process(parse_result)

if __name__ == '__main__':
    main()
