"""Classes for latitude and longitude."""
import math

class LatLon(object):
    """Base class for Latitude and Longitude."""
    def dms_split(self):
        secs = int(round(abs(math.degrees(self.val))*3600))
        sec = secs % 60
        mins = secs/60
        min = mins % 60
        deg = mins/60
        return deg, min, sec

    def radians(self):
        """Return value in radians."""
        return self.val

class Latitude(LatLon):
    def __init__(self, a):
        """Construct from a NDDMMSS string or a value in radians."""
        if isinstance(a, str):
            deg = int(a[1:3])
            min = int(a[3:5])
            sec = int(a[5:7])
            val = math.radians(deg + min/60.0 + sec/3600.0)
            if a[0] == "S":
                val = -val
        else:
            val = float(a)
        self.val = val

    def dms(self):
        """Return dict with deg, min, sec and ns."""
        deg, min, sec = self.dms_split()
        ns = 'N' if self.val>0 else 'S'
        return {'deg': deg, 'min': min, 'sec': sec, 'ns': ns}

class Longitude(LatLon):
    def __init__(self, a):
        """Construct from a EDDDMMSS string or a value in radians."""
        if isinstance(a, str):
            deg = int(a[1:4])
            min = int(a[4:6])
            sec = int(a[6:8])
            val = math.radians(deg + min/60.0 + sec/3600.0)
            if a[0] == "W":
                val = -val
        else:
            val = float(a)
        self.val = val

    def dms(self):
        """Return dict with deg, min, sec and ew."""
        deg, min, sec = self.dms_split()
        ew = 'E' if self.val>0 else 'W'
        return {'deg': deg, 'min': min, 'sec': sec, 'ew': ew}

