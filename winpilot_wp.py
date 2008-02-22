#!/usr/bin/env python
# Import file format is tab delimitted from Worldwide Soaring Turnpoint
# Exchange

import csv, math, sys

def importwp(in_file, out_file):
    reader = csv.reader(in_file, delimiter='\t')
    header = reader.next()

    for fields in reader:
        wp = dict(zip(header, fields))

        wp_id = wp['ID']
        wp_name = wp['Name'].replace(',', '')
        wp_lat = ("%02d" % int(wp['Latitude [degrees]'])) + ':' +\
                 ("%06.3f" % float(wp['Latitude [decimal minutes]'])) +\
                 wp['North/South']
        wp_lon = ("%03d" % int(wp['Longitude [degrees]'])) + ':' +\
                 ("%06.3f" % float(wp['Longitude [decimal minutes]'])) +\
                 wp['East/West']
        wp_elev = wp['Elevation [Feet]'] + 'F'
        if set('ADHYyz').intersection(wp['Control P']):
            wp_attr = 'TA'
        else:
            wp_attr = 'T'
        wp_comment = wp['Turnpoint'].replace(',', '')

        out_file.write(("%s,%s,%s,%s,%s,%s,%s *Z50\n") %
            (wp_id, wp_lat, wp_lon, wp_elev, wp_attr, wp_name, wp_comment))

def main():
    turnpoint_file = sys.argv[1]
    winpilot_file = sys.argv[2]
    importwp(file(turnpoint_file), file(winpilot_file, 'w'))

if __name__ == '__main__':
    main()
