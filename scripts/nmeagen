#!/usr/bin/env python

import freedb
import projection

import gtk
import gobject
import math
import os, time, pty, signal, termios

FT_TO_METERS = 0.3048
KTS_TO_MPS = 0.5144444444
MPS_TO_KTS = 1/KTS_TO_MPS

ENTRIES = (('ALT', 'Altititude (ft)', '4000'),
           ('ASPD', 'Airspeed (kt)', '0'),
           ('GSPD', 'Ground speed (kt)', '0'),
           ('CRSE', 'Course (deg)', '0'),
           ('MCDY', 'MacCready (kt)', '0.0'),
           ('BLST', 'Ballast', '1.0'),
           ('BUGS', 'Bugs (%)', '0'))

class NmeaGen:
    def __init__(self):
        self.db = freedb.Freedb()
        self.lambert = projection.Lambert(*self.db.get_projection())
        self.x, self.y, alt = self.db.get_waypoint('RIV')
        self.time = time.time()

        self.master_fd, slave_fd = pty.openpty()
        slave = os.ttyname(slave_fd)

        pidfile = "/tmp/gpsfake_pid-%s" % os.getpid()
        spawncmd = "/usr/local/sbin/xgpsd -N -P%s %s" % (pidfile, slave)
        if os.system(spawncmd + ' &'):
            print 'Spawn failed'
            sys.exit(1)
        else:
            time.sleep(1)
            fp = open(pidfile)
            self.pid = int(fp.read())
            fp.close()
            os.remove(pidfile)

        speed = 0
        ttyfp = open(slave, 'rw')
        raw = termios.tcgetattr(ttyfp.fileno())
        raw[0] = 0
        raw[1] = termios.ONLCR
        raw[2] &= ~(termios.PARENB | termios.CRTSCTS)
        raw[2] |= (termios.CSIZE & termios.CS8)
        raw[2] |= termios.CREAD | termios.CLOCAL
        raw[3] = 0
        raw[4] = raw[5] = eval("termios.B" + `speed`)
        termios.tcsetattr(ttyfp.fileno(), termios.TCSANOW, raw)

    def set_values(self, altitude, air_speed, ground_speed, course, maccready,
                   ballast, bugs):
        self.altitude = int(altitude)*FT_TO_METERS
        self.ground_speed = int(ground_speed)*KTS_TO_MPS
        self.air_speed = int(air_speed)*KTS_TO_MPS
        self.course = int(course)
        self.maccready = float(maccready)
        self.ballast = float(ballast)
        self.bugs = int(bugs)

    def update(self):
        t = time.time()
        dt = t - self.time
        self.time = t

        self.x += dt*self.ground_speed*math.sin(math.radians(self.course))
        self.y += dt*self.ground_speed*math.cos(math.radians(self.course))

        gmt = time.gmtime(t)
        tstr = time.strftime('%H%M%S', gmt)
        datestr = time.strftime('%d%m%y', gmt)

        lat, lon = self.lambert.reverse(self.x, self.y)
        if lat > 0:
            northing = 'N'
        else:
            northing = 'S'
            lat = - lat

        if lon > 0:
            easting = 'E'
        else:
            easting = 'W'
            lon = -lon

        lat = math.degrees(lat)
        lon = math.degrees(lon)
        lat = int(lat*60000)
        lat_deg = lat/60000
        lat_min = (lat % 60000) / 1000.0
        lon = int(lon*60000)
        lon_deg = lon/60000
        lon_min = (lon % 60000) / 1000.0

        data = '$GPRMC,%s,A,%02d%06.3f,%s,%03d%06.3f,%s,%.1f,%d,%s,0.0,E'\
                % (tstr, lat_deg, lat_min, northing, lon_deg, lon_min, easting, 
                   self.ground_speed*MPS_TO_KTS, self.course, datestr)
        data = self.add_checksum(data)
        os.write(self.master_fd, data)
        time.sleep(0.1)

        data = '$GPGGA,%s,%02d%06.3f,%s,%03d%06.3f,%s,1,12,1.0,%d,M,0.0,M,,' % \
                (tstr, lat_deg, lat_min, northing, lon_deg, lon_min, easting,
                 int(self.altitude))
        data = self.add_checksum(data)
        os.write(self.master_fd, data)
        time.sleep(0.1)

        data = '$GPGSA,A,3,1,2,3,4,5,6,7,8,9,10,11,12,1.0,1.0,1.0'
        data = self.add_checksum(data)
        os.write(self.master_fd, data)
        time.sleep(0.1)

        data = '$PBB50,%d,.0,%03.1f,0,%d,%03.1f,1,23' % \
                (int(self.air_speed*MPS_TO_KTS),
                 self.maccready, self.bugs, self.ballast)
        data = self.add_checksum(data)
        os.write(self.master_fd, data)

    def add_checksum(self, data):
        checksum = 0;
        for i in range(len(data) - 1):
            checksum = checksum ^ ord(data[i + 1])

        checksum = hex(checksum)[2:].upper()
        return data + '*' + checksum + '\r\n'

class NmeaApp:
    def __init__(self):
        self.nmea_gen = NmeaGen()

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_border_width(10)
        self.window.connect('destroy', self.quit_callback)

        table = gtk.Table(len(ENTRIES), 2)
        table.set_row_spacings(5)
        table.set_col_spacings(5)

        self.entry= {}
        for n, e in enumerate(ENTRIES):
            label = gtk.Label(e[1]+':')
            label.set_alignment(1.0, 0.5)
            table.attach(label, 0, 1, n, n+1)

            entry = gtk.Entry()
            entry.set_width_chars(10)
            entry.set_text(e[2])
            table.attach(entry, 1, 2, n, n+1)

            self.entry[e[0]] = entry

        apply_button = gtk.Button(stock=gtk.STOCK_APPLY)
        apply_button.connect('clicked', self.apply_callback)
        quit_button = gtk.Button(stock=gtk.STOCK_QUIT)
        quit_button.connect('clicked', self.quit_callback)

        bbox = gtk.HButtonBox()
        bbox.add(apply_button)
        bbox.add(quit_button)

        vbox = gtk.VBox()
        vbox.set_spacing(10)
        vbox.pack_start(table)
        vbox.pack_end(bbox)

        self.apply_callback(None)
        gobject.timeout_add(2000, self.timeout_callback)

        self.window.add(vbox)
        self.window.show_all()

    def timeout_callback(self):
        self.nmea_gen.update()
        return True

    def apply_callback(self, widget, data=None):
        self.nmea_gen.set_values(self.entry['ALT'].get_text(),
                                 self.entry['ASPD'].get_text(),
                                 self.entry['GSPD'].get_text(),
                                 self.entry['CRSE'].get_text(),
                                 self.entry['MCDY'].get_text(),
                                 self.entry['BLST'].get_text(),
                                 self.entry['BUGS'].get_text())

    def quit_callback(self, widget, data=None):
        self.quit()

    def quit(self):
        os.kill(self.nmea_gen.pid, signal.SIGTERM)
        gtk.main_quit()

    def main(self):
        gtk.main()

def main():
    nmea_app = NmeaApp()
    nmea_app.main()

if __name__ == '__main__':
    main()
