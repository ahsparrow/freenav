#!/usr/bin/env python

import math, unittest
import projection

REF_LAT = math.radians(50)
REF_LON = math.radians(0)
STD_PARA1 = math.radians(52)
STD_PARA2 = math.radians(48)

class ProjectionSequenceFunctions(unittest.TestCase):

    def setUp(self):
        self.lambert = projection.Lambert(STD_PARA1, STD_PARA2, REF_LAT,
                                          REF_LON)

    def testproj1(self):
        x, y = self.lambert.forward(math.radians(50), 0)
        self.assertAlmostEqual(x, 0, 0)
        self.assertAlmostEqual(y, 0, 0)

        x,y = self.lambert.forward(math.radians(50.1), 0)
        self.assertAlmostEqual(x, 0, -1)
        self.assertAlmostEqual(y, projection.EARTH_RADIUS*2*math.pi/3600, -2)

        x,y = self.lambert.forward(math.radians(50), math.radians(0.1))
        self.assertAlmostEqual(x, math.cos(math.radians(50))*\
                                  projection.EARTH_RADIUS*2*math.pi/3600, -2)
        self.assertAlmostEqual(y, 0, -1)

        x,y = self.lambert.forward(math.radians(49), math.radians(-1))
        self.assertAlmostEqual(x, -math.cos(math.radians(49))*\
                                  projection.EARTH_RADIUS*2*math.pi/360, -2)
        self.assertAlmostEqual(y, -projection.EARTH_RADIUS*2*math.pi/360, -4)

    def testproj2(self):
        x, y = self.lambert.forward(math.radians(51), math.radians(1))
        lat, lon = self.lambert.reverse(x, y)
        self.assertAlmostEqual(lat, math.radians(51), math.radians(6))
        self.assertAlmostEqual(lon, math.radians(1), math.radians(6))

if __name__ == '__main__':
    unittest.main()
