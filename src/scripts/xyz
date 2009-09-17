#!/usr/bin/env python

import sys
import getopt
import socket
import gtk
import gobject
import gps

asi_markup = '<span size="92000" weight="bold">%d</span>'
latlon_markup = '<span size="22000" weight="bold">%s</span>'

def deg_to_dmm(val):
    dec = int(round(val * 60 * 1000))
    min = dec / 1000
    dec = dec % 1000
    deg = min / 60
    min = min % 60
    return (deg, min, dec)

def fmt_lat(lat):
    if lat < 0:
        hemi = "S"
        lat = -lat
    else:
        hemi = "N"

    (deg, min, dec) = deg_to_dmm(lat)
    return "%s%02d %02d.%03d" % (hemi, deg, min, dec)

def fmt_lon(lon):
    if lon < 0:
        hemi = "W"
        lon = -lon
    else:
        hemi = "E"

    (deg, min, dec) = deg_to_dmm(lon)
    return "%s%03d %02d.%03d" % (hemi, deg, min, dec)

class App:
    def __init__(self, gps):
        self.gps = gps

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_border_width(3)
        self.window.connect('destroy', gtk.main_quit)

        vbox = gtk.VBox(False, 5)
        self.window.add(vbox)

        self.lat_label = gtk.Label('')
        self.lon_label = gtk.Label('')
        vbox.pack_start(self.lat_label, True, False, 0)
        vbox.pack_start(self.lon_label, True, False, 0)

        self.asi_label = gtk.Label('')
        vbox.pack_start(self.asi_label, True, False, 0)

        gobject.timeout_add(1000, self.timeout)
        self.window.show_all()

    def timeout(self):
        try:
            self.gps.query('gp\n')
        except socket.error:
            md = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                type=gtk.MESSAGE_ERROR,
                message_format='Lost connection to gpsd server')
            md.run()
            gtk.main_quit()
            return True

        self.asi_label.set_markup(asi_markup % self.gps.borgelt.air_speed)

        fix = self.gps.fix
        self.lat_label.set_markup(latlon_markup % fmt_lat(fix.latitude))
        self.lon_label.set_markup(latlon_markup % fmt_lon(fix.longitude))

        self.window.queue_draw()
        return True

    def main(self):
        gtk.main()

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'g:')
    except getopt.GetoptError:
        print "Bad option"
        sys.exit(2)

    gpshost = 'localhost'
    for o, a in opts:
        if o == '-g':
            gpshost = a

    app = App(gps.gps(host=gpshost))
    app.main()

if __name__ == '__main__':
    main()
