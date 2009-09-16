#!/usr/bin/env python

import nav, projection
import math
import unittest

# This should give a best glide of 40.1 at 52.77 knots, and at MacCready of 2kts
# glide of 34.89 at 67.98 knots
POLAR = {'a': -0.002117, 'b': 0.08998, 'c': -1.560}
ASI_CAL = {'v1': 33.3, 'a1': 0.775, 'b1': 6.1, 'a2': 0.95, 'b2': 0.3}

BEST_GLIDE_SPEED = 52.77
BEST_GLIDE = 40.1
M2_GLIDE_SPEED = 67.98
M2_GLIDE = 34.89

class Dummy:
    pass

class NavSequenceFunctions(unittest.TestCase):
    def setUp(self):
        lambert = projection.Lambert(49, 55, 52, 0)
        polar = POLAR
        asi_cal = ASI_CAL

        self.nav = nav.Nav(lambert, polar, asi_cal, 100)
        self.nav.set_dest(0, 0, 0)

        self.fix = Dummy()
        self.vario = Dummy()

        self.fix.altitude = 1000
        self.fix.track = 0
        self.fix.speed = 0
        self.fix.latitude = 52.0
        self.fix.longitude = 0.0

        self.vario.maccready = 0.0
        self.vario.bugs = 0
        self.vario.ballast = 1.0
        self.vario.air_speed = 0

    def test_dist1(self):
        self.nav.set_dest(1000, 0, 0)
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.dist, 1000, 0)

    def test_dist2(self):
        self.nav.set_dest(0, projection.EARTH_RADIUS*2*math.pi/360, 0)
        self.fix.latitude = 53
        self.fix.longitude = 0
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.dist, 0, -3)

    def test_dist3(self):
        self.nav.set_dest(
            projection.EARTH_RADIUS*2*math.pi/360*math.cos(math.radians(52)),
            0, 0)
        self.fix.latitude = 52
        self.fix.longitude = 1
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.dist, 0, -3)

    def test_maccready1(self):
        self.nav.set_dest(10000, 0, 0)
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.vm, BEST_GLIDE_SPEED*nav.KTS_TO_MPS, 1)
        self.assertAlmostEqual(self.nav.arrival_height, 
                               self.fix.altitude - 10000.0/BEST_GLIDE, 0)

    def test_maccready2(self):
        self.nav.set_dest(10000, 0, 0)
        self.vario.maccready = 2
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.vm, M2_GLIDE_SPEED*nav.KTS_TO_MPS, 1)
        self.assertAlmostEqual(self.nav.arrival_height, 
                               self.fix.altitude - 10000.0/M2_GLIDE, 0)

    def test_headwind(self):
        self.nav.set_dest(10000, 0, 0)
        self.nav.update(0, self.fix, self.vario)
        self.nav.set_headwind(10*nav.KTS_TO_MPS)
        self.assertAlmostEqual(self.nav.arrival_height,
            self.fix.altitude -
            10000.0/BEST_GLIDE*BEST_GLIDE_SPEED/(BEST_GLIDE_SPEED-10), 0)

    def test_asical(self):
        self.vario.air_speed = ASI_CAL['v1']/nav.KTS_TO_MPS
        self.nav.update(0, self.fix, self.vario)
        self.assertAlmostEqual(self.nav.air_speed, 
                               ASI_CAL['v1']*ASI_CAL['a1'] + ASI_CAL['b1'], 1)

if __name__ == '__main__':
    unittest.main()
