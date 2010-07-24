"""NMEA parsing module"""

import calendar
import logging
import math
import time

# GGA fields
GGA_TIME = 1
GGA_LATITUDE = 2
GGA_NS = 3
GGA_LONGITUDE = 4
GGA_EW = 5
GGA_FIX_QUALITY = 6
GGA_NUM_SATELLITES = 7
GGA_ALTITUDE = 9

# RMC fields
RMC_TIME = 1
RMC_STATUS = 2
RMC_LATITUDE = 3
RMC_NS = 4
RMC_LONGITUDE = 5
RMC_EW = 6
RMC_SPEED = 7
RMC_TRACK = 8
RMC_DATE = 9

# GRMZ (FLARM pressure altitude) fields
GRMZ_ALTITUDE = 1

# FLAU fields
FLAU_ALARM_LEVEL = 5
FLAU_ALARM_TYPE = 7
FLAU_ALARM_BEARING = 6

# GCS (Volkslogger pressure altitude) fields
GCS_ALTITUDE = 3

KTS_TO_MPS = 1852 / 3600.0
FT_TO_M = 12 * 25.4 / 1000

def check_checksum(data_str, checksum_str):
    """Return True if calculated checksum matches given checksum"""
    try:
        checksum = int(checksum_str, 16)
    except ValueError:
        return False

    # Checksum is XOR of all characters in the data
    csum = 0
    for c in data_str:
        csum = csum ^ ord(c)

    if csum == checksum:
        return True
    else:
        return False

class NmeaParser():
    """Class to parse NMEA data from FLARM or Volkslogger"""
    def __init__(self):
        """Class initialisation"""
        self.logger = logging.getLogger('freelog')

        # Buffer for NMEA data
        self.buf = ''

        # Signals generated from parsing the data
        self.signals = set()

        # NMEA sentence processing functions
        self.proc_funcs = {'GPRMC': self.proc_rmc,
                           'GPGGA': self.proc_gga,
                           'PGRMZ': self.proc_grmz,
                           'PFLAU': self.proc_flau,
                           'PGCS': self.proc_gcs}

        # Initialise variables
        self.flarm_alarm_level = 0
        self.time = -1
        self.speed = 0
        self.track = 0
        self.num_satellites = 0
        self.gps_altitude = 0
        self.pressure_alt = 0

        self.date = "010100"
        self.rmc_time = 0
        self.gga_time = 0

    def parse(self, data):
        """Parse NMEA data. Return list of signals"""
        # Prepend new data to old
        buf = ''.join([self.buf, data])

        # Clear signal list then process the data
        self.signals.clear()
        self.buf = self.parse_buf(buf)

        return self.signals

    def parse_buf(self, buf):
        """Extract NMEA data from data buffer. Return any unparsed data"""
        # Split data buffer at first newline
        sentence, separator, remainder = buf.partition("\r\n")

        if separator:
            if sentence[0:1] == '$':
                # Split sentence into message body and checksum
                body, _sep, checksum = sentence[1:].partition('*')

                if check_checksum(body, checksum):
                    self.logger.debug(sentence)
                    # Split body into comma separated fields and process
                    fields = body.split(',')
                    self.proc_funcs.get(fields[0], self.proc_unknown)(fields)
                else:
                    self.logger.warning("Checksum error: " + sentence)
            else:
                self.logger.warning("Incorrect sentence header: " + sentence)

            # Recurse function to process remaining data in buffer
            return self.parse_buf(remainder)
        else:
            return sentence

    def proc_gga(self, fields):
        """Process GGA GPS data. Time, lat/lon, altitude and num satellites"""
        quality = fields[GGA_FIX_QUALITY]
        if quality == '0':
            # Bail out early if fix quality is invalid
            return

        try:
            # Time
            tim = fields[GGA_TIME]

            # Latitude and longitude
            lat = fields[GGA_LATITUDE]
            self.latitude = math.radians(int(lat[:2]) + float(lat[2:]) / 60)

            lon = fields[GGA_LONGITUDE]
            self.longitude = math.radians(int(lon[:3]) + float(lon[3:]) / 60)
            if fields[GGA_EW] == 'W':
                self.longitude = -self.longitude

            # Number of satellites
            self.num_satellites = int(fields[GGA_NUM_SATELLITES])

            # Altitude above MSL
            self.gps_altitude = float(fields[GGA_ALTITUDE])
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        # Don't signal new-position if last GGA and RMC occured at the same time
        if self.rmc_time != self.gga_time:
            self.set_time(tim)
            self.signals.add('new-position')

        self.gga_time = tim

    def proc_rmc(self, fields):
        """Process RMC GPS data. Time, speed and track"""
        status = fields[RMC_STATUS]
        if status != 'A':
            # Bail out early if inactive fix
            return

        try:
            tim = fields[RMC_TIME]
            self.date = fields[RMC_DATE]

            # Latitude and longitude
            lat = fields[RMC_LATITUDE]
            self.latitude = math.radians(int(lat[:2]) + float(lat[2:]) / 60)

            lon = fields[RMC_LONGITUDE]
            self.longitude = math.radians(int(lon[:3]) + float(lon[3:]) / 60)
            if fields[RMC_EW] == 'W':
                self.longitude = -self.longitude

            # Speed and track
            speed_str = fields[RMC_SPEED]
            if speed_str:
                self.speed = float(speed_str) * KTS_TO_MPS

            track_str = fields[RMC_TRACK]
            if track_str:
                self.track = math.radians(float(track_str))
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        # Don't signal new-position if last GGA and RMC occured at the same time
        if self.gga_time != self.rmc_time:
            self.set_time(tim)
            self.signals.add('new-position')

        self.rmc_time = tim

    def proc_grmz(self, fields):
        """Process pressure altitude data"""
        try:
            self.pressure_alt = int(fields[GRMZ_ALTITUDE]) * FT_TO_M
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        self.signals.add('new-pressure')

    def proc_flau(self, fields):
        """Process FLARM alarm data"""
        old_alarm_level = self.flarm_alarm_level

        try:
            self.flarm_alarm_level = int(fields[FLAU_ALARM_LEVEL])

            bearing_str = fields[FLAU_ALARM_BEARING]
            if bearing_str:
                self.flarm_relative_bearing = int(bearing_str)

            alarm_type_str = fields[FLAU_ALARM_TYPE]
            if alarm_type_str:
                self.flarm_alarm_type = int(alarm_type_str)
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        # Add signal only if alarm level has increased
        if self.flarm_alarm_level > old_alarm_level:
            self.signals.add("flarm-alarm")

    def proc_gcs(self, fields):
        """Process Volkslogger pressure altitude"""
        try:
            # Convert hex string to signed int
            self.pressure_alt = int(fields[GCS_ALTITUDE], 16)
            if self.pressure_alt & 0x8000:
                self.pressure_alt -= 0x10000
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        self.signals.add('new-pressure')

    def proc_unknown(self, fields):
        """Do nothing for unknown sentence"""
        pass

    def set_time(self, tim):
        """Construct time from RMC data string and RMC/GGA time string"""
        tm = time.strptime(self.date + tim, "%d%m%y%H%M%S")
        self.time = calendar.timegm(tm)
