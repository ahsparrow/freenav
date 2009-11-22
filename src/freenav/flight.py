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

        self.task = self.db.get_task()
        self.reset_tp_list()

        self._fsm.enterStartState()

    def subscribe(self, subscriber):
        self.subscriber_list.add(subscriber)

    def update_subscribers(self):
        for s in self.subscriber_list:
            s.flight_update(self)

    def get_position(self):
        return (self.x, self.y)

    def get_nav(self):
        dx = self.tp_list[0]['x'] - self.x
        dy = self.tp_list[0]['y'] - self.y
        distance = math.sqrt(dx * dx + dy * dy)
        bearing = math.atan2(dx, dy)

        return {'id': self.tp_list[0]['id'],
                'distance': distance,
                'bearing': bearing}

    def update_position(self, utc, latitude, longitude, altitude,
                        ground_speed, track):
        self.utc = utc
        x, y = self.projection.forward(latitude, longitude)
        self.x = int(x)
        self.y = int(y)
        self.altitude = altitude
        self.track = track
        self.ground_speed = ground_speed

        self._fsm.new_position()
        self.update_subscribers()

    def update_vario(self, maccready, bugs, ballast):
        self.maccready = maccready
        self.bugs = bugs
        self.ballast = ballast

    def divert(self, waypoint_id):
        self._fsm.divert(waypoint_id)

    def cancel_divert(self):
        self._fsm.cancel_divert()

    def start(self):
        self._fsm.start()

    def force_start(self):
        self._fsm.force_start()

    def incr_turnpoint(self):
        self._fsm.incr_turnpoint()

    def decr_turnpoint(self):
        self._fsm.decr_turnpoint()

    #------------------------------------------------------------------------

    def do_start(self):
        self.tp_list.pop(0)
        self.update_subscribers()

    def do_divert(self, waypoint_id):
        self.divert_tp_list = self.tp_list
        self.tp_list = [db.get_waypoint(waypoint_id)]
        self.update_subscribers()

    def do_cancel_divert(self):
        self.tp_list = self.divert_tp_list
        self.update_subscribers()

    def do_incr_turnpoint(self):
        self.tp_list.pop(0)
        self.update_subscribers()

    def do_decr_turnpoint(self):
        prev_tp = self.task[-(len(self.tp_list) + 1)]
        self.tp_list.insert(0, prev_tp)
        self.update_subscribers()

    def do_arm_restart(self):
        self.reset_tp_list()
        self.update_subscribers()

    def do_force_start(self):
        self.reset_tp_list()
        self.update_subscribers()

    def is_previous_start(self):
        return False

    def in_start_sector(self):
        return False

    #------------------------------------------------------------------------

    def reset_tp_list(self):
        self.tp_list = self.task[:]

    def get_waypoint_list(self):
        return self.db.get_waypoint_list()

if __name__ == '__main__':
    f = Flight()
    f.force_start()
