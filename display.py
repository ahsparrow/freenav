#!/usr/bin/env python

import sys
import getopt
import gtk
import gobject
import gps

markup_str = '<span size="92000" weight="bold">%d</span>'

class App:
    def __init__(self, gps):
        self.gps = gps

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_border_width(3)
        self.window.connect('destroy', gtk.main_quit)

        vbox = gtk.VBox(False, 5)
        self.window.add(vbox)

        self.label = gtk.Label('')
        vbox.pack_start(self.label, True, False, 0)

        gobject.timeout_add(1000, self.timeout)

        self.window.show_all()

    def timeout(self):
        try:
            self.gps.query('g\n')
        except socket.error:
            md = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                type=gtk.MESSAGE_ERROR,
                message_format='Lost connection to gpsd server')
            md.run()
            gtk.main_quit()
            return True

        self.label.set_markup(markup_str % self.gps.borgelt.air_speed)
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
