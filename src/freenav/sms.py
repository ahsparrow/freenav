"""Send SMS message via a Bluetooth connected mobile phone"""

import bluetooth
import time

import freenav.util

RF_COMM_CHANNEL = 1

class Sms:
    def __init__(self, bt_addr, bt_channel=RF_COMM_CHANNEL):
        """Initialise class variables"""
        self.bt_addr = bt_addr
        self.bg_channel = bt_channel
        self.bt_sock = None

    def connect(self):
        """Connect to phone and set SMS text mode"""
        self.bt_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        try:
            # Connect to the phone
            self.bt_sock.connect((self.bt_addr, RF_COMM_CHANNEL))

            # Set SMS text mode
            self.bt_sock.send("AT+CMGF=1\r")
        except bluetooth.BluetoothError:
            self.bt_sock = None

        return self.bt_sock

    def send(self, phone_number, land_secs, latitude, longitude,
             email_address=None):
        """Send an SMS message

        phone_number - SMS recipient, format "+441234567890"
        land_secs - number of seconds since the epoch
        latitude, longitdue - radians
        email_address - (optional) email address string
        """

        if self.bt_sock is None:
            return

        # SMS send command
        sms_at_command = "AT+CMGS=\"%s\"\r" % phone_number

        # Create SMS message body
        tim_str = time.strftime("%H:%M", time.localtime(land_secs))
        lat_str = "%(deg)02d %(min)02d.%(dec)03d%(ns)s" % \
                freenav.util.dmm(latitude, 3)
        lon_str = "%(deg)03d %(min)02d.%(dec)03d%(ew)s" % \
                freenav.util.dmm(longitude, 3)
        msg = "LANDED %s %s %s" % (tim_str, lat_str, lon_str)

        # Prepend email address, append CTRL-Z
        if email_address:
            sms_txt = email_address + " " + msg + "\x1a"
        else:
            sms_txt = msg + "\x1a"
        print msg

        # Send commands to phone
        try:
            self.bt_sock.send(sms_at_command)
            self.bt_sock.send(sms_txt)
        except bluetooth.BluetoothError:
            self.close()

    def close(self):
        """Close connection to phone"""
        if self.bt_sock:
            try:
                self.bt_sock.close()
            except bluetooth.BluetoothError:
                pass
            self.bt_sock = None
