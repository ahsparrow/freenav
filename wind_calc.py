import collections
import math
import time

MAX_CIRCLE_TIME = 35
MAX_DRIFT_TIME = 90

class WindCalc:
    def __init__(self):
        self.vector_store = collections.deque()
        self.vector_store.append({'x': 0, 'y': 0, 'dx': 0, 'dy': 0, 'mag': 0,
                                  'turn_angle': 0, 'tim': 0})

        self.drift_store = collections.deque()

        self.turn_direction = 0
        self.turn_angle_acc = 0

        self.wind_speed = 0
        self.wind_direction = 0

    def restart_turn_search(self, turn_direction, new_vec):
        """Restart search by clearing deques and resetting accumulators"""
        self.drift_store.clear()
        self.vector_store.clear()

        self.vector_store.append(new_vec)
        self.turn_direction = turn_direction
        self.turn_angle_acc = 0

    def drop_old_vectors(self, tim):
        """Drop old data from vector_store. Return True if data dropped"""
        if len(self.vector_store) == 0:
            return False

        if (tim - self.vector_store[0]['tim']) > MAX_CIRCLE_TIME:
            p = self.vector_store.popleft()
            self.turn_angle_acc -= p['turn_angle']

            self.drop_old_vectors(tim)
            return True
        else:
            return False

    def drop_old_drifts(self, tim):
        """Drop old data from drift store"""
        if len(self.drift_store) > 0:
            if (tim - self.drift_store[0]['tim']) > MAX_DRIFT_TIME:
                self.drift_store.popleft()
                self.drop_old_drifts(tim)

    def wind_calc(self, x, y, t):
        """Calculated wind speed and direction"""
        # Discard any old drift measurements and add the new one
        self.drop_old_drifts(t)
        self.drift_store.append({'x': x, 'y': y, 'tim': t})

        # If we have two or more drift measurements then update the wind calc
        if len(self.drift_store) > 1:
            d = self.drift_store[0]
            dx = x - d['x']
            dy = y - d['y']
            dt = t - d['tim']
            self.wind_speed = math.sqrt(dx ** 2 + dy ** 2) / dt
            self.wind_direction = math.atan2(dx, dy)

    def drift_calc(self, new_vec):
        """Update drift calculation with new vector"""
        # If we need to drop old vectors then restart wind calculation
        if self.drop_old_vectors(new_vec['tim']):
            self.drift_store.clear()

        self.vector_store.append(new_vec)
        self.turn_angle_acc += new_vec['turn_angle']

        # If we've accumated 360 degrees of turn then update wind calculation
        if self.turn_angle_acc > (2 * math.pi):
            xacc = yacc = tacc = 0
            for v in self.vector_store:
                xacc += v['x']
                yacc += v['y']
                tacc += v['tim']

            vlen = len(self.vector_store)
            xavg = xacc / vlen
            yavg = yacc / vlen
            tavg = tacc / vlen

            self.wind_calc(xavg, yavg, tavg)

            # Re-initialise vector store and angle accumulator
            self.vector_store.clear()
            self.vector_store.append(new_vec)
            self.turn_angle_acc = 0

    def update(self, x, y, utc):
        """Main update function"""
        x = float(x)
        y = float(y)

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

        tim = time.mktime(utc)
        new_vec = {'x': x , 'y': y, 'dx': dx, 'dy': dy, 'mag': mag,
                   'turn_angle': turn_angle, 'tim': tim}

        # If turn direction has changed then restart search
        if turn_direction != self.turn_direction:
            self.restart_turn_search(turn_direction, new_vec)
        else:
            self.drift_calc(new_vec)
