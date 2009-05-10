#!/usr/bin/env python

import time, os

HEADER_STR = """HFFXA100\r
HPPLTPILOT:%s\r
HPGTYGLIDERTYPE:%s\r
HPGIDGLIDERID:%s\r
HFDTM100GPSDATUM:WGS 84\r
HFRFWFIRMWAREVERSION:0.1\r
HFRHWHARDWAREVERSION:0.1\r
HFFTYFRTYPE:Acme Log-o-matic,1.0\r\n"""

PILOT = 'Alan Sparrow'
GLIDER_TYPE = 'Mini Nimbus'
GLIDER_ID = 'HQY'

NUMCHAR = '123456789abcdefghijklmnopqrstuvwxyz'

WAIT = 1
LOG = 2
CLOSED = 3

class Logger:
    def __init__(self, dir):
        self.state = WAIT
        self.dir = dir

    def make_basename(self, tim):
        year = tim.tm_year % 10
        month = NUMCHAR[tim.tm_mon - 1]
        day = NUMCHAR[tim.tm_mday - 1]
        return ('%d%c%cx000' % (year, month, day))

    def latlon_to_dmm(self, latlon):
        t = int(round(abs(latlon)*60000))
        min, dec_min = divmod(t, 1000)
        deg, min = divmod(min, 60)
        return deg, min, dec_min

    def open(self):
        tim = time.localtime()
        basename = self.make_basename(tim)
        for c in NUMCHAR:
            filename = basename + c + '.igc'
            path = os.path.join(self.dir, filename)
            if not os.path.exists(path):
                break;

        if c != NUMCHAR[-1]:
            try:
                self.f = open(path, 'w')
                self.f.write('AXXX000\r\n')
                self.f.write('HFDTE%02d%02d%02d\r\n' %
                             (tim.tm_mday, tim.tm_mon, tim.tm_year % 100))
                self.f.write(HEADER_STR % (PILOT, GLIDER_TYPE, GLIDER_ID))

                # Write the I record (B record extension for TAS and GSP)
                self.f.write('I033638GSP3941TAS4244TRT\r\n')

                self.state = LOG
            except IOError:
                self.state = CLOSED
        else:
            self.state = CLOSED

    def close(self):
        self.state = CLOSED
        if self.state == LOG:
            self.f.close()

    def log(self, utc, lat, lon, alt, ground_speed, air_speed, track):
        if self.state == CLOSED:
            return

        if self.state == WAIT and ground_speed > 5:
            self.open()

        if self.state == LOG:
            fields = ['B']
            fields.append("%02d%02d%02d" % (utc.tm_hour, utc.tm_min, utc.tm_sec))
            fields.append('%02d%02d%03d' % self.latlon_to_dmm(lat))
            if lat < 0:
                fields.append('S')
            else:
                fields.append('N')
            fields.append('%03d%02d%03d' % self.latlon_to_dmm(lon))
            if lon < 0:
                fields.append('W')
            else:
                fields.append('E')
            fields.append('A')
            alt_str = '%05d' % alt
            fields.append(alt_str)
            fields.append(alt_str)
            fields.append('%03d' % ground_speed)
            fields.append('%03d' % air_speed)
            fields.append('%03d' % track)
            fields.append('\r\n')

            try:
                self.f.write(''.join(fields))
            except IOError:
                self.close()

def test():
    l = Logger()
    l.open('.', time.localtime())

    t = '2006-04-07Z12:34:56'
    lat = 1.2
    lon = 3.4
    alt = 3000
    air_speed = 50
    ground_speed = 60
    l.log(t, lat, lon, alt, air_speed, ground_speed)
    l.log(t, lat, lon, alt, air_speed, ground_speed)
    l.close()

if __name__ == '__main__':
    test()
