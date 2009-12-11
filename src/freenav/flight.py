import collections
import datetime
import math

import flight_sm
import freedb
import projection

KTS_TO_MPS = 1852.0 / 3600

class Flight:
    def __init__(self):
        self._fsm = flight_sm.Flight_sm(self)
        #self._fsm.setDebugFlag(True)

        self.subscriber_list = set()

        self.db = freedb.Freedb()
        p = self.db.get_projection()
        self.projection = projection.Lambert(
                p['Parallel1'], p['Parallel2'], p['Latitude'], p['Longitude'])

        # Initialise task and turnpoint list
        self.task = self.db.get_task()
        self.reset_tp_list()

        self.task_state = ''

        self.x = 0
        self.y = 0
        self.altitude = 0
        self.secs = 0
        self.ground_speed = 0
        self.track = 0

        # Altimetry related stuff
        self.pressure_level = None
        self.pressure_level_datum = None
        self.pressure_level_deque = collections.deque()
        self.airfield_altitude = None

        # Get QNE value - use None if it wasn't set today
        config = self.db.get_config()
        qne_date = datetime.date.fromtimestamp(config['QNE_Timestamp'])
        if (qne_date == datetime.date.today()):
            self.qne = config['qne']
        else:
            self.qne = None

        self._fsm.enterStartState()

    #------------------------------------------------------------------------
    # Model control methods

    def subscribe(self, subscriber):
        """Add a subscriber"""
        self.subscriber_list.add(subscriber)

    def update_position(self, secs, latitude, longitude, altitude,
                        ground_speed, track):
        "Update model with new position data"""
        self.secs = secs
        x, y = self.projection.forward(latitude, longitude)
        self.x = int(x)
        self.y = int(y)
        self.altitude = altitude
        self.track = track
        self.ground_speed = ground_speed

        self._fsm.new_position()
        self.notify_subscribers()

    def update_vario(self, maccready, bugs, ballast):
        """Update model with new vario parameters"""
        self.maccready = maccready
        self.bugs = bugs
        self.ballast = ballast

    def update_pressure_level(self, level):
        """Update model with new pressure level data"""
        self.pressure_level = level
        self._fsm.new_pressure_level(level)

    def divert(self, waypoint_id):
        """Divert to specified waypoint"""
        self._fsm.divert(waypoint_id)

    def cancel_divert(self):
        """Cancel divert (and return to task)"""
        self._fsm.cancel_divert()

    def trigger_start(self):
        """Start, or re-start, the task"""
        self._fsm.start_trigger()

    def next_turnpoint(self):
        """Goto next turnpoing"""
        self._fsm.next_turnpoint()

    #------------------------------------------------------------------------
    # Pass through function to database

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

    def get_secs(self):
        """Return GPS time, in seconds"""
        return self.secs

    def get_pressure_height(self):
        """Return height above airfield"""
        if self.pressure_level is None or self.pressure_level_datum is None:
            height = None
        else:
            height = self.pressure_level - self.pressure_level_datum
        return height

    def get_pressure_altitude(self):
        """Return height above sea level"""
        height = self.get_pressure_height()
        if height is None or self.airfield_altitude is None:
            altitude = None
        else:
            altitude = height + self.airfield_altitude
        return altitude

    def get_flight_level(self):
        """Return (QNE corrected) flight level"""
        if self.pressure_level is None:
            level = None
        else:
            level = self.pressure_level
            if not (self.qne is None or self.pressure_level_datum is None):
                level = level - self.pressure_level_datum + self.qne
        return level

    def get_position(self):
        """Return X, Y position"""
        return (self.x, self.y)

    def get_nav(self):
        """Return navigation (to current WP) data"""
        dx = self.tp_list[0]['x'] - self.x
        dy = self.tp_list[0]['y'] - self.y
        distance = math.sqrt(dx * dx + dy * dy)
        bearing = math.atan2(dx, dy)
        relative_bearing = (bearing - self.track) % (2 * math.pi)

        return {'id': self.tp_list[0]['id'],
                'distance': distance,
                'bearing': bearing,
                'relative_bearing': relative_bearing}

    def get_glide(self):
        """Return final glide parameters"""
        return {'margin': 1,
                'height': 100,
                'ete': 305,
                'maccready': 1}

    def get_velocity(self):
        """Return ground speed and track"""
        return {'speed': self.ground_speed, 'track': self.track}

    def get_wind(self):
        """Return wind speed and direction"""
        return {'speed': 5, 'direction': math.pi * 1.5}

    def get_task_state(self):
        """Return task state"""
        return self.task_state

    #------------------------------------------------------------------------
    # State machine methods

    def init_ground(self):
        """Get and store airfield altitude"""
        wps = self.db.get_nearest_landable(self.x, self.y)
        self.airfield_altitude = wps[0]['altitude']

    def do_update_pressure_level(self, level):
        """Record pressure level datum"""
        self.pressure_level_deque.append(level)

        # Calculate average over 60 samples
        if len(self.pressure_level_deque) > 60:
            self.set_pressure_level_datum()

    def do_takeoff(self):
        """Leaving the ground"""
        if self.pressure_level_datum is None and self.pressure_level_deque:
            # In case we haven't had time to accumulate a full sample
            self.set_pressure_level_datum()

    def set_task(self, task_state):
        self.task_state = task_state

    def make_start(self):
        """Start task"""
        self.tp_list.pop(0)
        self.notify_subscribers()

    def do_save_task(self):
        """Save current task list"""
        self.divert_tp_list = self.tp_list

    def do_divert(self, waypoint_id):
        """Divert to specified waypoint"""
        self.set_task("divert")
        self.tp_list = [self.db.get_waypoint(waypoint_id)]
        self.notify_subscribers()

    def do_cancel_divert(self):
        """Cancel waypoint diversion and return to saved task"""
        self.tp_list = self.divert_tp_list
        self.notify_subscribers()

    def do_next_turnpoint(self):
        """Goto next turnpoint (wrapping at end of list)"""
        self.tp_list.pop(0)
        if len(self.tp_list) == 0:
            self.tp_list = self.task[1:]
        self.notify_subscribers()

    def is_previous_start(self):
        """Return true if a start has already been made"""
        return False

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

    def set_pressure_level_datum(self):
        """Update datum and store to database"""
        self.pressure_level_datum = (sum(self.pressure_level_deque) /
                                     len(self.pressure_level_deque))
        self.pressure_level_deque.clear()

        self.db.set_pressure_level_datum(self.pressure_level_datum, self.secs)

    def reset_tp_list(self):
        """Reset the task turnpoint list"""
        self.tp_list = self.task[:]
        self.notify_subscribers()

if __name__ == '__main__':
    f = Flight()
    f.force_start()
