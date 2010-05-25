"""Classes for latitude and longitude."""
import math

class LatLon(object):
    """Base class for Latitude and Longitude"""
    def __init__(self, val):
        """Class initialiser"""
        self.val = val

    def dms_split(self):
        """Return degrees, minutes, seconds tuple"""
        total_seconds = int(round(abs(math.degrees(self.val)) * 3600))
        seconds = total_seconds % 60
        total_minutes = total_seconds / 60
        minutes = total_minutes % 60
        degress = minutes / 60
        return degress, minutes, seconds

    def radians(self):
        """Return value in radians"""
        return self.val

    def degrees(self):
        """Return value in degrees"""
        return math.degrees(self.val)

    def __float__(self):
        return self.val

class Latitude(LatLon):
    """Latitute class"""
    def __init__(self, ang):
        """Construct from a NDDMMSS string or a value in radians"""
        if isinstance(ang, str):
            degress = int(ang[1:3])
            minutes = int(ang[3:5])
            seconds = int(ang[5:7])
            val = math.radians(degress + minutes / 60.0 + seconds / 3600.0)
            if ang[0] == "S":
                val = -val
        else:
            val = float(ang)

        LatLon.__init__(self, val)

    def dms(self):
        """Return dict with deg, min, sec and ns"""
        degrees, minutes, seconds = self.dms_split()
        hemi = 'N' if self.val > 0 else 'S'
        return {'deg': degrees, 'min': minutes, 'sec': seconds, 'ns': hemi}

class Longitude(LatLon):
    """Longitude class"""
    def __init__(self, ang):
        """Construct from a EDDDMMSS string or a value in radians"""
        if isinstance(ang, str):
            degrees = int(ang[1:4])
            minutes = int(ang[4:6])
            seconds = int(ang[6:8])
            val = math.radians(degrees + minutes / 60.0 + seconds / 3600.0)
            if ang[0] == "W":
                val = -val
        else:
            val = float(ang)

        LatLon.__init__(self, val)

    def dms(self):
        """Return dict with deg, min, sec and ew"""
        degrees, minutes, seconds = self.dms_split()
        hemi = 'E' if self.val > 0 else 'W'
        return {'deg': degrees, 'min': minutes, 'sec': seconds, 'ew': hemi}

