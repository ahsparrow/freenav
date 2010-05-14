import math

MIN_TASK_SPEED_TIME = 15 * 60
MIN_TASK_SPEED_DISTANCE = 10000

def calculate_ground_speed(air_speed, course, wind_speed, wind_direction):
    """Return ground speed given air speed, course and wind"""
    swc = wind_speed / air_speed * math.sin(wind_direction - course)

    ground_speed = (air_speed * math.sqrt(1 - swc ** 2) +
                    wind_speed * math.cos(wind_direction - course))

    return ground_speed

def calculate_air_speed(ground_speed, course, wind_speed, wind_direction):
    """Return air speed given ground speed, course and wind"""
    a2 = (wind_speed ** 2 + ground_speed ** 2 -
          2 * wind_speed * ground_speed * math.cos(course - wind_direction))
    a2 = max(a2, 0)

    return math.sqrt(a2)

class Task:
    def __init__(self, tp_list, polar, settings):
        """Class initialisation"""

        # Input data
        self.tp_list = tp_list
        self.polar = polar
        self.bugs = settings['bugs']
        self.ballast = settings['ballast']
        self.safety_height = settings['safety_height']

        self.divert_wp = None
        self.wind_speed = 0
        self.wind_direction = 0

        # Turnpoint parameters
        self.nav_tp = tp_list[0]
        self.tp_index = 0
        self.tp_distance = 0
        self.tp_bearing = 0
        self.tp_log = [None] * len(tp_list)
        self.tp_sector_flag = False

        # Set Maccready (and do initial glide calculations)
        self.set_maccready(0.0)
        self.ete = 0
        self.arrival_height = 0
        self.glide_margin = 0

        # Task speed/time values
        self.start_time = 0
        self.task_speed = 0
        self.task_air_speed = 0
        self.speed_calc_time = 0

    def reset(self):
        """Reset turnpoint index"""
        self.tp_index = 0
        self.tp_sector_flag = False
        self.divert_wp = None

    def start(self, start_time, x, y, altitude):
        """Start task"""
        self.start_time = start_time
        self.task_speed = 0
        self.task_air_speed = 0

        self.tp_index = 1
        self.tp_sector_flag = False
        self.tp_log[0] = {'x': x, 'y': y, 'alt': altitude, 'tim': start_time}

    def resume(self, start_time, resume_time, x, y, altitude):
        """Resume task after program re-start"""
        self.divert_wp = None
        self.tp_sector_flag = False

        self.start_time = start_time
        self.tp_index = 1
        self.tp_log[0] = {'x': x, 'y': y, 'alt': altitude, 'tim': resume_time}

    def next_turnpoint(self, x, y, altitude, tp_time):
        """Increment turnpoint"""
        if self.tp_index < (len(self.tp_list) - 1):
            self.tp_log[self.tp_index] = {'x': x, 'y': y, 'alt': altitude,
                                          'tim': tp_time}
            self.tp_index += 1
            self.tp_sector_flag = False

    def previous_turnpoint(self):
        """Go back a turnpoint"""
        if self.tp_index > 1:
            self.tp_index -= 1
            self.tp_sector_flag = False

    def set_divert(self, wp):
        """Set the divert waypoint"""
        self.divert_wp = wp

    def set_wind(self, wind):
        """Set a new wind vector"""
        self.wind_speed = wind['speed']
        self.wind_direction = wind['direction']

        self.calculate_turnpoint_glides()

    def set_maccready(self, maccready):
        """Set new Maccready parameters"""
        self.maccready = maccready

        # Adjust polar coefficients for ballast and bugs
        a = self.polar['a'] / math.sqrt(self.ballast) * self.bugs
        b = self.polar['b'] * self.bugs
        c = self.polar['c'] * math.sqrt(self.ballast) * self.bugs

        # MacCready speed and sink rate
        self.vm = math.sqrt((c - self.maccready) / a)
        self.vm_sink_rate = -(a * self.vm ** 2 + b * self.vm + c)

        self.calculate_turnpoint_glides()

    def increment_maccready(self, incr):
        """Increment Maccready setting"""
        self.set_maccready(self.maccready + incr)

    def decrement_maccready(self, decr):
        """Decrement Maccready setting"""
        maccready = self.maccready - decr
        if maccready < 0.1:
            maccready = 0
        self.set_maccready(maccready)

    def get_glide(self):
        """Return final glide parameters"""
        return {'margin': self.glide_margin,
                'height': self.arrival_height,
                'ete': self.ete,
                'maccready': self.maccready}

    def get_turnpoint_id(self):
        """Return ID of active TP"""
        return self.nav_tp["id"]

    def in_sector(self, x, y, tp_index = 0):
        """Return true if in sector for specified TP"""
        tp = self.tp_list[tp_index]

        dx = x - tp['x']
        dy = y - tp['y']
        dist = math.hypot(dx, dy)

        sector = False
        if (dist < tp['radius1']):
            ang = math.atan2(dx, dy)
            ang1 = (math.pi + ang - math.radians(tp['angle12'])) % (2 * math.pi)
            if ang1 > math.pi:
                ang1 = 2 * math.pi - ang1

            if dist >= tp['radius2']:
                if ang1 < (math.radians(tp['angle1']) / 2):
                    sector = True
            else:
                if ang1 < (math.radians(tp['angle2']) / 2):
                    sector = True

        return sector

    def task_position(self, x, y, altitude, tim):
        """Update position for task"""
        # First check for sector (and possibly increment TP)
        sector_entry = self.check_sector(x, y, altitude, tim)
        tp_index = self.tp_index

        # Navigation waypoint
        nav_wp = self.tp_list[tp_index]
        self.calculate_tp_nav(x, y, nav_wp) 

        # Task speed
        if tp_index:
            self.calculate_leg_speed(x, y, altitude, tim)

        # Glide waypoint
        if self.tp_sector_flag:
            tp_index = self.tp_index + 1
        glide_wp = self.tp_list[tp_index]

        self.calculate_task_glide(x, y, altitude, glide_wp,
                                  self.tp_height_loss[tp_index],
                                  self.tp_glide_time[tp_index],
                                  self.tp_list[-1]['altitude'])

        return sector_entry

    def divert_position(self, x, y, altitude):
        """Update position for diverted task"""
        # Calculate navigation and glide to divert TP
        self.calculate_tp_nav(x, y, self.divert_wp)
        self.calculate_task_glide(x, y, altitude, self.divert_wp, 0, 0,
                                  self.divert_wp['altitude'])

    #-------------------------------------------------------------------------
    # Internal stuff

    def check_sector(self, x, y, altitude, tim):
        """Return True on sector entry, increment TP if barrel sector"""
        if self.tp_sector_flag:
            return False

        # Don't check start or finish sector
        tp_index = self.tp_index
        if tp_index == 0 or tp_index == len(self.tp_list) - 1:
            return False

        if self.in_sector(x, y, tp_index):
            if self.tp_list[tp_index]['radius1'] <= 500:
                self.next_turnpoint(x, y, altitude, tim)
            else:
                self.tp_sector_flag = True
            return True
        else:
            return False

    def calculate_tp_nav(self, x, y, tp):
        """Calculate distance and bearing to next TP"""
        tpx, tpy = self.tp_minxy(tp)
        dx = tpx - x
        dy = tpy - y
        self.tp_distance = math.hypot(dx, dy)
        self.tp_bearing = math.atan2(dx, dy)
        self.nav_tp = tp

    def calculate_task_glide(self, x, y, altitude, tp,
                             tp_height_loss, tp_glide_time, field_elevation):
        """Calculate glide around remainder of task"""
        if self.vm > self.wind_speed:
            tpx, tpy = self.tp_minxy(tp)
            height_loss, tim = self.calculate_glide(x, y, tpx, tpy)

            self.ete = tim + tp_glide_time
            height_loss = height_loss + tp_height_loss
            self.arrival_height = (altitude - height_loss - field_elevation)
            self.glide_margin = ((self.arrival_height - self.safety_height) /
                                 height_loss)
        else:
            self.ete = 0
            self.arrival_height = 0
            self.glide_margin = 0

    def calculate_leg_speed(self, x, y, altitude, tim):
        """Calcuate task speed from last TP"""
        if (tim - self.speed_calc_time) < 30:
            # Only calculate once every 30 seconds
            return
        else:
            self.speed_calc_time = tim

        tp_ref = self.tp_log[self.tp_index - 1]

        # Deltas from last turnpoint
        dt = tim - tp_ref['tim']
        da = altitude - tp_ref['alt']
        dx = x - tp_ref['x']
        dy = y - tp_ref['y']

        distance = math.sqrt(dx * dx + dy * dy)
        course = math.atan2(dx, dy)

        # Time to return/glide to last TP height
        glide_time = da / self.vm_sink_rate

        # Wind corrected Maccready ground speed
        ground_speed = calculate_ground_speed(
                self.vm, course, self.wind_speed, self.wind_direction)

        distance = distance + glide_time * ground_speed
        dt = dt + glide_time
        if (dt < MIN_TASK_SPEED_TIME) or (distance < MIN_TASK_SPEED_DISTANCE):
            # Don't update unless sufficient time has passed
            return

        # Task speed to glide corrected position
        self.task_speed = distance / dt

        # Wind corrected speed
        self.task_air_speed = calculate_air_speed(
                self.task_speed, course, self.wind_speed, self.wind_direction)

    def calculate_glide(self, x1, y1, x2, y2):
        """Return wind corrected glide height loss and time"""
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        course = math.atan2(dx, dy)

        # Get wind correct ground speed
        ground_speed = calculate_ground_speed(self.vm, course, self.wind_speed,
                                              self.wind_direction)
        # Height loss and time
        height_loss = dist * self.vm_sink_rate / ground_speed
        tim = dist / ground_speed

        return height_loss, tim

    def calculate_turnpoint_glides(self):
        """Calculate height loss and time around all task turnpoints"""
        if self.vm <= self.wind_speed:
            return

        glides = [self.calculate_glide(p1['x'], p1['y'], p2['x'], p2['y'])
                  for  p1, p2 in zip(self.tp_list, self.tp_list[1:])]
        height_loss, glide_time = map(list, zip(*glides))

        # Cumulative sums
        for i in range(-1, -len(glides), -1):
            height_loss[i - 1] += height_loss[i]
            glide_time[i - 1] += glide_time[i]

        self.tp_height_loss = height_loss + [0]
        self.tp_glide_time = glide_time + [0]

    def tp_minxy(self, tp):
        # Return turnpoint sector coordinates for min task distance
        if tp.has_key('mindistx'):
            xy = (tp['mindistx'], tp['mindisty'])
        else:
            xy = (tp['x'], tp['y'])
        return xy
