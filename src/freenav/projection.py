"""Map projection

Only Lambert Conformal Conical implemented
"""

__all__ = ['EARTH_RADIUS', 'Lambert']

from math import sin, cos, tan, asin, atan, atan2, log, sqrt, pi

EARTH_RADIUS = 6371000.0

class Projection:
    """Projection base case"""
    def dist(self, x1, y1, x2, y2):
        """Calculate true distance between two projected points"""
        lat1, lon1 = self.reverse(x1, y1)
        lat2, lon2 = self.reverse(x2, y2)
        dist_ang = (2 * asin(sqrt((sin((lat1 - lat2) / 2)) ** 2 +
                    cos(lat1) * cos(lat2) * (sin((lon1 - lon2) / 2)) ** 2)))

        return EARTH_RADIUS * dist_ang

    def course(self, x1, y1, x2, y2):
        """Calculate (initial) course between two projected point"""
        lat1, lon1 = self.reverse(x1, y1)
        lat2, lon2 = self.reverse(x2, y2)
        tc1 = atan2(sin(lon2 - lon1) * cos(lat2),
                    (cos(lat1) * sin(lat2) -
                     sin(lat1) * cos(lat2) * cos(lon2 - lon1)))
        return tc1 % (2 * pi)

class Lambert(Projection):
    """Lambert projection class"""
    def __init__(self, parallel1, parallel2, lat, lon):
        """Class initialisation"""
        self.ref_lon = lon
        self.n = (log(cos(parallel1) / cos(parallel2)) / 
                  log(tan(pi/4 + parallel2 / 2) / tan(pi/4 + parallel1 / 2)))

        self.f = (cos(parallel1) *
                  (tan(pi/4 + parallel1 / 2)) ** self.n) / self.n

        self.rho0 = self.f * (1 / tan(pi / 4 + lat / 2)) ** self.n

    def forward(self, lat, lon):
        """Project lat-lon position to X-Y position"""
        rho = self.f * (1 / tan(pi / 4 + lat / 2)) ** self.n

        x = EARTH_RADIUS * rho * sin(self.n * (lon - self.ref_lon))
        y = EARTH_RADIUS * (self.rho0 - rho * cos(self.n *
                                                  (lon - self.ref_lon)))
        return x, y

    def reverse(self, x, y):
        """Convert projected X-Y position back to lat-lon"""
        x = x / EARTH_RADIUS
        y = y / EARTH_RADIUS
        theta = atan2(x, (self.rho0 - y))
        if self.n > 0:
            sgn = 1
        elif self.n < 0:
            sgn = -1
        else:
            sgn = 0
        phi = sgn * sqrt(x * x + (self.rho0-y) ** 2)

        lat = 2 * atan((self.f / phi) ** (1 / self.n)) - pi / 2
        lon = self.ref_lon + theta / self.n
        return lat, lon
