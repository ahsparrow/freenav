import collections
import math
import time

MAX_CIRCLE_TIME = 35
MAX_DRIFT_TIME = 90
THERMAL_TIMEOUT = 60

class ThermalCalculator:
    """Calculate wind drift and total climb average whilst thermalling"""
    def __init__(self):
        self.drift_store = collections.deque()
        self.vector_store = collections.deque()
        self.vector_store.append({'x': 0, 'y': 0, 'dx': 0, 'dy': 0, 'mag': 0,
                                  'turn_angle': 0, 'tim': 0})
        self.turn_direction = 0
        self.turn_angle_acc = 0

        self.wind_speed = 0
        self.wind_direction = 0

        self.thermal_start = None
        self.thermal_average = 0

    def reset_vector_store(self, turn_direction, vec):
        """Re-initialise vector store and zero-ise angle accumulator"""
        self.vector_store.clear()
        self.turn_angle_acc = 0

        self.vector_store.append(vec)
        self.turn_direction = turn_direction

    def update_vector_store(self, vec):
        """Add new vector and drop any expired data. Return True if data was
           dropped"""
        self.vector_store.append(vec)
        self.turn_angle_acc += vec['turn_angle']

        drop = False
        while (vec['tim'] - self.vector_store[0]['tim']) > MAX_CIRCLE_TIME:
            p = self.vector_store.popleft()
            self.turn_angle_acc -= p['turn_angle']
            drop = True

        return drop

    def update_drift_store(self, drift):
        """Add new drift and drop expired data"""
        self.drift_store.append(drift)
        while (drift['tim'] - self.drift_store[0]['tim']) > MAX_DRIFT_TIME:
            self.drift_store.popleft()

    def thermal_calc(self, vec):
        """Calculate total thermal average so far"""
        self.thermal_average = ((vec['z'] - self.thermal_start['z']) /
                                (vec['tim'] - self.thermal_start['tim']))
        self.thermal_update_time = vec['tim']

    def thermal_start_stop(self, vec):
        """Test for thermal start and stop"""
        if ((self.thermal_start is None) or
            (vec['tim'] - self.thermal_update_time) > THERMAL_TIMEOUT):
            # Thermal "start" if we've turned 180 degrees
            if (self.turn_angle_acc > math.pi):
                # Find position quarter of a turn ago and call that the start
                acc = 0
                for vec in self.vector_store:
                    acc += vec['turn_angle']
                    if acc > (math.pi / 2):
                        break
                self.thermal_start = vec
                self.thermal_update_time = vec['tim']
            else:
                self.thermal_start = None

    def wind_calc(self):
        """Calculated wind speed and direction from drift values"""
        # Calculate average position/time of vector store
        xacc = yacc = tacc = 0
        for v in self.vector_store:
            xacc += v['x']
            yacc += v['y']
            tacc += v['tim']

        vlen = len(self.vector_store)
        xavg = xacc / vlen
        yavg = yacc / vlen
        tavg = tacc / vlen

        # Add new drift measurement
        self.update_drift_store({'x': xavg, 'y': yavg, 'tim': tavg})

        # If we have two or more drift measurements then update the wind calc
        if len(self.drift_store) > 1:
            d = self.drift_store[0]
            dx = xavg - d['x']
            dy = yavg - d['y']
            dt = tavg - d['tim']
            self.wind_speed = math.sqrt(dx ** 2 + dy ** 2) / dt
            self.wind_direction = math.atan2(dx, dy)

    def drift_update(self, turn_direction, vec):
        """Update the wind drift calculation with a new vector"""
        if turn_direction != self.turn_direction:
            # Turn direction has changed so restart
            self.drift_store.clear()
            self.reset_vector_store(turn_direction, vec)
            return

        # Add new vector, if we need to drop old vectors then restart drift
        # calculation
        if self.update_vector_store(vec):
            self.drift_store.clear()

        # If we've accumated 360 degrees of turn then update wind calculation
        if self.turn_angle_acc >= (2 * math.pi):
            self.wind_calc()
            self.thermal_calc(vec)
            self.reset_vector_store(turn_direction, vec)

    def update(self, x, y, z, utc_secs):
        """Main update function"""
        x = float(x)
        y = float(y)
        z = float(z)

        # Calculate vector from previous point
        v = self.vector_store[-1]
        dx = x - v['x']
        dy = y - v['y']
        mag = math.sqrt(dx * dx + dy * dy)

        # Sign of cross product between this and previous vector gives turn
        # direction
        cross_prod = (v['dx'] * dy) - (dx * v['dy'])
        if cross_prod > 0:
            turn_direction = 1
        else:
            turn_direction = -1

        # Calculate external angle between this and previous vector
        dot_prod = (v['dx'] * dx + v['dy'] * dy)
        denom = mag * v['mag']
        if denom == 0:
            turn_angle = 0
        else:
            cos_turn_angle = min(dot_prod/denom, 1.0)
            turn_angle = math.acos(cos_turn_angle)

        new_vec = {'x': x , 'y': y, 'z': z, 'dx': dx, 'dy': dy, 'mag': mag,
                   'turn_angle': turn_angle, 'tim': utc_secs}

        self.drift_update(turn_direction, new_vec)
        self.thermal_start_stop(new_vec)
