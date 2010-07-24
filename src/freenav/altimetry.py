"""This module provides the altimetry functionality for freenav program.

Given the takeoff altitude and QNE setting the class converts from standard
(1013.25mb) pressure readings to QNH, QFE and FL.

"""

import collections

# Size of the running average for takeoff pressure
AVG_SAMPLES = 100

class PressureAltimetry:
    """Class to handle altimetry related calculations for freenav"""
    def __init__(self):
        """Class initialisation"""
        self.takeoff_pressure_level = None
        self.takeoff_altitude = None
        self.qne = None

        self.pressure_level = None
        self.pressure_level_deque = collections.deque()

    def set_qne(self, qne):
        """Set QNE configuration value"""
        self.qne = qne

    def set_takeoff_altitude(self, altitude):
        """Sets the takeoff altitude configuration value"""
        self.takeoff_altitude = altitude

    def set_takeoff_pressure_level(self, level):
        """Set the takeoff pressure level (used to re-initialise in the air)"""
        self.takeoff_pressure_level = level

    def update_pressure_level(self, level):
        """Update pressure level value"""
        self.pressure_level = level 

    def update_ground_pressure_level(self, level):
        """Calculate running average of takeoff pressure level"""
        self.pressure_level_deque.append(level)
        if len(self.pressure_level_deque) > AVG_SAMPLES:
            self.pressure_level_deque.popleft()

        self.pressure_level = level
        self.takeoff_pressure_level = (sum(self.pressure_level_deque) /
                                       float(len(self.pressure_level_deque)))

    def get_pressure_height(self):
        """Return height above takeoff airfield"""
        if self.pressure_level is None or self.takeoff_pressure_level is None:
            height = None
        else:
            height = self.pressure_level - self.takeoff_pressure_level
        return height

    def get_pressure_altitude(self):
        """Return height above sea level"""
        height = self.get_pressure_height()
        if height is None or self.takeoff_altitude is None:
            altitude = None
        else:
            altitude = height + self.takeoff_altitude
        return altitude

    def get_flight_level(self):
        """Return (QNE corrected) flight level"""
        if self.pressure_level is None:
            level = None
        else:
            level = self.pressure_level
            if not (self.qne is None or self.takeoff_pressure_level is None):
                level = level - self.takeoff_pressure_level + self.qne
        return level
