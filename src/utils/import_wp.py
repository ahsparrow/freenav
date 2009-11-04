#!/usr/bin/env python
# Import file format is tab delimitted from Worldwide Soaring Turnpoint
# Exchange

import csv
import getopt
import math
import sys

import freenav.freedb
import freenav.projection

FT_TO_M = 0.3048

def importwp(db, csv_file, projection):
    reader = csv.reader(csv_file, delimiter='\t')
    header = reader.next()

    for fields in reader:
        wp = dict(zip(header, fields))
        lat = float(wp['Latitude [degrees]']) +\
            float(wp['Latitude [decimal minutes]']) / 60
        lon = float(wp['Longitude [degrees]']) +\
            float(wp['Longitude [decimal minutes]']) / 60
        if wp['East/West'] == 'W':
            lon = -lon

        x, y = projection.forward(math.radians(lat), math.radians(lon))

        control_p = wp['Control P']
        if set(control_p).intersection("ADHLYyZz"):
            landable_flag = 1
        else:
            landable_flag = 0

        db.insert_waypoint(wp['Name'], wp['ID'], int(x), int(y),
                           int(int(wp['Elevation [Feet]'])*FT_TO_M),
                           wp['Turnpoint'], wp['Comments'], landable_flag)

def usage():
    print 'usage: import_wp [options] input_file'
    print ''
    print 'Options:'
    print '    -a   Append data to existing database'

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ha')
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    append_flag = False
    for o, a in opts:
        if o == '-h':
            usage()
            sys.exit()
        if o == '-a':
            append_flag = True

    if len(args) != 1:
        usage()
        sys.exit(2)
    else:
        wp_file = args[0]

    db = freenav.freedb.Freedb()
    if not append_flag:
        db.delete_waypoints()

    p = db.get_projection()
    importwp(db, open(wp_file),
        freenav.projection.Lambert(p['Parallel1'], p['Parallel2'],
                                   p['Latitude'], p['Longitude']))
    db.commit()

if __name__ == '__main__':
    main()
