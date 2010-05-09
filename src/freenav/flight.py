import datetime
import math

import altimetry
import flight_sm
import freedb
import projection
import task
import thermal

KTS_TO_MPS = 1852.0 / 3600

SHORT_NAMES = {'Init':   'Init',
               'Ground': 'Grnd',
               'Air':    'Air',
               'Launch': 'Lnch',
               'Resume': 'Rsme',
               'Start':  'Start',
               'Sector': 'Sect',
               'Line':   'Line',
               'Task':   'Task',
               'Divert': 'Dvrt'}

SPEED_CALC_TIME_DELTA = 30

class Event:
    (INIT_GROUND_EVT,
     INIT_AIR_EVT,
     RESUME_EVT,
     NEW_POSITION_EVT,
     TAKEOFF_EVT,
     LAUNCH_EVT,
     START_EVT,
     START_SECTOR_EVT,
     LINE_EVT,
     TASK_EVT,
     DIVERT_EVT,
     SECTOR_EVT) = range(12)

class Flight:
    TAKEOFF_SPEED = 10
    STOPPED_SPEED = 2

    def __init__(self, polar):
        self._fsm = flight_sm.Flight_sm(self)

        self.db = freedb.Freedb()
        settings = self.db.get_settings()

        self.task = task.Task(self.db.get_task(), polar, settings)
        self.pressure_alt = altimetry.PressureAltimetry()
        self.thermal = thermal.ThermalCalculator()

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

    def update_maccready(self, maccready):
        """Update model with new Maccready parameters"""
        self.task.set_maccready(maccready)

    def incr_maccready(self, incr):
        """Increment the Maccready setting"""
        self.task.incr_maccready(incr)

    def decr_maccready(self, decr):
        """Decrement the Maccready setting"""
        self.task.decr_maccready(decr)

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

    def divert(self, divert):
        """Divert to specified waypoint"""
        self._fsm.divert(divert)

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
                'distance': self.task.tp_distance,
                'bearing': self.task.tp_bearing}

    def get_velocity(self):
        """Return ground speed and track"""
        return {'speed': self.ground_speed, 'track': self.track}

    def get_wind(self):
        """Return wind speed and direction"""
        speed = self.thermal.wind_speed
        dirn = self.thermal.wind_direction
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
        settings = self.db.get_settings()
        qne_date = datetime.date.fromtimestamp(settings['qne_timestamp'])

        if (qne_date == datetime.date.today()):
            qne = settings['qne']
        else:
            qne = None
        self.pressure_alt.set_qne(qne)

    def do_init_ground(self):
        """Get and store airfield altitude"""
        landables = self.db.get_nearest_landables(self.x, self.y)
        self.pressure_alt.set_takeoff_altitude(landables[0]['altitude'])

        # Temporary divert to takeoff WP
        self.task.divert(landables[0])

        self.notify_subscribers(Event.INIT_GROUND_EVT)

    def do_init_air(self):
        """In-air initialisation"""
        settings = self.db.get_settings()

        takeoff_date = datetime.date.fromtimestamp(settings["takeoff_time"])
        if (takeoff_date == datetime.date.today()):
            self.pressure_alt.set_takeoff_pressure_level(
                                            settings["takeoff_pressure_level"])
            self.pressure_alt.set_takeoff_altitude(settings["takeoff_altitude"])

        self.notify_subscribers(Event.INIT_AIR_EVT)

    def do_resume(self):
        """Resume task after program re-start in air"""
        settings = self.db.get_settings()
        self.task.resume(settings["start_time"], self.utc_secs, self.x, self.y,
                         self.altitude)

        self.notify_subscribers(Event.RESUME_EVT)

    def do_update_position(self, notify=False):
        """Update model with new position data"""
        self.thermal.update(self.x, self.y, self.altitude,
                                       self.utc_secs)
        self.task.calc_nav(self.x, self.y)
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())

        if notify:
            self.notify_subscribers(Event.NEW_POSITION_EVT)

    def do_update_task_position(self):
        """Update task"""
        tim = self.utc_secs
        task = self.task

        self.thermal.update(self.x, self.y, self.altitude, tim)
        task.calc_nav(self.x, self.y)
        task.calc_glide(self.x, self.y, self.altitude, self.get_wind())

        if (tim - task.speed_calc_time) >= SPEED_CALC_TIME_DELTA:
            task.calc_speed(tim, self.x, self.y, self.altitude, self.get_wind())

        self.notify_subscribers(Event.NEW_POSITION_EVT)

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

        self.notify_subscribers(Event.TAKEOFF_EVT)

    def do_launch(self):
        """Off the ground"""
        self.notify_subscribers(Event.LAUNCH_EVT)

    def do_start(self):
        """Begin start"""
        self.task.reset()
        self.notify_subscribers(Event.START_EVT)

    def do_start_sector(self):
        """Entered start sector"""
        self.notify_subscribers(Event.START_SECTOR_EVT)

    def do_line(self):
        """Crossing line - start task"""
        self.task.start(self.utc_secs, self.x, self.y, self.altitude)

        self.db.set_start(self.utc_secs)
        self.db.commit()

        self.notify_subscribers(Event.LINE_EVT)

    def do_task(self):
        """Start (or re-start) task"""
        self.task.calc_nav(self.x, self.y)
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())
        self.notify_subscribers(Event.TASK_EVT)

    def do_set_divert(self, divert):
        """Set divert to specified waypoint"""
        self.task.divert(divert)

    def do_divert(self):
        """Start a new diversion"""
        self.task.calc_nav(self.x, self.y)
        self.task.calc_glide(self.x, self.y, self.altitude, self.get_wind())
        self.notify_subscribers(Event.DIVERT_EVT)

    def do_cancel_divert(self):
        """Cancel waypoint diversion and return to saved task"""
        self.task.cancel_divert()

    def do_next_turnpoint(self):
        """Goto next turnpoint"""
        self.task.next_turnpoint(self.utc_secs, self.x, self.y, self.altitude)

    def do_prev_turnpoint(self):
        """Goto previous turnpoint"""
        self.task.prev_turnpoint()

    def is_previous_start(self):
        """Return true if a start has already been made today"""
        settings = self.db.get_settings()

        start_date = datetime.date.fromtimestamp(settings["start_time"])
        return (start_date == datetime.date.today())

    def in_start_sector(self):
        return self.task.in_sector(self.x, self.y, 0)

    #------------------------------------------------------------------------
    # Internal stuff

    def notify_subscribers(self, event):
        """Send an update to all the subscribers"""
        for s in self.subscriber_list:
            s.flight_update(event)
