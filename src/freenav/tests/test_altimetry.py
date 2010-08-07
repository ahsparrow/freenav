import nose.tools

import freenav.altimetry

TAKEOFF_ALTITUDE = 317

class TestClass:
    def setup(self):
        self.alt = freenav.altimetry.PressureAltimetry()
        self.alt.set_takeoff_altitude(TAKEOFF_ALTITUDE)

    def test_ground_pressure(self):
        self.alt.update_ground_pressure_level(10)
        self.alt.update_ground_pressure_level(20)
        self.alt.update_ground_pressure_level(30)

        nose.tools.assert_almost_equal(self.alt.takeoff_pressure_level, 20)

    def test_qne(self):
        test_qne =  25
        ground_pressure_level = 100

        self.alt.update_ground_pressure_level(ground_pressure_level)
        self.alt.update_pressure_level(test_qne + ground_pressure_level)

        qne = self.alt.get_pressure_height()

        nose.tools.assert_almost_equal(qne, test_qne)

    def test_qnh(self):
        takeoff_pressure_level = 123
        test_pressure_level = 1034

        self.alt.set_takeoff_pressure_level(takeoff_pressure_level)
        self.alt.update_pressure_level(test_pressure_level)

        qnh = self.alt.get_pressure_altitude()
        calc_qnh = (TAKEOFF_ALTITUDE +
                    (test_pressure_level - takeoff_pressure_level))
        nose.tools.assert_almost_equal(qnh, calc_qnh)

    def test_fl(self):
        test_fl = 3423

        self.alt.update_pressure_level(test_fl)
        nose.tools.assert_almost_equal(test_fl, self.alt.get_flight_level())

    def test_qne(self):
        test_qne = 345
        test_ground_pressure_level = -78
        test_pressure_level = 1933

        self.alt.set_qne(test_qne)
        self.alt.update_ground_pressure_level(test_ground_pressure_level)
        self.alt.update_pressure_level(test_pressure_level)

        check_fl = test_pressure_level - test_ground_pressure_level + test_qne
        nose.tools.assert_almost_equal(check_fl, self.alt.get_flight_level())
