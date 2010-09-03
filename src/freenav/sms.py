"""Send SMS message via a Bluetooth connected mobile phone"""

import bluetooth
import logging

RF_COMM_CHANNEL = 1

class Sms:
    def __init__(self, bt_addr, bt_channel=RF_COMM_CHANNEL):
        """Initialise class variables"""
        self.bt_addr = bt_addr
        self.bg_channel = bt_channel

        self.bt_sock = None
        self.phonebook = {}

        self.logger = logging.getLogger('freelog')

    def add_phonebook_entry(self, name, phone_number, email_address=None):
        """Add entry to phone book"""
        self.phonebook[name] = {'phone_number': phone_number,
                                'email_address': email_address}

    def connect(self):
        """Connect to phone and set SMS text mode"""
        self.bt_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        try:
            # Connect to the phone
            self.bt_sock.connect((self.bt_addr, RF_COMM_CHANNEL))

            # Set SMS text mode
            self.bt_sock.send("AT+CMGF=1\r")
        except bluetooth.BluetoothError:
            self.logger.warning("Can't connect to bluetooth " + self.bt_addr)
            self.bt_sock = None

        return self.bt_sock

    def disconnect(self):
        """Close connection to phone"""
        if self.bt_sock:
            try:
                self.bt_sock.close()
            except bluetooth.BluetoothError:
                pass
            self.bt_sock = None

    def send(self, name, msg):
        """Send an SMS message to specified phonebook entry"""
        if self.bt_sock is None:
            self.logger.error("No bluetooth connection, can't send message")
            return

        # SMS send command
        try:
            pb_entry = self.phonebook[name]
        except KeyError:
            self.logger.error("Unknown SMS name: " + name)
            return

        sms_at_command = "AT+CMGS=\"%s\"\r" % pb_entry['phone_number']

        # Prepend email address, append CTRL-Z
        if pb_entry['email_address']:
            sms_txt = pb_entry['email_address'] + " " + msg + "\x1a"
        else:
            sms_txt = msg + "\x1a"

        # Send commands to phone
        try:
            self.bt_sock.send(sms_at_command)
            self.bt_sock.send(sms_txt)
        except bluetooth.BluetoothError:
            self.logger.error("Send SMS message failed")
            self.disconnect()

    def send_all(self, msg):
        """Send SMS message to all entries in the phonebook"""
        for name in self.phonebook:
            self.send(name, msg)
