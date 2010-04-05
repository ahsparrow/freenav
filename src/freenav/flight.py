import datetime
import math

import altimetry
import flight_sm
import freedb
import projection
import task
import thermal

KTS_TO_MPS = 1852.0 / 3600

class Flight:
    TAKEOFF_SPEED = 10
    STOPPED_SPEED = 2

    def __init__(self, polar, safety_height):
        self._fsm = flight_sm.Flight_sm(self)

        self.db = freedb.Freedb()
        self.task = task.Task(self.db.get_task(), polar, safety_height)
        self.pressure_alt = altimetry.PressureAltimetry()
        self.thermal_calculator = thermal.ThermalCalculator()

        # Get projection from database
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
        self.num_satellites = 0

        # TP navigation
        self.tp_distance = 0
        self.tp_bearing = 0

        # List of model observers
        self.subscriber_list = set()

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
                        ground_speed, track, num_satellites):
        "Update model with new position data"""
        self.utc_secs = utc_secs
        x, y = [int(p) for p in self.projection.forward(latitude, longitude)]
        self.x, self.y = x, y
        self.altitude = altitude
        self.track = track
        self.ground_speed = ground_speed
        self.num_satellites = num_satellites

        self._fsm.new_position()

    def update_maccready(self, maccready, bugs, ballast):
        """Update model with new Maccready parameters"""
        self.task.set_maccready(maccready, bugs, ballast)

    def update_pressure_level(self, level):
        """Update model with new pressure level data"""
        self.pressure_alt.set_pressure_level(level)

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
    # Model query methods

    def get_utc_secs(self):
        """Return GPS time, in seconds"""
        return self.utc_secs

    def get_position(self):
        """Return X, Y position"""
        return (self.x, self.y)

    def get_nav(self):
        """Return navigation (to current TP) data"""
        return {'id': self.task.get_tp_id(),
                'distance': self.tp_distance,
                'bearing': self.tp_bearing}

    def get_velocity(self):
        """Return ground speed and track"""
        return {'speed': self.ground_speed, 'track': self.track}

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

    def get_num_satellites(self):
        """Return number of satellites in view"""
        return self.num_satellites

    #------------------------------------------------------------------------
    # State machine methods

    def do_init(self):
        """Initialisation"""
        self.task.reset()

        # Get QNE value - use None if it wasn't set today
        config = self.db.get_config()
        qne_date = datetime.date.fromtimestamp(config['qne_timestamp'])

        if (qne_date == datetime.date.today()):
            qne = config['qne']
        else:
            qne = None
        self.pressure_alt.set_qne(qne)

    def do_init_ground(self):
        """Get and store airfield altitude"""
        wps = self.db.get_nearest_landable(self.x, self.y)
        self.pressure_alt.set_takeoff_altitude(wps[0]['altitude'])

        # Temporary divert to takeoff WP
        self.task.divert(wps[0])

        self.notify_subscribers()

    def do_init_air(self):
        """In-air initialisation"""
        config = self.db.get_config()

        takeoff_date = datetime.date.fromtimestamp(config["takeoff_time"])
        if (takeoff_date == datetime.date.today()):
            self.pressure_alt.set_takeoff_pressure_level(
                                            config["takeoff_pressure_level"])
            self.pressure_alt.set_takeoff_altitude(config["takeoff_altitude"])

        self.notify_subscribers()

    def do_resume(self):
        """Resume task after program re-start in air"""
        config = self.db.get_config()
        self.task.start(config["start_time"])

        self.notify_subscribers()

    def do_update_position(self, notify=False):
        """Update model with new position data"""
        self.thermal_calculator.update(self.x, self.y, self.altitude,
                                       self.utc_secs)
        self.calc_nav()
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())

        if notify:
            self.notify_subscribers()

    def do_ground_pressure_level(self, level):
        """Average takeoff pressure level"""
        self.pressure_alt.update_ground_pressure_level(level)

    def do_takeoff(self):
        """Leaving the ground"""
        self.pressure_alt.takeoff()

        # Store takeoff info to database
        self.db.set_takeoff(self.utc_secs,
                            self.pressure_alt.takeoff_pressure_level,
                            self.pressure_alt.takeoff_altitude)
        self.db.commit()

        self.notify_subscribers()

    def do_launch(self):
        """Off the ground"""
        self.notify_subscribers()

    def do_start(self):
        """Begin start"""
        self.task.reset()
        self.notify_subscribers()

    def do_start_sector(self):
        """Entered start sector"""
        self.notify_subscribers()

    def do_line(self):
        """Crossing line - start task"""
        self.task.start(self.utc_secs)

        self.db.set_start(self.utc_secs)
        self.db.commit()

        for s in self.subscriber_list:
            s.flight_task_start(self)

    def do_task(self):
        """Update task"""
        self.calc_nav()
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())
        self.notify_subscribers()

    def do_set_divert(self, waypoint_id):
        """Set divert to specified waypoint"""
        divert_wp = self.db.get_waypoint(waypoint_id)
        self.task.divert(divert_wp)

    def do_divert(self):
        """Start a new diversion"""
        self.calc_nav()
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())
        self.notify_subscribers()

    def do_cancel_divert(self):
        """Cancel waypoint diversion and return to saved task"""
        self.task.cancel_divert()

    def do_next_turnpoint(self):
        """Goto next turnpoint"""
        self.task.next_turnpoint()

    def do_prev_turnpoint(self):
        """Goto previous turnpoint"""
        self.task.prev_turnpoint()

    def is_previous_start(self):
        """Return true if a start has already been made today"""
        config = self.db.get_config()

        start_date = datetime.date.fromtimestamp(config["start_time"])
        return (start_date == datetime.date.today())

    def in_start_sector(self):
        return self.task.in_start_sector(self.x, self.y)

    #------------------------------------------------------------------------
    # Internal stuff

    def notify_subscribers(self):
        """Send an update to all the subscribers"""
        for s in self.subscriber_list:
            s.flight_update(self)

    def calc_nav(self):
        """Calculate TP distance and bearing"""
        tp = self.task.get_tp_xy()
        dx = tp[0] - self.x
        dy = tp[1] - self.y
        self.tp_distance = math.sqrt(dx * dx + dy * dy)
        self.tp_bearing = math.atan2(dx, dy)

if __name__ == '__main__':
    f = Flight()
    f.force_start()
