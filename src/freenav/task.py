import math

MIN_TASK_SPEED_TIME = 0

def calc_ground_speed(air_speed, course, wind_speed, wind_direction):
    """Return ground speed given air speed, course and wind"""
    swc = wind_speed / air_speed * math.sin(wind_direction - course)

    ground_speed = (air_speed * math.sqrt(1 - swc ** 2) +
                    wind_speed * math.cos(wind_direction - course))

    return ground_speed

def calc_air_speed(ground_speed, course, wind_speed, wind_direction):
    """Return air speed given ground speed, course and wind"""
    a2 = (wind_speed ** 2 + ground_speed **2 -
          2 * wind_speed * ground_speed * math.cos(course - wind_direction))
    a2 = max(a2, 0)

    return math.sqrt(a2)

class Task:
    def __init__(self, tp_list, polar, settings):
        """Class initialisation"""
        self.tp_list = tp_list
        self.polar = polar
        self.bugs = settings['bugs']
        self.ballast = settings['ballast']
        self.safety_height = settings['safety_height']

        self.tp_distance = 0
        self.tp_bearing = 0

        self.tp_index = 0
        self.divert_wp = None
        self.tp_times = [None] * len(tp_list)

        self.ete = 0
        self.arrival_height = 0
        self.glide_margin = 0
        self.set_maccready(0.0)

        self.task_speed = 0
        self.task_air_speed = 0
        self.speed_calc_time = 0

    def reset(self):
        """Reset turnpoint index"""
        self.tp_index = 0
        self.divert_wp = None

    def start(self, start_time, x, y, altitude):
        """Start task"""
        self.start_time = start_time
        self.tp_index = 1
        self.tp_times[0] = {'x': x, 'y': y, 'alt': altitude,
                            'tim': start_time}

    def resume(self, start_time, resume_time, x, y, altitude):
        """Resume task after program re-start"""
        self.start_time = start_time
        self.tp_index = 1
        self.tp_times[0] = {'x': x, 'y': y, 'alt': altitude,
                            'tim': resume_time}

    def next_turnpoint(self, tp_time, x, y, altitude):
        """Increment turnpoint"""
        if self.tp_index < (len(self.tp_list) - 1):
            self.tp_times[self.tp_index] = {
                'x': x, 'y': y, 'alt': altitude, 'tim': tp_time}
            self.tp_index += 1

    def prev_turnpoint(self):
        if self.tp_index > 1:
            self.tp_index -= 1

    def divert(self, wp):
        self.divert_wp = wp

    def cancel_divert(self):
        self.divert_wp = None

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

    def incr_maccready(self, incr):
        """Increment Maccready setting"""
        self.set_maccready(self.maccready + incr)

    def decr_maccready(self, decr):
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

    def get_tp_id(self):
        """Return ID of active TP"""
        if self.divert_wp:
            tp = self.divert_wp
        else:
            tp = self.tp_list[self.tp_index]
        return tp["id"]

    def in_start_sector(self, x, y):
        """Return true if in start sector (2D only)"""
        start = self.tp_list[0]

        dx = x - start['x']
        dy = y - start['y']
        dist = math.sqrt(dx ** 2 + dy ** 2)

        in_sector = False
        if dist < start['radius1']:
            ang = math.atan2(dx, dy)
            ang1 = (ang - math.radians(start['angle12'])) % (2 * math.pi)
            if (ang1 > (math.pi / 2)) and (ang1 < (3 * math.pi / 2)):
                in_sector = True

        return in_sector

    def calc_nav(self, x, y):
        """Calculate TP distance and bearing"""
        tp = self.get_tp_xy()
        dx = tp[0] - x
        dy = tp[1] - y
        self.tp_distance = math.sqrt(dx * dx + dy * dy)
        self.tp_bearing = math.atan2(dx, dy)

    def calc_glide(self, x, y, altitude, wind):
        # Get coordinates of minimum remaining task
        if self.divert_wp:
            tps = [self.divert_wp]
        else:
            tps = self.tp_list[self.tp_index:]
        coords = [self.tp_minxy(tp) for tp in tps]

        # Get height loss and ETE around remainder of task
        if self.vm > wind['speed']:
            height_loss, ete = self.calc_height_loss_ete((x, y), coords, wind)
            self.ete = ete
            self.arrival_height = (altitude - height_loss -
                                   self.tp_list[-1]['altitude'])
            self.glide_margin = ((self.arrival_height - self.safety_height) /
                                 height_loss)
        else:
            self.ete = 0
            self.arrival_height = 0
            self.glide_margin = 0

    def calc_speed(self, tim, x, y, altitude, wind):
        """Calcuate task speed from last TP"""
        self.speed_calc_time = tim

        # Deltas from last turnpoint
        tp_ref = self.tp_times[self.tp_index - 1]
        dt = tim - tp_ref['tim']
        da = altitude - tp_ref['alt']
        dx = x - tp_ref['x']
        dy = y - tp_ref['y']

        distance = math.sqrt(dx * dx + dy * dy)
        course = math.atan2(dx, dy)

        # Time to return/glide to last TP height
        glide_time = da / self.vm_sink_rate

        # Wind corrected Maccready ground speed
        ground_speed = calc_ground_speed(self.vm, course, wind['speed'],
                                         wind['direction'])

        distance = distance + glide_time * ground_speed
        dt = dt + glide_time
        if dt <= MIN_TASK_SPEED_TIME:
            # Don't update unless sufficient time has passed
            return

        # Task speed to glide corrected position
        self.task_speed = distance / dt

        # Wind corrected speed
        self.task_air_speed = calc_air_speed(self.task_speed, course,
                                             wind['speed'], wind['direction'])

    #-------------------------------------------------------------------------
    # Internal stuff

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
            ground_speed = calc_ground_speed(self.vm, course, wind['speed'],
                                             wind['direction'])

            # Height loss and ETE from this leg plus all the rest
            height_loss = dist * self.vm_sink_rate / ground_speed
            ete = dist / ground_speed

            height_loss += height_loss1
            ete += ete1
        else:
            height_loss = 0
            ete = 0

        return (height_loss, ete)

    def get_tp_xy(self):
        """Return XY coordinates of active TP"""
        if self.divert_wp:
            tp = self.divert_wp
        else:
            tp = self.tp_list[self.tp_index]
        return self.tp_minxy(tp)

    def tp_minxy(self, tp):
        if tp.has_key('mindistx'):
            xy = (tp['mindistx'], tp['mindisty'])
        else:
            xy = (tp['x'], tp['y'])
        return xy
