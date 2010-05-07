#!/usr/bin/env python
# Turnpoint file format is tab delimitted from Worldwide Soaring Turnpoint
# Exchange

import csv
import math
import optparse
import sys

import yaml

import freenav.freedb
import freenav.projection

FT_TO_M = 0.3048

def import_turnpoints(db, csv_file, projection):
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
            db.insert_landable(wp['Name'], wp['ID'], int(x), int(y),
                               int(int(wp['Elevation [Feet]']) * FT_TO_M))

def import_landables(db, landouts_file, projection):
    for landout in yaml.load(landouts_file):
        lat_str = landout['latitude']
        lon_str = landout['longitude']

        if '.' in lat_str:
            lat = int(lat_str[:2]) + float(lat_str[3:]) / 60
        else:
            lat = (int(lat_str[:2]) + int(lat_str[3:5]) / 60.0 +
                   int(lat_str[5:7]) / 3600.0)

        if '.' in lon_str:
            lon = int(lon_str[:3]) + float(lon_str[4:]) / 60
        else:
            lon = (int(lon_str[:3]) + int(lon_str[4:6]) / 60.0 +
                   int(lon_str[6:8]) / 3600.0)
        if lon_str[3] == 'W':
            lon = -lon

        x, y = projection.forward(math.radians(lat), math.radians(lon))

        db.insert_landable(landout['name'], landout['id'], int(x), int(y),
                          int(landout['elevation'] * FT_TO_M))

def main():
    usage = "usage: %prog [options] file"
    parser = optparse.OptionParser(usage)
    parser.add_option('-a', '--append', dest='append_flag', default=False,
                      action="store_true", help='Append to existing table')
    parser.add_option('-t', '--turnpoints', default=False,
                      action="store_true", help='Add BGA turnpoints')
    parser.add_option('-f', '--fields', default=False,
                      action="store_true", help='Add landing fields')
    (options, args) = parser.parse_args()

    if len(args) != 1:
        parser.error("wrong number of arguments")

    db = freenav.freedb.Freedb()
    if not options.append_flag:
        db.delete_landables()

    p = db.get_projection()
    lambert = freenav.projection.Lambert(p['parallel1'], p['parallel2'],
                                         p['latitude'], p['longitude'])

    if options.fields:
        import_landables(db, open(args[0]), lambert)
    elif options.turnpoints:
        import_turnpoints(db, open(args[0]), lambert)
    else:
        parser.error("must specify turnpoints or fields")

    db.commit()

if __name__ == '__main__':
    main()
