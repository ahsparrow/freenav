""" Module to interface to a NMEA data source"""

import bluetooth
import gobject
import serial

import nmeaparser
import util

RF_COMM_CHANNEL = 1

def make_decl_expect(nmea):
    decl =  "$" + nmea + "*" + nmeaparser.calc_checksum_str(nmea) + "\r\n"
    expect = nmea.replace(",S,", ",A,")
    return (decl, expect)

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
        gobject.signal_new("flarm-traffic", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])
        gobject.signal_new("flarm-command", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_PYOBJECT])
        gobject.signal_new("flarm-declare", FreeNmea, gobject.SIGNAL_ACTION,
                           gobject.TYPE_NONE, [gobject.TYPE_BOOLEAN])

        self.nmea_dev = None

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
        self.io_source = gobject.io_add_watch(bt_sock, gobject.IO_IN,
                                              self.bt_io_callback)

        self.nmea_dev = bt_sock
        self.write_func = bt_sock.send

    def open_serial(self, dev_path, baudrate=None):
        """Open serial device"""
        if baudrate:
            ser = serial.Serial(dev_path, baudrate=baudrate, timeout=0)
        else:
            ser = serial.Serial(dev_path, timeout=0)

        # Flush stale data
        ser.flushInput()

        # Add I/O watch
        self.io_source = gobject.io_add_watch(ser, gobject.IO_IN,
                                              self.ser_io_callback)
        self.nmea_dev = ser
        self.write_func = ser.write

    def close(self):
        """Close input device"""
        if self.nmea_dev:
            gobject.source_remove(self.io_source)
            self.nmea_dev.close()

            self.nmea_dev = None

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

    def flac_callback(self):
        if self.nmea_declaration:
            decl, expect = self.nmea_declaration.pop(0)
            self.parser.expect(expect, self.flac_callback)
            self.write_func(decl)
        else:
            # Reset FLARM and signal end of declaration
            self.write_func("$PFLAR,0\r\n")
            self.emit('flarm-declare', True)

    def declare(self, declaration):
        """Start sending task declaration to FLARM"""
        nmea_decl = ["PFLAC,S,NEWTASK,Task"]
        nmea_decl.append("PFLAC,S,ADDWP,0000000N,00000000W,Takeoff")

        for tp in declaration:
            lat = ("%(deg)02d%(min)02d%(dec)03d%(ns)s" %
                   util.dmm(tp['latitude'], 3))
            lon = ("%(deg)03d%(min)02d%(dec)03d%(ew)s" %
                   util.dmm(tp['longitude'], 3))

            nmea_decl.append(
                "PFLAC,S,ADDWP,%s,%s,%s" % (lat, lon, tp['id']))

        nmea_decl.append("PFLAC,S,ADDWP,0000000N,00000000W,Land")
        self.nmea_declaration = map(make_decl_expect, nmea_decl)

        # Write first part of declaration to FLARM
        self.write_func("\r\n")
        decl, expect = self.nmea_declaration.pop(0)
        self.parser.expect(expect, self.flac_callback)
        self.write_func(decl)
