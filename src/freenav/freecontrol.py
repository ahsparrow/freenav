import ConfigParser
import collections
import math
import os.path
import time

import dbus, dbus.mainloop.glib
import gtk

DBUS_SERVICE = "org.freedesktop.Gypsy"
DBUS_PATH = "/org/freedesktop/Gypsy"

CONTROL_INTERFACE = "org.freedesktop.Gypsy.Server"
DEVICE_INTERFACE = "org.freedesktop.Gypsy.Device"
COURSE_INTERFACE = "org.freedesktop.Gypsy.Course"

KTS_TO_MPS = 1852 / 3600.0
FT_TO_M = 0.3048

POSITION_ALL_VALID = 0x7
COURSE_SPEED_TRACK_VALID = 0x3

INFO_LEVEL = 0

class FreeControl:
    def __init__(self, flight, view):
        self.view = view
        self.flight = flight
        self.flight.subscribe(self)

        self.level_display_type = 'flight_level'

        config = ConfigParser.ConfigParser()
        config.read(os.path.join(os.path.expanduser('~'), '.freeflight',
                                 'freenav.ini'))

        # Set-up all the D-Bus stuff
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        bus = dbus.SystemBus()
        control = bus.get_object(DBUS_SERVICE, DBUS_PATH)

        gps_dev = config.get('Devices', 'gps')
        path = control.Create(gps_dev, dbus_interface=CONTROL_INTERFACE)
        gps = bus.get_object(DBUS_SERVICE, path)
        gps.connect_to_signal("PositionChanged", self.position_changed)
        gps.connect_to_signal("PressureLevelChanged", self.level_changed)

        self.course = dbus.Interface(gps, dbus_interface=COURSE_INTERFACE)

        device = dbus.Interface(gps, dbus_interface=DEVICE_INTERFACE)
        device.Start()

        # Handle user interface events
        view.drawing_area.connect('button_press_event', self.button_press)
        view.window.connect('key_press_event', self.key_press)
        view.window.connect('destroy', gtk.main_quit)
        for i, ibox in enumerate(view.info_box):
            ibox.connect("button_press_event", self.info_button_press, i)

    def info_button_press(self, widget, event, *args):
        """Handle button press in info box"""
        print "Info button press", args[0]
        if args[0] == INFO_LEVEL:
            self.level_button_press()
        return True

    def button_press(self, widget, event, *args):
        """Handle button press (mouse click/screen touch)"""
        print "Button press"
        return True

    def key_press(self, widget, event, *args):
        """Handle key(board) press"""
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname in ('q', 'Q'):
            gtk.main_quit()
        elif keyname == ('Up'):
            self.view.zoom_in()
            self.view.redraw()
        elif keyname == ('Down'):
            self.view.zoom_out()
            self.view.redraw()
        else:
            print "Unhandled key:",keyname

        return True

    def position_changed(self,
                         field_set, timestamp, latitude, longitude, altitude):
        """Callback from D-Bus on new GPS position"""
        secs = timestamp
        latitude = math.radians(latitude)
        longitude = math.radians(longitude)
        altitude = int(altitude)

        # Get course parameters
        field_set, timestamp, speed, track, climb = self.course.GetCourse()
        speed = speed * KTS_TO_MPS
        track = math.radians(track)

        # Update model with new position
        self.flight.update_position(secs, latitude, longitude, altitude,
                                    speed, track)

    def level_changed(self, level):
        """Callback from D-Bus on new pressure altitude"""
        self.flight.update_level(level * FT_TO_M)

    def flight_update(self, flight):
        """Callback on flight model change"""
        self.display_level()
        self.view.update_position(*flight.get_position())

    #------------------------------------------------------------------

    def level_button_press(self):
        if self.level_display_type == 'flight_level':
            self.level_display_type = 'altitude'
        elif self.level_display_type == 'altitude':
            self.level_display_type = 'height'
        else:
            self.level_display_type = 'flight_level'
        self.display_level()

    def display_level(self):
        if self.level_display_type == 'height':
            height = self.flight.get_pressure_height()
            if height is None:
                s = "****F"
            else:
                s = str(int(height / FT_TO_M)) + 'F'
        elif self.level_display_type == 'altitude':
            altitude = self.flight.get_pressure_altitude()
            if altitude is None:
                s = "****"
            else:
                s = str(int(altitude / FT_TO_M))
        else:
            fl = self.flight.get_flight_level()
            if fl is None:
                s = "FL**"
            else:
                s = "FL%02d" % round((fl / FT_TO_M) / 100)
        self.view.info_label[INFO_LEVEL].set_text(s)
        self.view.redraw()

    def main(self):
        gtk.main()
