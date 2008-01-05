#!/usr/bin/env python
"""Map projection

Only Lambert Conformal Conical implemented
"""

__all__ = ['EARTH_RADIUS', 'Lambert']

from math import *

EARTH_RADIUS = 6371000.0

class Projection:
    def dist(self, x1, y1, x2, y2):
        lat1, lon1 = [radians(c) for c in self.reverse(x1, y1)]
        lat2, lon2 = [radians(c) for c in self.reverse(x2, y2)]
        d=2*asin(sqrt((sin((lat1-lat2)/2))**2 +\
            cos(lat1)*cos(lat2)*(sin((lon1-lon2)/2))**2))

        return EARTH_RADIUS*d

class Lambert(Projection):
    def __init__(self, std_parallel1, std_parallel2, refLat, refLon):
        std_parallel1 = radians(std_parallel1)
        std_parallel2 = radians(std_parallel2)
        refLat = radians(refLat)
        self.refLon = radians(refLon)
        self.n = (log(cos(std_parallel1)/cos(std_parallel2))/ 
            log(tan(pi/4 + std_parallel2/2)/tan(pi/4 + std_parallel1/2)))

        self.F = (cos(std_parallel1)*(tan(pi/4+std_parallel1/2))**self.n)/self.n

        self.rho0 = self.F*(1/tan(pi/4 + refLat/2))**self.n

    def forward(self, lat, lon):
        lat, lon = radians(lat), radians(lon)
        rho = self.F*(1/tan(pi/4 + lat/2))**self.n

        x = EARTH_RADIUS*rho*sin(self.n*(lon - self.refLon))
        y = EARTH_RADIUS*(self.rho0 - rho*cos(self.n*(lon - self.refLon)))
        return x, y

    def reverse(self, x, y):
        x = x/EARTH_RADIUS
        y = y/EARTH_RADIUS
        theta = atan2(x, (self.rho0-y))
        if self.n > 0:
            sn = 1
        elif self.n < 0:
            sn = -1
        else:
            sn = 0
        phi = sn*sqrt(x*x + (self.rho0-y)**2)

        lat = 2*atan((self.F/phi)**(1/self.n)) - pi/2
        lon = self.refLon + theta/self.n
        return degrees(lat), degrees(lon)
