#!/usr/bin/env python
#
# Database management class
#

import os
import time

import sqlite3

GPS_DEVS = ['Serial-1', 'Serial-2', 'Bluetooth-1', 'Bluetooth-2']

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

SCHEMA = {
    'Projection': [
        ('parallel1', 'REAL'), ('parallel2', 'REAL'),
        ('latitude', 'REAL'), ('longitude', 'REAL')],

    'Waypoints': [
        ('id', 'TEXT'), ('name', 'TEXT'), ('x', 'INTEGER'), ('y', 'INTEGER'),
        ('altitude', 'INTEGER'), ('turnpoint', 'TEXT'), ('comment', 'TEXT')],

    'Airspace': [
        ('id', 'TEXT'), ('name', 'TEXT'), ('base', 'TEXT'), ('top', 'TEXT'),
        ('x_min', 'INTEGER'), ('y_min', 'INTEGER'),
        ('x_max', 'INTEGER'), ('y_max', 'INTEGER')],

    'Airspace_Lines': [
        ('airspace_id', 'TEXT'), ('x1', 'INTEGER'), ('y1', 'INTEGER'),
        ('x2', 'INTEGER'), ('y2', 'INTEGER')],

    'Airspace_Arcs': [
        ('airspace_id', 'TEXT'), ('x', 'INTEGER'), ('y', 'INTEGER'),
        ('radius', 'INTEGER'), ('start', 'INTEGER'), ('length', 'INTEGER')],

    'Tasks' : [('id', 'INTEGER'), ('aat_flag', 'INTEGER')],

    'Turnpoints': [
        ('task_id', 'INTEGER'), ('task_index', 'INTEGER'),
        ('waypoint_id', 'TEXT'),
        ('radius1', 'INTEGER'), ('angle1', 'REAL'),
        ('radius2', 'INTEGER'), ('angle2', 'REAL'),
        ('direction', 'TEXT'), ('angle12', 'REAL'),
        ('mindistx', 'INTEGER'), ('mindisty', 'INTEGER')],

    'Landables': [
        ('id', 'TEXT'), ('name', 'TEXT'),
        ('x', 'INTEGER'), ('y', 'INTEGER'), ('altitude', 'INTEGER')],

    'Settings': [('task_id', 'INTEGER'),
                 ('qne', 'REAL'),
                 ('qne_timestamp', 'INTEGER'),
                 ('takeoff_pressure_level', 'REAL'),
                 ('takeoff_altitude', 'REAL'),
                 ('takeoff_time', 'INTEGER'),
                 ('start_time', 'INTEGER'),
                 ('bugs', 'REAL'),
                 ('ballast', 'REAL'),
                 ('safety_height', 'INTEGER'),
                 ('gps_device', 'TEXT')]}

class Freedb:
    def __init__(self, file=''):
        if not file:
            file = os.path.join(os.getenv('HOME'), '.freeflight', 'free.db')
        self.db = sqlite3.connect(file)
        self.db.row_factory = dict_factory
        self.c = self.db.cursor()

    def create_table(self, table_name, columns):
        """Utility function to create table from SCHEMA information"""
        col_str = ','.join([cname + ' ' + ctype for (cname, ctype) in columns])
        sql = 'CREATE TABLE %s (%s)' % (table_name, col_str)
        self.c.execute(sql)

    def commit(self):
        self.db.commit()

    def vacuum(self):
        self.c.execute('vacuum')

    def create(self, parallel1, parallel2, latitude, longitude):
        """Create tables from schema, add initial values and indices"""
        for table_name in SCHEMA:
            self.create_table(table_name, SCHEMA[table_name])

        sql = '''INSERT INTO Projection
              (parallel1, parallel2, latitude, longitude)
              VALUES (?, ?, ?, ?)'''
        self.c.execute(sql, (parallel1, parallel2, latitude, longitude))

        sql = '''INSERT INTO Settings
              (task_id, qne, qne_timestamp, takeoff_pressure_level,
               takeoff_time, takeoff_altitude, start_time, bugs, ballast,
               safety_height, gps_device)
              VALUES (0, 0, 0, 0, 0, 0, 0, 1.0, 1.0, 0, ?)'''
        self.c.execute(sql, (GPS_DEVS[0], ))

        self.c.execute('CREATE INDEX X_Index ON Waypoints (x)')
        self.c.execute('CREATE INDEX Y_Index ON Waypoints (y)')
        self.c.execute('CREATE INDEX Xmin_Index ON Airspace (x_min)')
        self.c.execute('CREATE INDEX Xmax_Index ON Airspace (x_max)')
        self.c.execute('CREATE INDEX Ymin_Index ON Airspace (y_min)')
        self.c.execute('CREATE INDEX Ymax_Index ON Airspace (y_max)')

        self.commit()

    def get_projection(self):
        """Get projection values"""
        sql = 'SELECT * FROM Projection'
        self.c.execute(sql)
        return self.c.fetchone()

    def delete_waypoints(self):
        """Delete all the waypoints"""
        self.c.execute('DELETE FROM Waypoints')

    def insert_waypoint(self, name, id, x, y, altitude, turnpoint, comment,
                        landable_flag):
        """Add a new waypoint"""
        sql = '''INSERT INTO Waypoints
              (name, id, x, y, altitude, turnpoint, comment)
              VALUES (?, ?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql, (name, id, x, y, altitude, turnpoint, comment))

    def get_waypoint(self, id):
        """Return waypoint data"""
        sql = 'SELECT * FROM Waypoints WHERE id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def get_waypoint_list(self):
        """Return a list of all waypoints"""
        sql = 'SELECT * FROM Waypoints ORDER BY id'
        self.c.execute(sql)
        return self.c.fetchall()

    def get_area_waypoint_list(self, x, y, width, height):
        """Return list of waypoints filtered by area"""
        sql = 'SELECT * FROM Waypoints WHERE x>? AND x<? AND y>? AND y<?'
        self.c.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.c.fetchall()

    def delete_landables(self):
        """Delete all the landing fields"""
        self.c.execute('DELETE FROM Landables')

    def insert_landable(self, name, id, x, y, altitude):
        """Add a new landing field"""
        sql = '''INSERT INTO Landables (name, id, x, y, altitude)
              VALUES (?, ?, ?, ?, ?)'''
        self.c.execute(sql, (name, id, x, y, altitude))

    def get_landable(self, id):
        """Return landing field data"""
        sql = 'SELECT * FROM Landable WHERE id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def get_landable_list(self):
        """Return a list of all landing fields"""
        sql = 'SELECT * FROM Landables'
        self.c.execute(sql)
        return self.c.fetchall()

    def get_area_airspace(self, x, y, width, height):
        """Return list of airspace filtered by area"""
        sql = '''SELECT * FROM Airspace
              WHERE ? < x_max AND ? > x_min AND ? < y_max AND ? > y_min'''
        self.c.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.c.fetchall()

    def get_airspace_lines(self, id):
        """Return list of boundary lines for given airspace id"""
        sql = 'SELECT * FROM Airspace_Lines WHERE airspace_id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def get_airspace_arcs(self, id):
        """Return list of boundary arcs for given airspace id"""
        sql = 'SELECT * FROM Airspace_Arcs WHERE airspace_id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def set_task(self, task, id=0):
        """Delete old task data and add new"""
        sql = 'DELETE FROM Tasks WHERE id=? '
        self.c.execute(sql, (id,))
        sql = 'DELETE FROM Turnpoints WHERE task_id=?'
        self.c.execute(sql, (id,))

        sql = 'INSERT INTO Tasks (id, aat_flag) VALUES (?, ?)'
        self.c.execute(sql, (id, 0))

        sql = '''INSERT INTO Turnpoints (task_id, task_index, Waypoint_Id,
              radius1, angle1, radius2, angle2, direction, angle12,
              mindistx, mindisty)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        for tp_num, tp in enumerate(task):
            self.c.execute(sql, (id, tp_num, tp['waypoint_id'],
                                 tp['radius1'], tp['angle1'],
                                 tp['radius2'], tp['angle2'],
                                 tp['direction'], tp['angle12'],
                                 tp['mindistx'], tp['mindisty']))

    def get_task(self, id=-1):
        """Get turnpoints for specified task"""
        if id == -1:
            # Default is to get active task
            id = self.get_active_task_id()

        sql = '''SELECT * FROM Turnpoints INNER JOIN Waypoints
              ON Turnpoints.waypoint_id=Waypoints.id
              WHERE Turnpoints.task_id = ? ORDER BY Turnpoints.task_index'''
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def get_active_task_id(self):
        """Get the current task id"""
        sql = 'SELECT * FROM Settings'
        self.c.execute(sql)
        return self.c.fetchone()['task_id']

    def set_active_task_id(self, task_id):
        """Set the current task id"""
        sql = 'UPDATE Settings SET task_id = ?'
        self.c.execute(sql, (task_id,))

    def delete_airspace(self):
        """Delete all airspace data"""
        self.c.execute('DELETE FROM Airspace')
        self.c.execute('DELETE FROM Airspace_Lines')
        self.c.execute('DELETE FROM Airspace_Arcs')

    def insert_airspace(self, id, name, base, top, xmin, ymin, xmax, ymax):
        """Insert new airspace record"""
        sql = '''INSERT INTO Airspace
              (id, name, base, top, x_min, y_min, x_max, y_max)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql,
            (id, name, base, top, int(xmin), int(ymin), int(xmax), int(ymax)))

    def insert_airspace_line(self, id, x1, y1, x2, y2):
        """Insert an airspace line segment"""
        sql = '''INSERT INTO Airspace_Lines (airspace_id, x1, y1, x2, y2)
              VALUES (?, ?, ?, ?, ?)'''
        self.c.execute(sql, (id, int(x1), int(y1), int(x2), int(y2)))

    def insert_airspace_arc(self, id, x, y, radius, startAngle, arcLength):
        """Insert an airspace arc segment"""
        sql = '''INSERT INTO Airspace_Arcs
              (airspace_id, x, y, radius, start, length)
              VALUES (?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql, (id, int(x), int(y), int(radius),
                             int(startAngle * 64), int(arcLength * 64)))

    def insert_airspace_circle(self, id, x, y, radius):
        """Convenience function to add a 360 degree arc"""
        self.insert_airspace_arc(id, x, y, radius, 0, 360)

    def set_qne(self, qne):
        """Set QNE value and date"""
        time_stamp = int(time.time())
        sql = 'UPDATE Settings SET qne=?, qne_timestamp=?'
        self.c.execute(sql, (qne, time_stamp))

    def clear_qne(self):
        """Clear QNE data"""
        self.c.execute("UPDATE Settings SET qne_timestamp=0")

    def get_settings(self):
        """Returns setting values"""
        self.c.execute('SELECT * FROM Settings')
        return self.c.fetchone()

    def set_takeoff(self, tim, level, altitude):
        """Set takeoff pressure level, time and altitude"""
        sql = '''UPDATE Settings Set takeoff_pressure_level=?,
              takeoff_time=?, takeoff_altitude=?'''
        self.c.execute(sql, (level, tim, altitude))

    def set_start(self, tim):
        """Set start time"""
        sql = "UPDATE Settings Set start_time=?"
        self.c.execute(sql, (tim,))

    def set_gps_dev(self, gps_dev):
        """Set GPS device string"""
        sql = "UPDATE Settings SET gps_device=?"
        self.c.execute(sql, (gps_dev,))

    def set_bugs(self, bugs):
        """Set bugs value"""
        sql = "UPDATE Settings SET bugs=?"
        self.c.execute(sql, (bugs,))

    def set_ballast(self, ballast):
        """Set ballast value"""
        sql = "UPDATE Settings SET ballast=?"
        self.c.execute(sql, (ballast,))

    def set_safety_height(self, safety_height):
        """Set safety height value"""
        sql = "UPDATE Settings SET safety_height=?"
        self.c.execute(sql, (safety_height,))

    def get_nearest_landables(self, xpos, ypos):
        """Get list of landing fields sorted by distance"""
        sql = 'SELECT * FROM Landables'
        self.c.execute(sql)
        wps = self.c.fetchall()

        def dist_cmp(a, b):
            z = (((a['x'] - xpos)**2 + (a['y'] - ypos)**2) -
                 ((b['x'] - xpos)**2 + (b['y'] - ypos)**2))
            if z > 0:
                return 1
            elif z < 0:
                return -1
            else:
                return 0

        wps.sort(dist_cmp)
        return wps
