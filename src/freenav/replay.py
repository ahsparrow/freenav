#!/usr/bin/env python
import datetime
import fcntl
import math
import os
import pty
import sys
import termios
import time

import projection

KTS_TO_MPS = 1852.0 / 3600
M_TO_FT = 1 / 0.3048

GPRMC_FMT = "$GPRMC,%s,A,%02d%06.3f,%s,%03d%06.3f,%s,%.1f,%d,%s,0.0,E"
GPGGA_FMT = "$GPGGA,%s,%02d%06.3f,%s,%03d%06.3f,%s,1,12,1.0,%d,M,0.0,M,,"
PGRMZ_FMT = "$PGRMZ,%d,F,2"

GPS_SYMLINK_NAME = "/tmp/gps"

def gen_gprmc(lat, lon, speed, course, dt):
    lat_deg, lat_min, northing = dm_split(lat, "NS")
    lon_deg, lon_min, easting = dm_split(lon, "EW")

    tim_str = dt.strftime("%H%M%S")
    date_str = dt.strftime("%d%m%y")

    nmea = GPRMC_FMT % (tim_str, lat_deg, lat_min, northing,
                        lon_deg, lon_min, easting, 
                        speed / KTS_TO_MPS , math.degrees(course), date_str)
    nmea = add_checksum(nmea)
    return nmea

def gen_gpgga(lat, lon, altitude, dt):
    lat_deg, lat_min, northing = dm_split(lat, "NS")
    lon_deg, lon_min, easting = dm_split(lon, "EW")

    tim_str = dt.strftime("%H%M%S")

    nmea = GPGGA_FMT % (tim_str, lat_deg, lat_min, northing,
                        lon_deg, lon_min, easting, int(altitude))
    nmea = add_checksum(nmea)
    return nmea

def gen_pgrmz(altitude):
    alt_ft = altitude * M_TO_FT
    nmea = PGRMZ_FMT % alt_ft
    nmea = add_checksum(nmea)
    return nmea

def add_checksum(data):
    checksum = 0;
    for i in range(len(data) - 1):
        checksum = checksum ^ ord(data[i + 1])

    checksum = hex(checksum)[2:].upper()
    return data + '*' + checksum + "\r\n"

def dm_split(latlon, hemi_vals):
    if latlon >= 0:
        hemi = hemi_vals[0]
    else:
        hemi = hemi_vals[1]
        latlon = -latlon

    latlon_degs = math.degrees(latlon)
    milli_mins = int(latlon_degs * 60000)
    deg = milli_mins / 60000
    min = (milli_mins % 60000) / 1000.0
    return (deg, min, hemi)

def igc_parse(rec):
    tim_str = rec[1:7]
    lat_str = rec[7:15]
    lon_str = rec[15:24]
    pressure_alt_str = rec[25:30]
    gps_alt_str = rec[30:35]
    gs_str = rec[35:38]
    trk_str = rec[41:44]

    tim = datetime.datetime.strptime(tim_str + "2000", "%H%M%S%Y")
    dt = datetime.datetime.combine(datetime.datetime.today(), tim.time())

    lat = math.radians(int(lat_str[:2]) +
                       (int(lat_str[2:7]) / 60000.0))
    lon = math.radians(int(lon_str[:3]) +
                       (int(lon_str[3:8]) / 60000.0))
    if lon_str[-1] == 'W':
        lon = -lon

    gps_alt = int(gps_alt_str)
    pressure_alt = int(pressure_alt_str)

    return dt, lat, lon, gps_alt, pressure_alt

def main():
    stdin_fd = sys.stdin.fileno()
    oldterm = termios.tcgetattr(stdin_fd)
    newattr = termios.tcgetattr(stdin_fd)
    newattr[3] = newattr[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(stdin_fd, termios.TCSANOW, newattr)
    oldflags = fcntl.fcntl(stdin_fd, fcntl.F_GETFL)
    fcntl.fcntl(stdin_fd, fcntl.F_SETFL, oldflags | os.O_NONBLOCK)

    master_fd, slave_fd = pty.openpty()

    slave_name = os.ttyname(slave_fd)
    try:
        os.unlink(GPS_SYMLINK_NAME)
    except OSError:
        pass
    os.symlink(slave_name, GPS_SYMLINK_NAME)

    (iflag, oflag,
     cflag, lflag, ispeed, ospeed, cc) = termios.tcgetattr(slave_fd)
    iflag = oflag = lflag = 0
    cc[termios.VMIN] = 1
    cflag = termios.CREAD | termios.CLOCAL
    termios.tcsetattr(slave_fd, termios.TCSANOW,
                      [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])

    igc_file = open(sys.argv[1])
    proj = projection.Lambert(math.radians(49), math.radians(55),
                              math.radians(52), math.radians(0))

    for rec in igc_file:
        if rec[0] == 'B':
            break
    dt1, lat1, lon1, gps_alt, pressure_alt = igc_parse(rec)
    x1, y1 = proj.forward(lat1, lon1)

    sleep_time = 1.0

    try:
        for rec in igc_file:
            if rec[0] == 'B':
                dt, lat, lon, gps_alt, pressure_alt = igc_parse(rec)
                x, y = proj.forward(lat, lon)

                tdelta = dt - dt1
                dist = math.sqrt((x - x1) ** 2 + (y - y1) ** 2)
                speed = dist / tdelta.seconds
                track = math.atan2(x - x1, y - y1)

                dt1, x1, y1 = dt, x, y

                os.write(master_fd, gen_gprmc(lat, lon, speed, track, dt))
                os.write(master_fd, gen_gpgga(lat, lon, gps_alt, dt))
                os.write(master_fd, gen_pgrmz(pressure_alt))
                time.sleep(sleep_time)

            try:
                c = sys.stdin.read(1)
                if c == '+':
                    sleep_time = sleep_time * 2
                elif c == '-':
                    sleep_time = sleep_time / 2
                print "Sleep %.2f" % sleep_time
            except IOError:
                c = None
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, oldterm)
        fcntl.fcntl(stdin_fd, fcntl.F_SETFL, oldflags)

if __name__ == "__main__":
    main()
