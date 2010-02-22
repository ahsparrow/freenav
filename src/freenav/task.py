import math

class Task:
    def __init__(self, tp_list, polar, safety_height):
        """Class initialisation"""
        self.tp_list = tp_list
        self.polar = polar
        self.safety_height = safety_height

        self.tp_index = 0
        self.divert_wp = None

        self.ete = 0
        self.arrival_height = 0
        self.glide_margin = 0
        self.set_maccready(0.0, 1.0, 1.0)

    def reset(self):
        """Reset turnpoint index"""
        self.tp_index = 0
        self.divert_wp = None

    def start(self, start_time):
        """Start task"""
        self.start_time = start_time
        self.tp_index = 1

    def next_turnpoint(self):
        if self.tp_index < (len(self.tp_list) - 1):
            self.tp_index += 1

    def prev_turnpoint(self):
        if self.tp_index > 1:
            self.tp_index -= 1

    def divert(self, wp):
        self.divert_wp = wp

    def cancel_divert(self):
        self.divert_wp = None

    def set_maccready(self, maccready, bugs, ballast):
        """Set new Maccready parameters"""
        self.maccready = maccready
        self.bugs = bugs
        self.ballast = ballast

        # Adjust polar coefficients for ballast and bugs
        a = self.polar['a'] / math.sqrt(ballast) * bugs
        b = self.polar['b'] * bugs
        c = self.polar['c'] * math.sqrt(ballast) * bugs

        # MacCready speed and sink rate
        self.vm = math.sqrt((c - self.maccready) / a)
        self.vm_sink_rate = -(a * self.vm ** 2 + b * self.vm + c)

    def get_glide(self):
        """Return final glide parameters"""
        return {'margin': self.glide_margin,
                'height': self.arrival_height,
                'ete': self.ete,
                'maccready': self.maccready}

    def get_tp_xy(self):
        """Return XY coordinates of active TP"""
        if self.divert_wp:
            tp = self.divert_wp
        else:
            tp = self.tp_list[self.tp_index]
        return self.tp_minxy(tp)

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

    def tp_minxy(self, tp):
        if tp.has_key('mindistx'):
            xy = (tp['mindistx'], tp['mindisty'])
        else:
            xy = (tp['x'], tp['y'])
        return xy

