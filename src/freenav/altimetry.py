"""This module provides the altimetry functionality for freenav program"""

import collections

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
        """Set QNE value"""
        self.qne = qne

    def set_pressure_level(self, level):
        """Set pressure level value"""
        self.pressure_level = level 

    def set_takeoff_altitude(self, altitude):
        """Sets the takeoff altitude"""
        self.takeoff_altitude = altitude

    def set_takeoff_pressure_level(self, level):
        """Set the pressure level at takeoff"""
        self.takeoff_pressure_level = level

    def update_ground_pressure_level(self, level):
        """Average takeoff pressure level"""
        self.pressure_level_deque.append(level)

        # Calculate average over 60 samples
        if len(self.pressure_level_deque) > 60:
            self.calc_takeoff_pressure_level()

    def takeoff(self):
        """Leaving the ground"""
        if self.takeoff_pressure_level is None and self.pressure_level_deque:
            # We didn't have time to accumulate a full sample
            self.calc_takeoff_pressure_level()

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

    def calc_takeoff_pressure_level(self):
        """Update takeoff level"""
        self.takeoff_pressure_level = (sum(self.pressure_level_deque) /
                                       len(self.pressure_level_deque))
        self.pressure_level_deque.clear()
