"""This model provides the controller for the freenav program"""

import collections
import ConfigParser
import logging
import time

import gobject
import gtk

try:
    import osso
    IS_HILDON_APP = True
except ImportError:
    IS_HILDON_APP = False

import freeview
import freenav
import flight
import freesound
import freenmea
import nmeaparser
import sms

OSSO_APPLICATION = "uk.org.freeflight.freenav"

KTS_TO_MPS = 1852 / 3600.0
KPH_TO_MPS = 1000 / 3600.0
FT_TO_M = 0.3048

DIVERT_TIMEOUT = 5000
INFO_TIMEOUT = 3000

INFO_LEVEL = 0
INFO_TASK = 1
INFO_TIME = 2

MENU_LABELS = ["Log", "Mute"] + [""] * (freeview.MATRIX_SIZE - 3) + ["Quit"]

class FreeControl:
    """Controller class for freenav program"""
    def __init__(self, flight_model, view, db, config):
        """Class initialisation"""
        self.logger = logging.getLogger('freelog')

        # Links to view and model
        self.view = view
        self.flight = flight_model
        self.flight.subscribe(self)
        self.config = config

        # Sounds
        self.sound = freesound.Sound()

        # SMS configuration
        if config.has_section('SMS-Device'):
            bt_addr = config.get('SMS-Device', 'Bluetooth-Address')
            self.sms = sms.Sms(bt_addr)
            items = config.items('SMS-Names')
            for name, sms_id in items:
                number = config.get(sms_id, 'Number')
                try:
                    email = config.get(sms_id, 'Email')
                except ConfigParser.NoOptionError:
                    email = None
                self.sms.add_phonebook_entry(name, number, email)
        else:
            self.sms = None

        # FLARM audio control
        self.flarm_mute = False

        # FLARM radar display control
        self.flarm_display = False
        self.flarm_detections = {}

        # Controller state variables
        self.divert_indicator_flag = False
        self.info_flag = False
        self.level_display_type = collections.deque(["flight_level",
                                                     "height",
                                                     "altitude",
                                                     "thermal_average"])
        self.task_display_type = collections.deque(["start_time",
                                                    "task_speed",
                                                    "task_time",
                                                    "thermal_average"])
        # Get GPS device
        dev_name = config.get('Device-Names', db.get_settings()['gps_device'])
        dev = config.get(dev_name, 'Device')
        if config.has_option(dev_name, 'Baud'):
            baud_rate = config.getint(dev_name, 'Baud')
        else:
            baud_rate = None

        # Open NMEA device and connect signals
        self.nmea_parser = nmeaparser.NmeaParser()
        self.nmea_dev = freenmea.FreeNmea(self.nmea_parser)
        self.nmea_dev.open(dev, baud_rate)
        self.nmea_dev.connect('new-position', self.position_changed)
        self.nmea_dev.connect('new-pressure', self.pressure_level_changed)
        self.nmea_dev.connect('flarm-alarm', self.flarm_alarm)

        # Handle user interface events
        view.drawing_area.connect('button_press_event', self.button_press)
        view.drawing_area.connect('button_release_event', self.button_release)
        view.window.connect('key_press_event', self.key_press)
        view.window.connect('destroy', self.destroy)
        for i, ibox in enumerate(view.info_box):
            ibox.connect("button_press_event", self.info_button_press, i)
        view.window.connect('window-state-event', self.on_window_state_change)

        if IS_HILDON_APP:
            # Add timeout callback to keep the N810 display on. Need to make
            # osso_c object variable otherwise program core dumps"""
            self.osso_c = osso.Context(OSSO_APPLICATION, freenav.__version__,
                                       False)
            self.osso_device = osso.DeviceState(self.osso_c)
            gobject.timeout_add(25000, self.blank_timeout)

        self.window_in_fullscreen = False

    def blank_timeout(self):
        """Stop the N810 display from blanking"""
        self.osso_device.display_blanking_pause()
        return True

    def destroy(self, _widget):
        """Stop input devices and quit"""
        self.nmea_dev.close()
        gtk.main_quit()

    def on_window_state_change(self, _widget, event, *_args):
        """Callback on window state change"""
        if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            self.window_in_fullscreen = True
        else:
            self.window_in_fullscreen = False

    def info_button_press(self, _widget, event, info):
        """Handle button press in info box"""
        if event.type != gtk.gdk.BUTTON_PRESS:
            # Ignore double press
            return False

        if info == INFO_LEVEL:
            self.level_button_press()
        elif info == INFO_TASK:
            self.task_button_press()
        elif info == INFO_TIME:
            self.time_button_press()

        return True

    def button_press(self, _widget, event):
        if event.type != gtk.gdk.BUTTON_PRESS:
            # Ignore double press
            return False

        self.button_press_x = event.x
        self.button_press_y = event.y

    def button_release(self, _widget, event):
        """Handle button press (mouse click/screen touch)"""
        x, y = self.view.win_to_view(event.x, event.y)
        mode, region_val = self.view.get_button_region(event.x, event.y)

        if mode == 'matrix':
            if region_val != None:
                if self.matrix_mode == 'maccready':
                    self.flight.update_maccready(region_val * KTS_TO_MPS)
                elif self.matrix_mode == 'zoom':
                    self.view.set_zoom(region_val)
                elif self.matrix_mode == 'menu':
                    if MENU_LABELS[region_val] == "Log":
                        self.view.track_log = not self.view.track_log
                    elif MENU_LABELS[region_val] == "Mute":
                        self.flarm_mute = not self.flarm_mute
                        self.view.set_mute_indicator(self.flarm_mute)
                    elif MENU_LABELS[region_val] == "Quit":
                        response = self.view.confirm_dialog("Quit?")
                        if response != gtk.RESPONSE_NO:
                            self.view.window.destroy()


            self.view.cancel_matrix()

        else:
            if self.divert_indicator_flag:
                self.divert(x, y)

            elif self.info_flag:
                self.show_info(x, y)

            elif region_val == 'divert':
                if self.flight.get_state() in ('Task', 'Divert'):
                    self.start_divert()
                    self.view.redraw()

            elif region_val == 'next':
                self.flight.next_turnpoint()
                self.view.redraw()

            elif region_val == 'prev':
                self.flight.prev_turnpoint()
                self.view.redraw()

            elif region_val == 'flarm':
                self.toggle_flarm()
                self.view.redraw()

            elif region_val == 'zoom':
                self.matrix_mode = 'zoom'
                ind = freeview.SCALE.index(self.view.view_scale)
                selected = [n==ind for n in range(len(freeview.ZOOM_LABELS))]
                self.view.set_matrix(freeview.ZOOM_LABELS, selected)

            elif region_val == 'glide':
                self.matrix_mode = 'maccready'
                maccready = (self.flight.task.get_glide()['maccready'] /
                             KTS_TO_MPS)

                labels = [str(x) for x in range(9)]
                selected = [maccready==int(m) for m in labels]
                self.view.set_matrix(labels, selected)

            elif region_val == 'menu':
                self.matrix_mode = 'menu'
                selected = [False] * freeview.MATRIX_SIZE
                selected[MENU_LABELS.index("Log")] = self.view.track_log
                selected[MENU_LABELS.index("Mute")] = self.flarm_mute
                self.view.set_matrix(MENU_LABELS, selected)

            elif region_val == 'zoom_in':
                self.view.zoom_in()
                self.view.redraw()

            elif region_val == 'zoom_out':
                self.view.zoom_out()
                self.view.redraw()

            else:
                self.start_info()
                self.view.redraw()

        return True

    def key_press(self, _widget, event, *_args):
        """Handle key(board) press"""
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname in ('q', 'Q'):
            self.view.window.destroy()

        elif keyname in ('Up', 'F7'):
            # F7 is N810 'Zoom in' key
            self.view.zoom_in()
            self.view.redraw()

        elif keyname in ('Down', 'F8'):
            # F8 is N810 'Zoom out' key
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

    def position_changed(self, _source, nmea):
        """Callback for new GPS position"""
        # Remove old flarm traffic
        for f in nmea.flarm_traffic.keys():
            if (nmea.time - nmea.flarm_traffic[f].time) > 5:
                del nmea.flarm_traffic[f]
        self.flight.flarm_traffic = nmea.flarm_traffic

        # Update model with new position
        self.flight.update_position(nmea.time, nmea.latitude, nmea.longitude,
                                    nmea.gps_altitude, nmea.speed, nmea.track,
                                    nmea.num_satellites, nmea.fix_quality)

    def pressure_level_changed(self, _source, nmea):
        """Callback for new pressure altitude"""
        self.flight.update_pressure_level(nmea.pressure_alt)

    def flarm_alarm(self, _source, nmea):
        """Callback for FLARM alarm"""
        if self.flarm_mute or nmea.flarm_alarm_type < 2:
            # Ignore traffic and silent aircraft alarms
            return

        bearing = nmea.flarm_relative_bearing
        if abs(bearing) < 15:
            sound = 'ahead'
        elif abs(bearing) > 150:
            sound = 'behind'
        elif bearing > 110:
            sound = 'right-back'
        elif bearing > 45:
            sound = 'right'
        elif bearing > 0:
            sound = 'right-front'
        elif bearing < -110:
            sound = 'left-back'
        elif bearing < -45:
            sound = 'left'
        else:
            sound = 'left-front'

        self.sound.play(sound)

    def flight_update(self, event):
        """Callback on flight model change"""
        if event == flight.LINE_EVT:
            # Crossing line, play sound and reset task info
            self.sound.play('line')
            while self.task_display_type[0] != "start_time":
                self.task_display_type.rotate()

        if event == flight.START_SECTOR_EVT or event == flight.SECTOR_EVT:
            # Enter sector, play sound
            self.sound.play('sector')

        self.display_task_info()

        if event != flight.INIT_POSITION_EVT:
            # Update display
            self.display_level_info()
            self.display_time_info(self.flight.get_utc_secs())
            self.view.update_position(*self.flight.get_position())

        if event == flight.LAND_EVT:
            # Send SMS position messages
            if self.sms:
                self.sound.play("sms-beep")
                response = self.view.confirm_dialog("Send SMS?", "SMS")
                if response != gtk.RESPONSE_NO:
                    self.send_sms()

    #------------------------------------------------------------------

    def level_button_press(self):
        """Button press in the level info box. Change between level displays"""
        self.level_display_type.rotate(-1)
        self.display_level_info()

    def time_button_press(self):
        """Button press in the time info box. Start the task"""
        task_state = self.flight.get_state()
        if task_state == "Launch":
            self.flight.trigger_start()

        elif task_state in ("Start", "Sector", "Task"):
            stat = self.view.confirm_dialog("Start?", "Task")
            if stat == gtk.RESPONSE_YES:
                self.flight.trigger_start()

    def task_button_press(self):
        """Button press in the task info box"""
        if self.flight.get_state() == "Task":
            self.task_display_type.rotate(-1)
            self.display_task_info()
        else:
            self.flight.cancel_divert()

    def display_level_info(self):
        """Update pressure level info label"""
        if self.level_display_type[0] == 'height':
            # Display height above takeoff point
            height = self.flight.pressure_alt.get_pressure_height()
            if height is None:
                info = '****G'
            else:
                info = "%03dG" % (height / FT_TO_M)

        elif self.level_display_type[0] == 'altitude':
            # Display altitude
            altitude = self.flight.pressure_alt.get_pressure_altitude()
            if altitude is None:
                info = "%03d*" % (self.flight.altitude / FT_TO_M)
            else:
                info = "%03d" % (altitude / FT_TO_M)

        elif self.level_display_type[0] == 'flight_level':
            # Display flight level
            flight_level = self.flight.pressure_alt.get_flight_level()
            if flight_level is None:
                info = 'FL**'
            elif flight_level < 0:
                info = 'FL<0'
            else:
                info = 'FL%02d' % round((flight_level / FT_TO_M) / 100)
        else:
            # Display total thermal average
            info = "%.1f" % (self.flight.thermal.thermal_average / KTS_TO_MPS)

        self.view.info_label[INFO_LEVEL].set_text(info)

    def display_task_info(self):
        """Update task info label"""
        task_state = self.flight.get_state()
        if task_state == "Task":
            display_type = self.task_display_type[0]
            if display_type == "start_time":
                # Start time
                info_str = time.strftime(
                    "%H:%M", time.localtime(self.flight.task.start_time))

            elif display_type == "task_speed":
                # Task speed, limited to 999kph
                speed = self.flight.task.task_air_speed / KPH_TO_MPS
                speed = min(speed, 999)
                info_str = ("%.0f" % speed)

            elif display_type == "task_time":
                # Task time, limited to 9:59
                ete = min(self.flight.task.task_ete, 35940)
                tim_str = time.strftime("%H:%M", time.gmtime(ete))
                info_str = tim_str[1:]
            else:
                # Total thermal average
                info_str = "%.1f" % (self.flight.thermal.thermal_average /
                                     KTS_TO_MPS)
        elif task_state == "Init":
            # Initialisation countdown
            info_str = "Init-%d" % self.flight.init_count

        else:
            # State name
            info_str = flight.SHORT_NAMES[task_state]

        self.view.info_label[INFO_TASK].set_text(info_str)

    def display_time_info(self, secs):
        """Update time info label"""
        tim = time.strftime("%H:%M", time.localtime(secs))
        self.view.info_label[INFO_TIME].set_text(tim)

    def divert(self, x, y):
        """Divert to landable field"""
        self.reset_divert()
        gobject.source_remove(self.divert_timeout_id)

        landables = self.flight.db.get_nearest_landables(x, y)
        self.flight.divert(landables[0])

    def start_divert(self):
        """Set divert indicator and start timeout"""
        self.divert_indicator_flag = True
        self.view.set_divert_indicator(True)
        self.divert_timeout_id = gobject.timeout_add(DIVERT_TIMEOUT,
                                                     self.reset_divert)

    def reset_divert(self):
        """Reset divert indicator"""
        self.divert_indicator_flag = False
        self.view.set_divert_indicator(False)
        return False

    def show_info(self, x, y):
        """Show info at given position"""
        self.reset_info()
        gobject.source_remove(self.info_timeout_id)

        self.display_airspace(x, y)

    def start_info(self):
        """Set info indicator and start timeout"""
        self.info_flag = True
        self.view.set_info_indicator(True)
        self.info_timeout_id = gobject.timeout_add(INFO_TIMEOUT,
                                                   self.reset_info)

    def reset_info(self):
        """Reset info indicator"""
        self.info_flag = False
        self.view.set_info_indicator(False)
        return False

    def toggle_mute(self):
        """Toggle the FLARM mute"""
        self.flarm_mute = not self.flarm_mute
        self.view.set_mute_indicator(self.flarm_mute)

    def toggle_flarm(self):
        """Toggle FLARM radar display"""
        flarm_radar = not self.view.flarm_radar_flag
        self.view.set_flarm_radar(flarm_radar)

    def display_airspace(self, x, y):
        """Display airspace info"""
        info = self.view.mapcache.get_airspace_info(x, y)
        self.view.show_airspace_info(info)

    def send_sms(self):
        """Send Lat/Lon landing report via SMS"""
        tim = self.flight.utc_secs
        lat, lon = self.flight.get_latlon()

        # Create SMS message body
        tim_str = time.strftime("%H:%M", time.localtime(tim))
        lat_str = "%(deg)02d %(min)02d.%(dec)03d%(ns)s" % \
                freenav.util.dmm(lat, 3)
        lon_str = "%(deg)03d %(min)02d.%(dec)03d%(ew)s" % \
                freenav.util.dmm(lon, 3)
        msg = "LANDED %s %s %s" % (tim_str, lat_str, lon_str)

        self.sms.send_all(msg)

    def main(self):
        """Main program entry"""
        gtk.main()
