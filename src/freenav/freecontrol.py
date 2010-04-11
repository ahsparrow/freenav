import collections
import math
import time

import dbus, dbus.mainloop.glib
import gobject
import gtk

try:
    import hildon
    import osso
    is_hildon_app = True
except ImportError:
    is_hildon_app = False

import freedb

OSSO_APPLICATION = "uk.org.freeflight.freenav"

DBUS_SERVICE = "org.freedesktop.Gypsy"
DBUS_PATH = "/org/freedesktop/Gypsy"

CONTROL_INTERFACE = "org.freedesktop.Gypsy.Server"
DEVICE_INTERFACE = "org.freedesktop.Gypsy.Device"
POSITION_INTERFACE = "org.freedesktop.Gypsy.Position"
COURSE_INTERFACE = "org.freedesktop.Gypsy.Course"
PRESSURE_LEVEL_INTERFACE = "org.freedesktop.Gypsy.PressureLevel"
SATELLITE_INTERFACE = "org.freedesktop.Gypsy.Satellite"

KTS_TO_MPS = 1852 / 3600.0
KPH_TO_MPS = 1000 / 3600.0
FT_TO_M = 0.3048

DIVERT_TIMEOUT = 5000
MACCREADY_TIMEOUT = 3000

MACCREADY_STEP = 0.5 * KTS_TO_MPS

INFO_LEVEL = 0
INFO_GLIDE = 1
INFO_TASK = 2
INFO_TIME = 3

class FreeControl:
    def __init__(self, flight, view, config):
        # Links to view and model
        self.view = view
        self.flight = flight
        self.flight.subscribe(self)
        db = freedb.Freedb()

        # Controller state variables
        self.divert_indicator_flag = False
        self.maccready_indicator_flag = False
        self.level_display_type = collections.deque(["flight_level",
                                                     "altitude",
                                                     "height"])
        self.task_display_type = collections.deque(["start_time",
                                                    "task_speed",
                                                    "task_time"])
        # Set-up all the D-Bus stuff
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        bus = dbus.SystemBus()
        control = bus.get_object(DBUS_SERVICE, DBUS_PATH)

        # GPS device
        gps_dev_path = config.get('Devices', db.get_config()['gps_device'])
        path = control.Create(gps_dev_path, dbus_interface=CONTROL_INTERFACE)
        gps = bus.get_object(DBUS_SERVICE, path)

        # Various interfaces
        self.gps_dev_if = dbus.Interface(gps, dbus_interface=DEVICE_INTERFACE)
        posn_if = dbus.Interface(gps, dbus_interface=POSITION_INTERFACE)
        plevel_if = dbus.Interface(gps, dbus_interface=PRESSURE_LEVEL_INTERFACE)
        self.course_if = dbus.Interface(gps, dbus_interface=COURSE_INTERFACE)
        self.satellite_if = dbus.Interface(gps,
                                           dbus_interface=SATELLITE_INTERFACE)

        # Signal handlers for position and pressure level changes
        posn_if.connect_to_signal("PositionChanged", self.position_changed)
        plevel_if.connect_to_signal("PressureLevelChanged",
                                    self.pressure_level_changed)
        # Start the GPS
        self.gps_dev_if.Start()

        # Handle user interface events
        view.drawing_area.connect('button_press_event', self.button_press)
        view.window.connect('key_press_event', self.key_press)
        view.window.connect('destroy', self.destroy)
        for i, ibox in enumerate(view.info_box):
            ibox.connect("button_press_event", self.info_button_press, i)
        view.window.connect('window-state-event', self.on_window_state_change)

        if is_hildon_app:
            """Add timeout callback to keep the N810 display on. Need to make
               osso_c object variable otherwise program core dumps"""
            self.osso_c = osso.Context(OSSO_APPLICATION, "0.0.1", False)
            self.osso_device = osso.DeviceState(self.osso_c)
            gobject.timeout_add(25000, self.blank_timeout)

    def blank_timeout(self):
        """Stop the N810 display from blanking"""
        self.osso_device.display_blanking_pause()
        return True

    def destroy(self, widget):
        """Stop input devices and quit"""
        self.gps_dev_if.Stop()
        gtk.main_quit()

    def on_window_state_change(self, widget, event, *args):
        """Callback on window state change"""
        if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            self.window_in_fullscreen = True
        else:
            self.window_in_fullscreen = False

    def info_button_press(self, widget, event, *args):
        """Handle button press in info box"""
        if event.type != gtk.gdk.BUTTON_PRESS:
            # Ignore double press
            return False

        info = args[0]
        if info == INFO_LEVEL:
            self.level_button_press()
        elif info == INFO_TASK:
            self.task_button_press()
        elif info == INFO_TIME:
            self.time_button_press()

        return True

    def button_press(self, widget, event, *args):
        """Handle button press (mouse click/screen touch)"""
        region = self.view.get_button_region(event.x, event.y)

        if region == 'turnpoint' and self.flight.get_state() != 'Divert':
            # Next/prev turnpoint
            if self.divert_indicator_flag:
                self.flight.prev_turnpoint()
                self.reset_divert()
            else:
                self.flight.next_turnpoint()
        elif self.divert_indicator_flag:
            # Divert
            self.reset_divert()
            x, y = self.view.win_to_view(event.x, event.y)
            landable = self.flight.db.get_nearest_landable(x, y)
            self.flight.divert(landable[0]['id'])
        elif region == 'divert':
            if (not self.divert_indicator_flag and
                (self.flight.get_state() in ('Task', 'Divert'))):
                # Arm divert
                self.divert_indicator_flag = True
                self.view.set_divert_indicator(True)
                self.divert_timeout_id = gobject.timeout_add(
                                            DIVERT_TIMEOUT, self.divert_timeout)
        elif region == 'glide':
            if not self.maccready_indicator_flag:
                self.maccready_indicator_flag = True
                self.view.set_maccready_indicator(True)
                self.maccready_timeout_id = gobject.timeout_add(
                                    MACCREADY_TIMEOUT, self.maccready_timeout)
        else:
            # Display airspace info
            x, y = self.view.win_to_view(event.x, event.y)
            info = self.view.mapcache.get_airspace_info(x, y)
            self.view.show_airspace_info(info)

        return True

    def key_press(self, widget, event, *args):
        """Handle key(board) press"""
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname in ('q', 'Q'):
            self.view.window.destroy()
        elif keyname in ('Up', 'F7'):
            # F7 is N810 'Zoom in' key
            if self.maccready_indicator_flag:
                self.flight.incr_maccready(MACCREADY_STEP)
                self.restart_maccready_timeout()
            else:
                self.view.zoom_in()
            self.view.redraw()
        elif keyname in ('Down', 'F8'):
            # F8 is N810 'Zoom out' key
            if self.maccready_indicator_flag:
                self.flight.decr_maccready(MACCREADY_STEP)
                self.restart_maccready_timeout()
            else:
                self.view.zoom_out()
            self.view.redraw()
        elif keyname == 'Right':
            self.flight.next_turnpoint()
        elif event.keyval == gtk.keysyms.F6:
            if self.window_in_fullscreen:
                self.view.window.unfullscreen()
            else:
                self.view.window.fullscreen()

        return True

    def position_changed(self,
                         field_set, timestamp, latitude, longitude, altitude):
        """Callback from D-Bus on new GPS position"""
        secs = timestamp
        latitude = math.radians(latitude)
        longitude = math.radians(longitude)
        altitude = int(altitude)

        # Get course parameters
        field_set, timestamp, speed, track, climb = self.course_if.GetCourse()
        speed = speed * KTS_TO_MPS
        track = math.radians(track)

        num_satellites = self.satellite_if.GetNumSatellites()

        # Update model with new position
        self.flight.update_position(secs, latitude, longitude, altitude,
                                    speed, track, num_satellites)

    def pressure_level_changed(self, level):
        """Callback from D-Bus on new pressure altitude"""
        self.flight.update_pressure_level(level * FT_TO_M)

    def flight_update(self, flight):
        """Callback on flight model change"""
        self.display_level_info()
        self.display_glide_info()
        self.display_task_info()
        self.display_time_info(flight.get_utc_secs())
        self.view.update_position(*flight.get_position())

    def flight_task_start(self, flight):
        """Call back on task start - reset task display type"""
        while self.task_display_type[0] != "start_time":
            self.task_display_type.rotate()
        self.flight_update(flight)

    #------------------------------------------------------------------

    def level_button_press(self):
        """Button press in the level info box. Change between level displays"""
        self.level_display_type.rotate()
        self.display_level_info()

    def time_button_press(self):
        """Button press in the time info box. Start the task"""
        task_state = self.flight.get_state()
        if task_state == "Launch":
            self.flight.trigger_start()

        elif task_state in ("Start", "Sector", "Task"):
            stat = self.view.task_start_dialog()
            if stat == gtk.RESPONSE_YES:
                self.flight.trigger_start()

    def task_button_press(self):
        """Button press in the task info box"""
        if self.flight.get_state() == "Task":
            # XXX self.task_display_type.rotate()
            self.display_task_info()
        else:
            self.flight.cancel_divert()

    def display_level_info(self):
        """Update pressure level info label"""
        if self.level_display_type[0] == 'height':
            height = self.flight.pressure_alt.get_pressure_height()
            if height is None:
                s = '+****'
            else:
                s = "+%03d" % (height / FT_TO_M)
        elif self.level_display_type[0] == 'altitude':
            altitude = self.flight.pressure_alt.get_pressure_altitude()
            if altitude is None:
                s = "?%03d" % (self.flight.altitude / FT_TO_M)
            else:
                s = "%03d" % (altitude / FT_TO_M)
        else:
            fl = self.flight.pressure_alt.get_flight_level()
            if fl is None:
                s = 'FL**'
            else:
                s = 'FL%02d' % round((fl / FT_TO_M) / 100)
        self.view.info_label[INFO_LEVEL].set_text(s)

    def display_glide_info(self):
        """Update glide info label"""
        s = "%0.1f" % (self.flight.thermal_calculator.thermal_average /
                       KTS_TO_MPS)
        self.view.info_label[INFO_GLIDE].set_text(s)

    def display_task_info(self):
        """Update task info label"""
        task_state = self.flight.get_state()
        if task_state == "Task":
            if self.task_display_type[0] == "start_time":
                # Start time
                info_str = time.strftime(
                    "%H:%M", time.localtime(self.flight.task.start_time))
            elif self.task_display_type[0] == "task_speed":
                # Task speed, limited to 999kph
                speed = min(self.flight.get_task_speed(), 999)
                info_str = ("%.0f" % (speed / KPH_TO_MPS))
            else:
                # Task time, limited to 9:59
                task_secs = min(self.flight.get_task_secs(), 35940)
                tim_str = time.strftime("%H:%M", time.gmtime(task_secs))
                info_str = tim_str[1:]
        else:
            info_str = task_state
        self.view.info_label[INFO_TASK].set_text(info_str)

    def display_time_info(self, secs):
        """Update time info label"""
        s = time.strftime('%H:%M', time.localtime(secs))
        self.view.info_label[INFO_TIME].set_text(s)

    def divert_timeout(self):
        self.divert_indicator_flag = False
        self.view.set_divert_indicator(False)
        return False

    def reset_divert(self):
        self.divert_indicator_flag = False
        self.view.set_divert_indicator(False)
        gobject.source_remove(self.divert_timeout_id)

    def maccready_timeout(self):
        self.maccready_indicator_flag = False
        self.view.set_maccready_indicator(False)
        return False

    def restart_maccready_timeout(self):
        gobject.source_remove(self.maccready_timeout_id)
        self.maccready_timeout_id = gobject.timeout_add(MACCREADY_TIMEOUT,
                                                        self.maccready_timeout)

    def main(self):
        gtk.main()
