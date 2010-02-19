import collections
import datetime
import math

import flight_sm
import freedb
import projection
import thermal

KTS_TO_MPS = 1852.0 / 3600

class Flight:
    TAKEOFF_SPEED = 10
    STOPPED_SPEED = 2

    def __init__(self, polar, safety_height):
        self._fsm = flight_sm.Flight_sm(self)

        # Model configuration parameters
        self.ref_polar = polar
        self.update_vario(0.0, bugs=1.0, ballast=1.0)
        self.safety_height = safety_height

        # List of observers
        self.subscriber_list = set()

        # Thermal/wind calculator
        self.thermal_calculator = thermal.ThermalCalculator()

        # Projection parameters
        self.db = freedb.Freedb()
        p = self.db.get_projection()
        self.projection = projection.Lambert(
                p['parallel1'], p['parallel2'], p['latitude'], p['longitude'])

        # Position, etc
        self.x = 0
        self.y = 0
        self.altitude = 0
        self.utc_secs = 0
        self.ground_speed = 0
        self.track = 0

        # TP navigation
        self.tp_distance = 0
        self.tp_bearing = 0

        # Final glide
        self.ete = 0
        self.arrival_height = 0
        self.glide_margin = 0

        # Task
        self.start_utc_secs = 0
        self.task_secs = 0
        self.task_speed = 0

        # Altimetry
        self.takeoff_pressure_level = None
        self.takeoff_altitude = None

        self.pressure_level = None
        self.pressure_level_deque = collections.deque()

        # Initialise state machine
        self._fsm.enterStartState()

    #------------------------------------------------------------------------
    # Model control methods

    def subscribe(self, subscriber):
        """Add a subscriber"""
        self.subscriber_list.add(subscriber)

    #------------------------------------------------------------------------
    # Flight change methods

    def update_position(self, utc_secs, latitude, longitude, altitude,
                        ground_speed, track):
        "Update model with new position data"""
        self.utc_secs = utc_secs
        x, y = self.projection.forward(latitude, longitude)
        self.x = int(x)
        self.y = int(y)
        self.altitude = altitude
        self.track = track
        self.ground_speed = ground_speed

        self._fsm.new_position()

    def update_vario(self, maccready, bugs, ballast):
        """Update model with new vario parameters"""
        self.maccready = maccready
        self.bugs = bugs
        self.ballast = ballast

        # Adjust polar coefficients for ballast and bugs
        a = self.ref_polar['a'] / math.sqrt(ballast) * bugs
        b = self.ref_polar['b'] * bugs
        c = self.ref_polar['c'] * math.sqrt(ballast) * bugs

        # MacCready speed and sink rate
        self.vm = math.sqrt((c - self.maccready) / a)
        self.vm_sink_rate = -(a * self.vm ** 2 + b * self.vm + c)

    def update_pressure_level(self, level):
        """Update model with new pressure level data"""
        self.pressure_level = level

        self._fsm.new_pressure_level(level)

    #------------------------------------------------------------------------
    # Navigation change methods

    def trigger_start(self):
        """Start, or re-start, the task"""
        self._fsm.start_trigger()

    def next_turnpoint(self):
        """Goto next turnpoing"""
        self._fsm.next_turnpoint()

    def prev_turnpoint(self):
        """Goto prev turnpoing"""
        self._fsm.prev_turnpoint()

    def divert(self, waypoint_id):
        """Divert to specified waypoint"""
        self._fsm.divert(waypoint_id)

    def cancel_divert(self):
        """Cancel divert (and return to task)"""
        self._fsm.cancel_divert()

    #------------------------------------------------------------------------
    # Pass through functions to database

    def get_waypoint_list(self):
        return self.db.get_waypoint_list()

    def get_area_waypoint_list(self, x, y, width, height):
        return self.db.get_area_waypoint_list(x, y, width, height)

    def get_area_airspace(self, x, y, width, height):
        return self.db.get_area_airspace(x, y, width, height)

    def get_airspace_lines(self, id):
        return self.db.get_airspace_lines(id)

    def get_airspace_arcs(self, id):
        return self.db.get_airspace_arcs(id)

    def get_nearest_landable(self, x, y):
        return self.db.get_nearest_landable(x, y)

    #------------------------------------------------------------------------
    # Model query methods

    def get_utc_secs(self):
        """Return GPS time, in seconds"""
        return self.utc_secs

    def get_pressure_height(self):
        """Return height above takeoff airfield"""
        if self.pressure_level is None or self.takeoff_pressure_level is None:
            height = None
        else:
            height = self.pressure_level - self.takeoff_pressure_level
        return height

    def get_pressure_altitude(self):
        """Return height above sea level"""
        height = self.get_pressure_height()
        if height is None or self.takeoff_altitude is None:
            altitude = None
        else:
            altitude = height + self.takeoff_altitude
        return altitude

    def get_flight_level(self):
        """Return (QNE corrected) flight level"""
        if self.pressure_level is None:
            level = None
        else:
            level = self.pressure_level
            if not (self.qne is None or self.takeoff_pressure_level is None):
                level = level - self.takeoff_pressure_level + self.qne
        return level

    def get_position(self):
        """Return X, Y position"""
        return (self.x, self.y)

    def get_nav(self):
        """Return navigation (to current TP) data"""
        return {'id': self.task[self.tp_index]['id'],
                'distance': self.tp_distance,
                'bearing': self.tp_bearing}

    def get_glide(self):
        """Return final glide parameters"""
        return {'margin': self.glide_margin,
                'height': self.arrival_height,
                'ete': self.ete,
                'maccready': self.maccready}

    def get_velocity(self):
        """Return ground speed and track"""
        return {'speed': self.ground_speed, 'track': self.track}

    def get_start_time(self):
        """Return the start time"""
        return self.start_utc_secs

    def get_task_secs(self):
        """Return the estimated task time"""
        return self.task_secs

    def get_task_speed(self):
        """Return current task speed"""
        return self.task_speed

    def get_wind(self):
        """Return wind speed and direction"""
        speed = self.thermal_calculator.wind_speed
        dirn = self.thermal_calculator.wind_direction
        return {'speed': speed, 'direction': dirn}

    def get_state(self):
        """Return flight state"""
        if self._fsm.isInTransition():
            state = self._fsm.getPreviousState()
        else:
            state = self._fsm.getState()
        return state.getName().split('.')[-1]

    #------------------------------------------------------------------------
    # State machine methods

    def do_init(self):
        """Initialisation"""
        # Initialise task and turnpoint list
        self.reset_task()

        # Get QNE value - use None if it wasn't set today
        config = self.db.get_config()
        qne_date = datetime.date.fromtimestamp(config['qne_timestamp'])

        if (qne_date == datetime.date.today()):
            self.qne = config['qne']
        else:
            self.qne = None

    def do_init_ground(self):
        """Get and store airfield altitude"""
        wps = self.db.get_nearest_landable(self.x, self.y)
        self.takeoff_altitude = wps[0]['altitude']

        self.notify_subscribers()

    def do_init_air(self):
        """In-air initialisation"""
        config = self.db.get_config()

        takeoff_date = datetime.date.fromtimestamp(config["takeoff_time"])
        if (takeoff_date == datetime.date.today()):
            self.takeoff_pressure_level = config["takeoff_pressure_level"]
            self.takeoff_altitude = config["takeoff_altitude"]

        self.notify_subscribers()

    def do_resume(self):
        """Resume task after program re-start in air"""
        config = self.db.get_config()
        self.start_utc_secs = config["start_time"]
        self.tp_index += 1

        self.notify_subscribers()

    def do_update_position(self, notify=False):
        """Update model with new position data"""
        self.calc_nav()
        self.calc_glide()
        self.thermal_calculator.update(self.x, self.y, self.altitude,
                                       self.utc_secs)
        if notify:
            self.notify_subscribers()

    def do_update_pressure_level(self, level):
        """Average takeoff pressure level"""
        self.pressure_level_deque.append(level)

        # Calculate average over 60 samples
        if len(self.pressure_level_deque) > 60:
            self.set_takeoff_pressure_level(self.pressure_level_deque)

    def do_takeoff(self):
        """Leaving the ground"""
        if self.takeoff_pressure_level is None and self.pressure_level_deque:
            # We didn't have time to accumulate a full sample
            self.set_takeoff_pressure_level(self.pressure_level_deque)

        # Store takeoff info to database
        self.db.set_takeoff(self.takeoff_pressure_level, self.utc_secs,
                            self.takeoff_altitude)
        self.db.commit()

        self.notify_subscribers()

    def do_launch(self):
        """Off the ground"""
        self.notify_subscribers()

    def do_reset_task(self):
        """Reset TP list from task"""
        self.reset_task()
        self.notify_subscribers()

    def do_start_sector(self):
        """Entry start sector"""
        self.notify_subscribers()

    def do_line(self):
        """Crossing line - start task"""
        self.start_utc_secs = self.utc_secs
        self.tp_index += 1

        self.db.set_start(self.start_utc_secs)
        self.db.commit()

        for s in self.subscriber_list:
            s.flight_task_start(self)

    def do_task(self):
        """Update task"""
        self.calc_nav()
        self.calc_glide()
        self.notify_subscribers()

    def do_save_task(self):
        """Save current task list"""
        self.divert_task = self.task
        self.divert_tp_index = self.tp_index

    def do_set_divert(self, waypoint_id):
        """Set divert to specified waypoint"""
        divert_wp = self.db.get_waypoint(waypoint_id)
        divert_wp["mindistx"] = divert_wp["x"]
        divert_wp["mindisty"] = divert_wp["y"]
        self.task = [divert_wp]
        self.tp_index = 0

    def do_divert(self):
        """Start a new diversion"""
        self.calc_nav()
        self.calc_glide()
        self.notify_subscribers()

    def do_cancel_divert(self):
        """Cancel waypoint diversion and return to saved task"""
        self.task = self.divert_task
        self.tp_index = self.divert_tp_index

    def do_next_turnpoint(self):
        """Goto next turnpoint"""
        if self.tp_index < (len(self.task) - 1):
            self.tp_index += 1

    def do_prev_turnpoint(self):
        """Goto previous turnpoint"""
        if self.tp_index > 0:
            self.tp_index -= 1

    def is_previous_start(self):
        """Return true if a start has already been made today"""
        config = self.db.get_config()

        start_date = datetime.date.fromtimestamp(config["start_time"])
        return (start_date == datetime.date.today())

    def in_start_sector(self):
        """Return true if in start sector (2D only)"""
        start = self.task[0]

        dx = self.x - start['x']
        dy = self.y - start['y']
        dist = math.sqrt(dx ** 2 + dy ** 2)

        in_sector = False
        if dist < start['radius1']:
            ang = math.atan2(dx, dy)
            ang1 = (ang - math.radians(start['angle12'])) % (2 * math.pi)
            if (ang1 > (math.pi / 2)) and (ang1 < (3 * math.pi / 2)):
                in_sector = True

        return in_sector

    #------------------------------------------------------------------------
    # Internal stuff

    def notify_subscribers(self):
        """Send an update to all the subscribers"""
        for s in self.subscriber_list:
            s.flight_update(self)

    def set_takeoff_pressure_level(self, level_deque):
        """Update takeoff level and store to database"""
        self.takeoff_pressure_level = (sum(level_deque) / len(level_deque))
        level_deque.clear()

    def reset_task(self):
        """Reset the task turnpoint list"""
        self.task = self.db.get_task()
        self.tp_index = 0

    #------------------------------------------------------------------------
    # Calculations

    def calc_nav(self):
        """Calculate TP distance and bearing"""
        tp = self.get_tp_minxy(self.task[self.tp_index])
        dx = tp[0] - self.x
        dy = tp[1] - self.y
        self.tp_distance = math.sqrt(dx * dx + dy * dy)
        self.tp_bearing = math.atan2(dx, dy)

    def xcalc_glide(self):
        """Calculate ETE, arrival height and glide margin"""
        pass

    def xcalc_task_time(self):
        """Calculate remaining time on task"""
        pass

    def xcalc_task_glide(self):
        """Calculate glide around whole task"""
        # Get coordinates of minimum task
        coords = [get_tp_minxy(tp) for tp in self.task]

    def calc_glide(self):
        # Get coordinates of minimum remaining task
        coords = [self.get_tp_minxy(tp) for tp in self.task[self.tp_index:]]

        wind = self.get_wind()

        # Get height loss and ETE around remainder of task
        wind = self.get_wind()
        if self.vm > wind['speed']:
            height_loss, ete = self.calc_height_loss_ete((self.x, self.y),
                                                         coords, wind)
            self.ete = ete
            self.arrival_height = (self.altitude - height_loss -
                                   self.task[-1]['altitude'])
            self.glide_margin = ((self.arrival_height - self.safety_height) /
                                 height_loss)
        else:
            self.ete = 0
            self.arrival_height = 0
            self.glide_margin = 0

    def calc_height_loss_ete(self, posn, tps, wind):
        """Calculate final glide height loss and ETE"""
        if tps:
            next_tp = tps[0]
            height_loss1, ete1 = self.calc_height_loss_ete(next_tp, tps[1:],
                                                           wind)
            # Course and distance to next TP
            dx = next_tp[0] - posn[0]
            dy = next_tp[1] - posn[1]
            dist = math.sqrt(dx ** 2 + dy ** 2)
            course = math.atan2(dx, dy)

            # Get ground speed (wind direction is direction it is blowing to)
            swc = ((wind['speed'] / self.vm) *
                   math.sin(wind['direction'] - course))
            gspeed = (self.vm * math.sqrt(1 - swc ** 2) +
                      wind['speed'] * math.cos(wind['direction'] - course))

            # Height loss and ETE from this leg plus all the rest
            height_loss = dist * self.vm_sink_rate / gspeed
            ete = dist / gspeed

            height_loss += height_loss1
            ete += ete1
        else:
            height_loss = 0
            ete = 0

        return (height_loss, ete)

    #------------------------------------------------------------------------

    def get_tp_minxy(self, tp):
        if tp.has_key('mindistx'):
            xy = (tp['mindistx'], tp['mindisty'])
        else:
            xy = (tp['x'], tp['y'])
        return xy


if __name__ == '__main__':
    f = Flight()
    f.force_start()
