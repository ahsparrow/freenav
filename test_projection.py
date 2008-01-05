#!/usr/bin/env python

import projection
import math, unittest

REF_LAT = 50
REF_LON = 0
STD_PARA1 = 52
STD_PARA2 = 48

class ProjectionSequenceFunctions(unittest.TestCase):

    def setUp(self):
        self.lambert = projection.Lambert(STD_PARA1, STD_PARA2, REF_LAT, REF_LON)

    def testproj1(self):
        x, y = self.lambert.forward(50, 0)
        self.assertAlmostEqual(x, 0, 0)
        self.assertAlmostEqual(y, 0, 0)

        x,y = self.lambert.forward(50.1, 0)
        self.assertAlmostEqual(x, 0, -1)
        self.assertAlmostEqual(y, projection.EARTH_RADIUS*2*math.pi/3600, -2)

        x,y = self.lambert.forward(50, 0.1)
        self.assertAlmostEqual(x, math.cos(math.radians(50))*\
                                  projection.EARTH_RADIUS*2*math.pi/3600, -2)
        self.assertAlmostEqual(y, 0, -1)

        x,y = self.lambert.forward(49, -1)
        self.assertAlmostEqual(x, -math.cos(math.radians(49))*\
                                  projection.EARTH_RADIUS*2*math.pi/360, -2)
        self.assertAlmostEqual(y, -projection.EARTH_RADIUS*2*math.pi/360, -4)

    def testproj2(self):
        x, y = self.lambert.forward(51, 1)
        lat, lon = self.lambert.reverse(x, y)
        self.assertAlmostEqual(lat, 51, 6)
        self.assertAlmostEqual(lon, 1, 6)


if __name__ == '__main__':
    unittest.main()
