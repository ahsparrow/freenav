#!/usr/bin/env python
# Import file format is tab delimitted from Worldwide Soaring Turnpoint
# Exchange

import freedb, projection
import csv, math, sys

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

        x, y = projection.forward(lat, lon)

        db.insert_waypoint(wp['Name'], wp['ID'], int(x), int(y),
                           int(int(wp['Elevation [Feet]'])*FT_TO_M))

def main():
    wp_file = sys.argv[1]
    db = freedb.Freedb()

    db.delete_waypoints()
    db.drop_waypoint_indices()
    importwp(db, file(wp_file), projection.Lambert(*db.get_projection()))

    db.create_waypoint_indices()
    db.commit()

if __name__ == '__main__':
    main()
