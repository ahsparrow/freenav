import math

import nose.tools

import freenav.projection

FAI_EARTH_RADIUS = 6371000.0

PARALLEL1 = math.radians(49)
PARALLEL2 = math.radians(55)
REF_LAT = math.radians(52)
REF_LON = math.radians(0)

LAT1 = math.radians(51.0)
LON1 = math.radians(-1)
LAT2 = math.radians(53.5)
LON2 = math.radians(1.8)

class TestClass:
    def setup(self):
        self.proj = freenav.projection.Lambert(PARALLEL1, PARALLEL2,
                                               REF_LAT, REF_LON)

    def test_forward_reverse(self):
        x, y = self.proj.forward(LAT1, LON1)
        lat, lon = self.proj.reverse(x, y)

        nose.tools.assert_almost_equal(lat, LAT1)
        nose.tools.assert_almost_equal(lon, LON1)

    def test_dist(self):
        x1, y1 = self.proj.forward(LAT1, LON1)
        x2, y2 = self.proj.forward(LAT2, LON2)

        dist = self.proj.dist(x1, y1, x2, y2)

        dist1 = FAI_EARTH_RADIUS * math.acos(math.sin(LAT1) * math.sin(LAT2) +
                  math.cos(LAT1) * math.cos(LAT2) * math.cos(LON1 - LON2))

        nose.tools.assert_almost_equal(dist, dist1)

    def test_course(self):
        x1, y1 = self.proj.forward(LAT1, LON1)
        x2, y2 = self.proj.forward(LAT2, LON2)

        course = self.proj.course(x1, y1, x2, y2)

        d = self.proj.dist(x1, y1, x2, y2) / FAI_EARTH_RADIUS
        course1 = math.acos((math.sin(LAT2) - math.sin(LAT1) * math.cos(d)) /
                            (math.sin(d) * math.cos(LAT1)))
        if math.sin(LON1 - LON2) > 0:
            course1 = 2 * math.pi - course1

        nose.tools.assert_almost_equal(course, course1)
