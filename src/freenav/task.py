import math

MIN_TASK_SPEED_TIME = 15 * 60
MIN_TASK_SPEED_DISTANCE = 10000

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
        self.nav_wp = tp_list[0]
        self.tp_index = 0
        self.tp_distance = 0
        self.tp_bearing = 0
        self.tp_log = [None] * len(tp_list)
        self.tp_sector_flag = False

        # Set Maccready (and do initial glide calculations)
        self.set_maccready(0.0)
        self.glide_ete = 0
        self.glide_arrival_height = 0
        self.glide_margin = 0

        # Task speed/time values
        self.start_time = 0
        self.task_speed = 0
        self.task_air_speed = 0
        self.task_ete = 0
        self.task_calc_time = 0

    def reset(self):
        """Reset turnpoint index"""
        self.tp_index = 0
        self.tp_sector_flag = False

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
        self.tp_sector_flag = False

        self.start_time = start_time
        self.tp_index = 1
        self.tp_log[0] = {'x': x, 'y': y, 'alt': altitude, 'tim': resume_time}

    def next_turnpoint(self, x, y, altitude, tp_time):
        """Increment turnpoint"""
        if self.tp_index < (len(self.tp_list) - 1):
            self.tp_log[self.tp_index] = {'x': x, 'y': y, 'alt': altitude, 'tim': tp_time}
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
        self.nav_wp = wp

    def set_wind(self, wind):
        """Set a new wind vector"""
        self.wind_speed = wind['speed']
        self.wind_direction = wind['direction']

        self.set_tp_glides()

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

        self.set_tp_glides()

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
                'height': self.glide_arrival_height,
                'ete': self.glide_ete,
                'maccready': self.maccready}

    def get_turnpoint_id(self):
        """Return ID of active TP"""
        return self.nav_wp["id"]

    def in_sector(self, x, y, tp_index=0):
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
        self.nav_wp = self.tp_list[tp_index]

        # Navigation waypoint
        tpx, tpy = self.tp_minxy(self.nav_wp)
        dist, bearing = self.calculate_nav(x, y, tpx, tpy) 
        self.tp_distance = dist
        self.tp_bearing = bearing

        # Glide waypoint
        if self.tp_sector_flag:
            tp_index = self.tp_index + 1

        # Calculate glide around rest of the task
        self.set_glide_to_finish(x, y, altitude, self.tp_list[tp_index:])

        # Calculate speed on current leg and time to complete task
        if tp_index != 0 and (tim - self.task_calc_time) >= 30:
            self.task_calc_time = tim
            if self.vm > self.wind_speed:
                self.set_task_speed(x, y, altitude, tim, self.tp_log[self.tp_index - 1])

                if self.task_air_speed > self.wind_speed:
                    height = altitude - self.tp_list[-1]['altitude']
                    print
                    ete = self.calculate_ete(x, y, height, self.tp_list[tp_index:])
                    self.task_ete = tim - self.start_time + ete

        return sector_entry

    def divert_position(self, x, y, altitude):
        """Update position for diverted task"""
        # Calculate navigation and glide to divert TP
        tpx, tpy = self.tp_minxy(self.divert_wp)
        dist, bearing = self.calculate_nav(x, y, tpx, tpy)
        self.tp_distance = dist
        self.tp_bearing = bearing

        self.set_glide_to_finish(x, y, altitude, [self.divert_wp])

    #-------------------------------------------------------------------------
    # Internal stuff

    def set_task_speed(self, x, y, altitude, tim, tp_ref):
        """Calcuate task speed from last TP"""
        # Deltas from turnpoint
        dt = tim - tp_ref['tim']
        da = altitude - tp_ref['alt']
        dx = x - tp_ref['x']
        dy = y - tp_ref['y']

        distance = math.hypot(dx, dy)
        course = math.atan2(dx, dy)

        # Time to return/glide to last TP height
        glide_time = da / self.vm_sink_rate

        # Wind corrected Maccready ground speed
        ground_speed = self.calculate_ground_speed(self.vm, course)
        #print distance, glide_time, ground_speed

        distance = distance + glide_time * ground_speed
        dt = dt + glide_time
        if (dt < MIN_TASK_SPEED_TIME) or (distance < MIN_TASK_SPEED_DISTANCE):
            # Don't update unless sufficient time has passed
            return

        # Task speed to glide corrected position
        self.task_speed = distance / dt

        # Wind corrected speed
        self.task_air_speed = self.calculate_air_speed(self.task_speed, course)
        #print self.task_air_speed, self.task_speed

    def set_glide_to_finish(self, x, y, altitude, tp_list):
        """Calculate glide around remainder of task"""
        if self.vm > self.wind_speed:
            tp = tp_list[0]
            tpx, tpy = self.tp_minxy(tp)
            height_loss, tim = self.calculate_glide(x, y, tpx, tpy)

            self.glide_ete = tim + tp.get('glide_time', 0)
            height_loss = height_loss + tp.get('height_loss', 0)

            self.glide_arrival_height = (altitude - height_loss - tp_list[-1]['altitude'])
            self.glide_margin = ((self.glide_arrival_height - self.safety_height) /
                                 height_loss)
        else:
            self.glide_ete = 0
            self.glide_arrival_height = 0
            self.glide_margin = 0

    def set_tp_glides(self):
        """Calculate height loss and time around all task turnpoints"""
        if self.vm <= self.wind_speed:
            return

        # Calculate glides between consecutive turnpoints
        glides = [self.calculate_glide(p1['x'], p1['y'], p2['x'], p2['y'])
                  for  p1, p2 in zip(self.tp_list, self.tp_list[1:])]

        # Add zeroes for final TP and split into two lists
        glides.append((0, 0))
        height_loss, glide_time = map(list, zip(*glides))

        # Calculate cumulative sums
        for i in range(-1, -len(glides), -1):
            height_loss[i - 1] += height_loss[i]
            glide_time[i - 1] += glide_time[i]

        # Add to TP list
        for tp, tp_height_loss, tp_glide_time in zip(self.tp_list, height_loss, glide_time):
            tp['height_loss'] = tp_height_loss
            tp['glide_time'] = tp_glide_time

    def calculate_nav(self, x1, y1, x2, y2):
        """Calculate distance and bearing to next TP"""
        dx = x2 - x1
        dy = y2 - y1
        tp_distance = math.hypot(dx, dy)
        tp_bearing = math.atan2(dx, dy)
        return tp_distance, tp_bearing

    def calculate_glide(self, x1, y1, x2, y2):
        """Return wind corrected glide height loss and time"""
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        course = math.atan2(dx, dy)

        # Get wind correct ground speed
        ground_speed = self.calculate_ground_speed(self.vm, course)

        # Height loss and time
        height_loss = dist * self.vm_sink_rate / ground_speed
        tim = dist / ground_speed

        return height_loss, tim

    def calculate_ete(self, x, y, height, tp_list):
        """Recursively calculate time to complete the task"""
        if not tp_list:
            return 0

        # Get distance, bearing and glide to next TP
        tp = tp_list[0]
        tpx, tpy = self.tp_minxy(tp)

        tp_dist, tp_bearing = self.calculate_nav(x, y, tpx, tpy)
        gs = self.calculate_ground_speed(self.task_air_speed, tp_bearing)

        if height < tp['height_loss']:
            # If height is less than need for glide at next TP then recurse rest of TPs
            tim = (tp_dist / gs) + self.calculate_ete(tpx, tpy, height, tp_list[1:])
            print 1, tim, (tp_dist / gs), gs
        else:
            # Calculate fraction of leg at task speed and remainder at glide speed
            height_diff = height - tp['height_loss']
            glide_height_loss, glide_time = self.calculate_glide(x, y, tpx, tpy)
            height_ratio = height_diff / glide_height_loss

            if height_ratio > 1:
                # Above glide, so just do glide to finish
                tim = glide_time + tp['glide_time']
                print 2, tim, glide_time, tp['glide_time']
            else:
                # Below glide, so calculate part of time at task speed and part at glide
                t_dist = tp_dist * (1 - height_ratio)
                t_time = t_dist / gs

                g_time = glide_time * height_ratio

                tim = t_time + g_time + tp['glide_time']
                print 3, tim, t_time, gs, self.wind_speed, self.task_air_speed

        return tim

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

    def tp_minxy(self, tp):
        # Return turnpoint sector coordinates for min task distance
        if tp.has_key('mindistx'):
            xy = (tp['mindistx'], tp['mindisty'])
        else:
            xy = (tp['x'], tp['y'])
        return xy

    def calculate_ground_speed(self, air_speed, course):
        """Return ground speed given air speed, course and wind"""
        swc = self.wind_speed / air_speed * math.sin(self.wind_direction - course)

        ground_speed = (air_speed * math.sqrt(1 - swc ** 2) +
                        self.wind_speed * math.cos(self.wind_direction - course))

        return ground_speed

    def calculate_air_speed(self, ground_speed, course):
        """Return air speed given ground speed, course and wind"""
        a2 = (self.wind_speed ** 2 + ground_speed ** 2 -
              2 * self.wind_speed * ground_speed * math.cos(course - self.wind_direction))
        a2 = max(a2, 0)

        if a2 > 0:
            return math.sqrt(a2)
        else:
            return 0
