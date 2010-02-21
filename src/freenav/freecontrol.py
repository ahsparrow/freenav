import collections
import math
import time

import dbus, dbus.mainloop.glib
import gobject
import gtk

DBUS_SERVICE = "org.freedesktop.Gypsy"
DBUS_PATH = "/org/freedesktop/Gypsy"

CONTROL_INTERFACE = "org.freedesktop.Gypsy.Server"
DEVICE_INTERFACE = "org.freedesktop.Gypsy.Device"
POSITION_INTERFACE = "org.freedesktop.Gypsy.Position"
COURSE_INTERFACE = "org.freedesktop.Gypsy.Course"
VARIO_INTERFACE = "org.freedesktop.Gypsy.Vario"
PRESSURE_LEVEL_INTERFACE = "org.freedesktop.Gypsy.PressureLevel"

KTS_TO_MPS = 1852 / 3600.0
KPH_TO_MPS = 1000 / 3600.0
FT_TO_M = 0.3048

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

        # Controller state variables
        self.divert_indicator_flag = False
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

        gps_dev = config.get('Devices', 'gps')
        path = control.Create(gps_dev, dbus_interface=CONTROL_INTERFACE)
        gps = bus.get_object(DBUS_SERVICE, path)

        posn_if = dbus.Interface(gps, dbus_interface=POSITION_INTERFACE)
        posn_if.connect_to_signal("PositionChanged", self.position_changed)

        plevel_if = dbus.Interface(gps, dbus_interface=PRESSURE_LEVEL_INTERFACE)
        plevel_if.connect_to_signal("PressureLevelChanged",
                                    self.pressure_level_changed)

        vario_dev = config.get('Devices', 'vario')
        path = control.Create(vario_dev, dbus_interface=CONTROL_INTERFACE)
        vario = bus.get_object(DBUS_SERVICE, path)

        vario_if = dbus.Interface(vario, dbus_interface=VARIO_INTERFACE)
        vario_if.connect_to_signal("VarioChanged", self.vario_changed)

        self.course_if = dbus.Interface(gps, dbus_interface=COURSE_INTERFACE)

        device_if = dbus.Interface(gps, dbus_interface=DEVICE_INTERFACE)
        device_if.Start()

        # Handle user interface events
        view.drawing_area.connect('button_press_event', self.button_press)
        view.window.connect('key_press_event', self.key_press)
        view.window.connect('destroy', gtk.main_quit)
        for i, ibox in enumerate(view.info_box):
            ibox.connect("button_press_event", self.info_button_press, i)

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
        win_width, win_height = widget.window.get_size()

        if (event.x < 100) and (event.y > (win_height - 100)):
            # Next/prev turnpoint
            if self.divert_indicator_flag:
                self.flight.prev_turnpoint()
                self.reset_divert()
            else:
                self.flight.next_turnpoint()
        elif (event.x < 100) and (event.y < 100):
            if (not self.divert_indicator_flag and
                (self.flight.get_state() in ('Task', 'Divert'))):
                # Arm divert
                self.divert_indicator_flag = True
                self.view.set_divert_indicator(True)
                self.divert_timeout_id = gobject.timeout_add(5000,
                                                    self.divert_timeout)
        elif self.divert_indicator_flag:
            # Divert
            self.reset_divert()
            x, y = self.view.win_to_view(event.x, event.y)
            landable = self.flight.db.get_nearest_landable(x, y)
            self.flight.divert(landable[0]['id'])
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
            gtk.main_quit()
        elif keyname == 'Up':
            self.view.zoom_in()
            self.view.redraw()
        elif keyname == 'Down':
            self.view.zoom_out()
            self.view.redraw()
        elif keyname == 'Right':
            self.flight.next_turnpoint()
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
        field_set, timestamp, speed, track, climb = self.course_if.GetCourse()
        speed = speed * KTS_TO_MPS
        track = math.radians(track)

        # Update model with new position
        self.flight.update_position(secs, latitude, longitude, altitude,
                                    speed, track)

    def pressure_level_changed(self, level):
        """Callback from D-Bus on new pressure altitude"""
        self.flight.update_pressure_level(level * FT_TO_M)

    def vario_changed(self, tas, bugs, oat, vario, maccready, ballast):
        """Callback from D-Bus on new vario settings"""
        maccready = maccready * KTS_TO_MPS
        bugs = (100 + bugs) / 100.0
        self.flight.update_maccready(maccready, bugs, ballast)

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
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO,
                                       message_format='Start task?',
                                       type=gtk.MESSAGE_QUESTION)
            ret = dialog.run()
            dialog.destroy()
            if ret == gtk.RESPONSE_YES:
                self.flight.trigger_start()

    def task_button_press(self):
        """Button press in the task info box"""
        if self.flight.get_state() == "Task":
            self.task_display_type.rotate()
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
                s = "%+d" % (height / FT_TO_M)
        elif self.level_display_type[0] == 'altitude':
            altitude = self.flight.pressure_alt.get_pressure_altitude()
            if altitude is None:
                s = '****'
            else:
                s = str(int(altitude / FT_TO_M))
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

    def main(self):
        gtk.main()
