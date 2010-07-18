"""NMEA interface module"""

import logging
import math
import time

import bluetooth
import gobject
import gtk
import serial

GGA_TIME = 1
GGA_LATITUDE = 2
GGA_NS = 3
GGA_LONGITUDE = 4
GGA_EW = 5
GGA_FIX_QUALITY = 6
GGA_NUM_SATELLITES = 7
GGA_ALTITUDE = 9

RMC_TIME = 1
RMC_STATUS = 2
RMC_LATITUDE = 3
RMC_NS = 4
RMC_LONGITUDE = 5
RMC_EW = 6
RMC_SPEED = 7
RMC_TRACK = 8

GRMZ_ALTITUDE = 1

FLAU_ALARM_LEVEL = 5
FLAU_ALARM_TYPE = 7
FLAU_ALARM_BEARING = 6

GCS_ALTITUDE = 3

FLAC_QUERY_TYPE = 1
FLAC_KEY = 2

KTS_TO_MPS = 1852 / 3600.0
FT_TO_M = 12 * 25.4 / 1000

RF_COMM_CHANNEL = 1

def check_checksum(data_str, checksum_str):
    """Return True if calculated checksum matches given checksum"""
    try:
        checksum = int(checksum_str, 16)
    except ValueError:
        return False

    # Checksum is XOR of all characters in the data
    sum = 0
    for d in data_str:
        sum = sum ^ ord(d)

    if sum == checksum:
        return True
    else:
        return False

def dmm(ang, hemis):
    """Splits lat/lon, in radians, into degrees, minutes and decimal minutes"""
    dec_min = int(round(math.degrees(abs(ang)) * 60000))
    min, dec_min = divmod(dec_min, 1000)
    deg, min = divmod(min, 60)

    return (deg, min, dec_min, hemis[1] if ang < 0 else hemis[0])

class FreeNmea(gobject.GObject):
    def __init__(self):
        gobject.GObject.__init__(self)

        self.logger = logging.getLogger('freelog')

        # Buffer for NMEA data
        self.buf = ''

        # Register new signals
        gobject.signal_new("new-position", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [])
        gobject.signal_new("new-pressure", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [])
        gobject.signal_new("flarm-alarm", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [])

        self.proc_funcs = {'GPRMC': self.proc_rmc,
                           'GPGGA': self.proc_gga,
                           'PGRMZ': self.proc_grmz,
                           'PFLAU': self.proc_flau,
                           'PGCS': self.proc_gcs,
                           'PFLAC': self.proc_flac}

        # Initialise a few variables
        self.flarm_alarm_level = 0
        self.time = -1
        self.speed = 0
        self.track = 0
        self.num_satellites = 0
        self.gps_altitude = 0

        self.gga_is_difftime = True
        self.rmc_is_difftime = True

        self.task_declaration = []

    def open(self, dev, baud_rate):
        """Open NMEA device"""
        if dev[0] == '/':
            self.open_serial(dev, baud_rate)
        else:
            self.open_bt(dev)

    def open_bt(self, addr):
        """Open a bluetooth connection"""
        bt_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        bt_sock.connect((addr, RF_COMM_CHANNEL))

        # Add I/O watch and write method
        gobject.io_add_watch(bt_sock, gobject.IO_IN, self.bt_io_callback)

        self.nmea_dev = bt_sock
        self.write = bt_sock.send

    def open_serial(self, dev_path, baudrate=None):
        """Open serial device"""
        if baudrate:
            ser = serial.Serial(dev_path, baudrate=baudrate, timeout=0)
        else:
            ser = serial.Serial(dev_path, timeout=0)

        # Flush stale data
        ser.flushInput()

        # Add I/O watch and write method
        gobject.io_add_watch(ser, gobject.IO_IN, self.ser_io_callback)

        self.nmea_dev = ser
        self.write = ser.write

    def close(self):
        """Close input device"""
        self.nmea_dev.close()

    def ser_io_callback(self, *args):
        """Callback on NMEA serial input data"""
        data = self.nmea_dev.read()
        self.add_nmea_data(data)

        return True

    def bt_io_callback(self, *args):
        """Callback on NMEA bluetooth input data"""
        data = self.nmea_dev.recv(1024)
        self.add_nmea_data(data)

        return True

    def add_nmea_data(self, data):
        """Prepend new NMEA data and parse new data"""
        buf = ''.join([self.buf, data])
        self.buf = self.parse_nmea(buf)

    def parse_nmea(self, buf):
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
            return self.parse_nmea(remainder)
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
            gga_time = int(tim[:2]) * 3600 + int(tim[2:4]) * 60 + int(tim[4:6])

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

        self.gga_is_difftime = (gga_time != self.time)
        self.time = gga_time

        # Send new-position unless RMC occurs at the same time
        if self.rmc_is_difftime:
            self.emit('new-position')

    def proc_rmc(self, fields):
        """Process RMC GPS data. Time, speed and track"""
        status = fields[RMC_STATUS]
        if status != 'A':
            # Bail out early if inactive fix
            return

        try:
            tim = fields[RMC_TIME]
            rmc_time = int(tim[:2]) * 3600 + int(tim[2:4]) * 60 + int(tim[4:6])

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

        self.rmc_is_difftime = (rmc_time != self.time)
        self.time = rmc_time

        # Send new-position unless GGA occurs at the same time
        if self.gga_is_difftime:
            self.emit('new-position')

    def proc_grmz(self, fields):
        """Process pressure altitude data"""
        try:
            self.pressure_alt = int(fields[GRMZ_ALTITUDE]) * FT_TO_M
        except ValueError:
            self.logger.error("Error processing: " + ','.join(fields))
            return

        self.emit('new-pressure')

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

        # Emit signal if alarm level has increased
        if self.flarm_alarm_level > old_alarm_level:
            self.emit("flarm-alarm")

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

        self.emit('new-pressure')

    def proc_flac(self, fields):
        """Process FLARM ack - Send the next TP in the task declaration"""
        if fields[FLAC_QUERY_TYPE] != 'A':
            # Ignore everything except FLARM answers
            return

        # Write next TP (if any) from declaration
        if fields[FLAC_KEY] in ('NEWTASK', 'ADDWP') and self.task_declaration:
            self.write(self.task_declaration.pop())

    def proc_unknown(self, fields):
        """Do nothing for unknown sentence"""
        pass

    def declare_task(self, tp_list):
        """Create task declaration and send to FLARM"""
        # Create list of NMEA waypoints
        declaration = ["$PFLAC,S,ADDWP,0000000N,00000000W,Takeoff\r\n"]
        for tp in tp_list:
            wp = str(tp['waypoint_id'])
            lat = "%02d%02d%03d%s" % dmm(tp['latitude'], 'NS')
            lon = "%03d%02d%03d%s" % dmm(tp['longitude'], 'EW')
            nmea = "$PFLAC,S,ADDWP,%s,%s,%s\r\n" % (lat, lon, wp)
            declaration.append(nmea)
        declaration.append("$PFLAC,S,ADDWP,0000000N,00000000W,Land\r\n")

        # Reverse and store
        declaration.reverse()
        self.task_declaration = declaration

        # Write start of task to FLARM
        self.write("$PFLAC,S,NEWTASK,Task\r\n")
