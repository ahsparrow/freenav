""" Module to interface to a NMEA data source"""

import bluetooth
import gobject
import serial

RF_COMM_CHANNEL = 1

class FreeNmea(gobject.GObject):
    """Class to process data from serial or bluetooth connected GPS"""
    def __init__(self, parser):
        """Class initialisation"""
        gobject.GObject.__init__(self)
        self.parser = parser

        # Register new signals
        gobject.signal_new("new-position", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])
        gobject.signal_new("new-pressure", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])
        gobject.signal_new("flarm-alarm", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])

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

        # Add I/O watch
        gobject.io_add_watch(bt_sock, gobject.IO_IN, self.bt_io_callback)
        self.nmea_dev = bt_sock

    def open_serial(self, dev_path, baudrate=None):
        """Open serial device"""
        if baudrate:
            ser = serial.Serial(dev_path, baudrate=baudrate, timeout=0)
        else:
            ser = serial.Serial(dev_path, timeout=0)

        # Flush stale data
        ser.flushInput()

        # Add I/O watch
        gobject.io_add_watch(ser, gobject.IO_IN, self.ser_io_callback)
        self.nmea_dev = ser

    def close(self):
        """Close input device"""
        self.nmea_dev.close()

    def ser_io_callback(self, *_args):
        """Callback on serial input data"""
        data = self.nmea_dev.read()
        self.proc_data(data)

        return True

    def bt_io_callback(self, *_args):
        """Callback on bluetooth input data"""
        data = self.nmea_dev.recv(1024)
        self.proc_data(data)

        return True

    def proc_data(self, data):
        """Process NMEA data, emit signal depending on result"""
        signals = self.parser.parse(data)
        for signal in signals:
            self.emit(signal, self.parser)

