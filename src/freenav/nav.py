import math
import time

KTS_TO_MPS = 1852.0/3600
INVALID_ETE = -1

class Nav:
    # Internal units are MKS for all variables
    def __init__(self, projection, polar, asi_cal, height_margin):
        self.projection = projection
        self.polar = polar
        self.asi_cal = asi_cal
        self.height_margin = height_margin

        self.headwind = 0
        self.maccready = 0
        self.bug_ratio = 1.0
        self.ballast_ratio = 1.0

        self.tp = ''
        self.tpx = 0
        self.tpy = 0
        self.tp_altitude = 0
        self.dist = 0

        # Navigation results
        self.x = 0
        self.y = 0
        self.altitude = 0
        self.track = 0
        self.ground_speed = 0
        self.air_speed = 0
        self.utc = ()
        self.bearing = 0
        self.ete = 0
        self.glide_margin = 0
        self.arrival_height = 0

    def set_dest(self, name, x, y, altitude):
        self.tp_name = name
        self.tpx = x
        self.tpy = y
        self.tp_altitude = altitude

    def set_headwind(self, headwind):
        self.headwind = headwind
        self.calc()

    def update(self, timestamp, latitude, longitude, altitude, track,
               ground_speed, air_speed, maccready, bugs, ballast):
        self.utc = time.gmtime(timestamp)
        x, y = self.projection.forward(math.radians(latitude),
                                       math.radians(longitude))
        self.x = int(x)
        self.y = int(y)
        self.altitude = int(altitude)
        self.track = math.radians(track)
        self.ground_speed = ground_speed*KTS_TO_MPS

        # Correct airspeed for airframe static errors
        air_speed = air_speed*KTS_TO_MPS
        if air_speed < self.asi_cal['v1']:
            a, b = self.asi_cal['a1'], self.asi_cal['b1']
        else:
            a, b = self.asi_cal['a2'], self.asi_cal['b2']
        self.air_speed = a * air_speed + b

        self.maccready = maccready * KTS_TO_MPS
        self.bugs_ratio = (100 + bugs) / 100.0
        self.ballast_ratio = ballast
        self.calc()

        return True

    def calc(self):
        # Distance and bearing
        dx = self.tpx-self.x
        dy = self.tpy-self.y
        self.dist = math.sqrt(dx*dx+dy*dy)
        self.bearing = math.atan2(self.tpx-self.x, self.tpy-self.y)

        # Adjust polar coefficients for ballast and bugs
        a = self.polar['a']/math.sqrt(self.ballast_ratio)*self.bugs_ratio
        b = self.polar['b']*self.bugs_ratio
        c = self.polar['c']*math.sqrt(self.ballast_ratio)*self.bugs_ratio

        # MacCready speed and sink rate
        self.vm = math.sqrt((c - self.maccready)/a)
        sink_rate = -(a*self.vm*self.vm + b*self.vm + c)

        # Arrival height, glide margin
        gspeed = self.vm - self.headwind
        if gspeed > 0:
            height_loss = self.dist*sink_rate/gspeed
            self.arrival_height = self.altitude-self.tp_altitude-height_loss

            if height_loss:
                self.glide_margin = \
                    (self.arrival_height - self.height_margin)/height_loss

        # Estimated time enroute
        resgs = math.cos(self.bearing - self.track)*gspeed
        if resgs > 10:
            self.ete = self.dist/resgs
        else:
            self.ete = INVALID_ETE
