"""NMEA interface module"""
# XXX Deal with errors

import math
import time

import bluetooth
import gio
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
RMC_SPEED = 7
RMC_TRACK = 8

KTS_TO_MPS = 1852 / 3600.0
FT_TO_M = 12 * 25.4 / 1000

RF_COMM_CHANNEL = 1

def check_checksum(data_str, checksum_str=None):
    """Return True if calculated checksum matches given checksum"""
    if checksum_str:
        # Checksum is XOR of all characters in the data
        sum = 0
        for d in data_str:
            sum = sum ^ ord(d)

        if sum == int(checksum_str, 16):
            return True
        else:
            return False
    else:
        # No checksum, so pass anyway
        return True

class FreeNmea(gobject.GObject):
    def __init__(self):
        gobject.GObject.__init__(self)

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
                           'PFLAU': self.proc_flau}

        # Initialise a few variables
        self.flarm_alarm_level = 0
        self.time = -1

    def open(self, dev, baud_rate):
        """Open NMEA device"""
        if dev[0] == '/':
            self.open_serial(dev, baud_rate)
        else:
            self.open_bt(dev)

    def open_bt(self, addr):
        """Open a bluetooth connection"""
        self.bt_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        self.bt_sock.connect((addr, RF_COMM_CHANNEL))

        # Create input stream and add I/O watch
        self.stream = gio.unix.InputStream(self.bt_sock, True)
        gobject.io.io_add_watch(self.bt_sock, gobject.IO_IN, self.io_callback)

    def open_serial(self, dev_path, baudrate=None):
        """Open serial device"""
        if baudrate:
            ser = serial.Serial(dev_path, baudrate=baudrate, timeout=0)
        else:
            ser = serial.Serial(dev_path, timeout=0)

        # Flush stale data
        ser.flushInput()

        # Create input stream and add I/O watch
        self.stream = gio.unix.InputStream(ser.fileno(), True)
        gobject.io_add_watch(ser.fileno(), gobject.IO_IN, self.io_callback)

    def close(self):
        # Close input stream
        self.stream.close()

    def io_callback(self, *args):
        """Callback on NMEA input data"""
        # Prepend new data to old and parse NMEA data
        buf = ''.join([self.buf, self.stream.read()])
        self.buf = self.parse_nmea(buf)

        return True

    def parse_nmea(self, buf):
        """Extract NMEA data from data buffer"""
        # Split data buffer at first newline
        sentence, separator, remainder = buf.partition("\r\n")

        if separator:
            print sentence

            if sentence[0] == '$':
                # Split sentence into message body and checksum
                body_checksum = sentence[1:].split('*')

                if check_checksum(*body_checksum):
                    # Split body into comma separated fields and process
                    fields = body_checksum[0].split(',')
                    self.proc_funcs.get(fields[0], self.proc_unknown)(fields)
                else:
                    print "Checksum error"
            else:
                print "Incorrect sentence header"

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
            print "Error processing GGA"
            return

        if gga_time == self.time:
            self.emit('new-position')
        else:
            self.time = gga_time

    def proc_rmc(self, fields):
        """Process RMC GPS data. Time, speed and track"""
        status = fields[RMC_STATUS]
        if status != 'A':
            # Bail out early if inactive fix
            return

        try:
            tim = fields[GGA_TIME]
            rmc_time = int(tim[:2]) * 3600 + int(tim[2:4]) * 60 + int(tim[4:6])

            self.speed = float(fields[RMC_SPEED]) * KTS_TO_MPS

            self.track = math.radians(float(fields[RMC_TRACK]))
        except ValueError:
            print "Error processing RMC"
            return

        if rmc_time == self.time:
            self.emit('new-position')
        else:
            self.time = rmc_time

    def proc_grmz(self, fields):
        """Process pressure altitude data"""
        try:
            self.pressure_alt = int(fields[1]) * FT_TO_M
        except ValueError:
            print "Error processing GRMZ"
            return

        self.emit('new-pressure')

    def proc_flau(self, fields):
        """Process FLARM alarm data"""
        old_alarm_level = self.flarm_alarm_level

        try:
            self.flarm_alarm_level = int(fields[5])
            self.flarm_relative_bearing = int(fields[6])
            self.flarm_alarm_type = int(fields[7])
        except ValueError:
            print "Error processing FLAU"
            return

        # Emit signal if alarm level has increased
        if self.flarm_alarm_level > old_alarm_level:
            self.emit("flarm-alarm")

    def proc_unknown(self, fields):
        """Do nothing for unknown sentence"""
        pass

def flarm_cb(gps):
    print "flarm", gps.flarm_alarm_direction

def posn_cb(gps):
    print "posn", gps.num_satellites

if __name__ == '__main__':
    gps = Gps()
    gps.open_serial('/tmp/gps')
    #gps.connect("flarm-alarm", flarm_cb)
    gps.connect('new-position', posn_cb)
    gtk.main()
