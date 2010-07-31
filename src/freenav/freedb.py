"""This module provides a database management wrapper for the freenav
programs
"""

import math
import os
import time

import sqlite3

GPS_DEVS = ['Serial-1', 'Serial-2', 'Bluetooth-1', 'Bluetooth-2']

def dict_factory(cursor, row):
    """Row factory for database"""
    column_dict = {}
    for idx, col in enumerate(cursor.description):
        column_dict[col[0]] = row[idx]
    return column_dict

SCHEMA = {
    'Projection': [
        ('parallel1', 'REAL'), ('parallel2', 'REAL'),
        ('latitude', 'REAL'), ('longitude', 'REAL')],

    'Waypoints': [
        ('id', 'TEXT'), ('name', 'TEXT'), ('x', 'INTEGER'), ('y', 'INTEGER'),
        ('latitude', 'REAL'), ('longitude', 'REAL'), ('altitude', 'INTEGER'),
        ('turnpoint', 'TEXT'), ('comment', 'TEXT')],

    'Airspace': [
        ('id', 'TEXT'), ('name', 'TEXT'), ('base', 'TEXT'), ('top', 'TEXT'),
        ('x_min', 'INTEGER'), ('y_min', 'INTEGER'),
        ('x_max', 'INTEGER'), ('y_max', 'INTEGER')],

    'Airspace_Lines': [
        ('airspace_id', 'TEXT'), ('x1', 'INTEGER'), ('y1', 'INTEGER'),
        ('x2', 'INTEGER'), ('y2', 'INTEGER')],

    # Start and length are in radians. Zero angle is along x-axis, positive
    # angles are anti-clockwise (towards y-axis)
    'Airspace_Arcs': [
        ('airspace_id', 'TEXT'), ('x', 'INTEGER'), ('y', 'INTEGER'),
        ('radius', 'INTEGER'), ('start', 'REAL'), ('length', 'REAL')],

    'Tasks' : [('id', 'INTEGER'), ('aat_flag', 'INTEGER')],

    # Angles are degrees relative to North, increasing clockwise
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
    """Database wrapper class"""
    def __init__(self, db_file=''):
        """Class initialisation"""
        if not db_file:
            db_file = os.path.join(os.getenv('HOME'), '.freeflight', 'free.db')
        self.db = sqlite3.connect(db_file)
        self.db.row_factory = dict_factory
        self.cursor = self.db.cursor()

    def create_table(self, table_name, columns):
        """Utility function to create table from SCHEMA information"""
        col_str = ','.join([cname + ' ' + ctype for (cname, ctype) in columns])
        sql = 'CREATE TABLE %s (%s)' % (table_name, col_str)
        self.cursor.execute(sql)

    def commit(self):
        """Commit changes"""
        self.db.commit()

    def vacuum(self):
        """Do a bit of hoovering"""
        self.cursor.execute('vacuum')

    def create(self, parallel1, parallel2, latitude, longitude):
        """Create tables from schema, add initial values and indices"""
        for table_name in SCHEMA:
            self.create_table(table_name, SCHEMA[table_name])

        sql = '''INSERT INTO Projection
              (parallel1, parallel2, latitude, longitude)
              VALUES (?, ?, ?, ?)'''
        self.cursor.execute(sql, (parallel1, parallel2, latitude, longitude))

        sql = '''INSERT INTO Settings
              (task_id, qne, qne_timestamp, takeoff_pressure_level,
               takeoff_time, takeoff_altitude, start_time, bugs, ballast,
               safety_height, gps_device)
              VALUES (0, 0, 0, 0, 0, 0, 0, 1.0, 1.0, 0, ?)'''
        self.cursor.execute(sql, (GPS_DEVS[0], ))

        self.cursor.execute('CREATE INDEX X_Index ON Waypoints (x)')
        self.cursor.execute('CREATE INDEX Y_Index ON Waypoints (y)')
        self.cursor.execute('CREATE INDEX Xmin_Index ON Airspace (x_min)')
        self.cursor.execute('CREATE INDEX Xmax_Index ON Airspace (x_max)')
        self.cursor.execute('CREATE INDEX Ymin_Index ON Airspace (y_min)')
        self.cursor.execute('CREATE INDEX Ymax_Index ON Airspace (y_max)')

        self.commit()

    def get_projection(self):
        """Get projection values"""
        sql = 'SELECT * FROM Projection'
        self.cursor.execute(sql)
        return self.cursor.fetchone()

    def delete_waypoints(self):
        """Delete all the waypoints"""
        self.cursor.execute('DELETE FROM Waypoints')

    def insert_waypoint(self, name, wp_id, x, y, latitude, longitude, altitude,
                        turnpoint, comment):
        """Add a new waypoint"""
        sql = '''INSERT INTO Waypoints
            (name, id, x, y, latitude, longitude, altitude, turnpoint, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (name, wp_id, x, y, latitude, longitude,
                                  altitude, turnpoint, comment))

    def get_waypoint(self, wp_id):
        """Return waypoint data"""
        sql = 'SELECT * FROM Waypoints WHERE id=?'
        self.cursor.execute(sql, (wp_id,))
        return self.cursor.fetchone()

    def get_waypoint_list(self):
        """Return a list of all waypoints"""
        sql = 'SELECT * FROM Waypoints ORDER BY id'
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def get_area_waypoint_list(self, x, y, width, height):
        """Return list of waypoints filtered by area"""
        sql = 'SELECT * FROM Waypoints WHERE x>? AND x<? AND y>? AND y<?'
        self.cursor.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.cursor.fetchall()

    def delete_landables(self):
        """Delete all the landing fields"""
        self.cursor.execute('DELETE FROM Landables')

    def insert_landable(self, name, wp_id, x, y, altitude):
        """Add a new landing field"""
        sql = '''INSERT INTO Landables (name, id, x, y, altitude)
              VALUES (?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (name, wp_id, x, y, altitude))

    def get_landable_list(self):
        """Return a list of all landing fields"""
        sql = 'SELECT * FROM Landables'
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def get_area_airspace(self, x, y, width, height):
        """Return list of airspace filtered by area"""
        sql = '''SELECT * FROM Airspace
              WHERE ? < x_max AND ? > x_min AND ? < y_max AND ? > y_min'''
        self.cursor.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.cursor.fetchall()

    def get_airspace_lines(self, wp_id):
        """Return list of boundary lines for given airspace id"""
        sql = 'SELECT * FROM Airspace_Lines WHERE airspace_id=?'
        self.cursor.execute(sql, (wp_id,))
        return self.cursor.fetchall()

    def get_airspace_arcs(self, wp_id):
        """Return list of boundary arcs for given airspace id"""
        sql = 'SELECT * FROM Airspace_Arcs WHERE airspace_id=?'
        self.cursor.execute(sql, (wp_id,))
        return self.cursor.fetchall()

    def set_task(self, task, wp_id=0):
        """Delete old task data and add new"""
        sql = 'DELETE FROM Tasks WHERE id=? '
        self.cursor.execute(sql, (wp_id,))
        sql = 'DELETE FROM Turnpoints WHERE task_id=?'
        self.cursor.execute(sql, (wp_id,))

        sql = 'INSERT INTO Tasks (id, aat_flag) VALUES (?, ?)'
        self.cursor.execute(sql, (wp_id, 0))

        sql = '''INSERT INTO Turnpoints (task_id, task_index, Waypoint_Id,
              radius1, angle1, radius2, angle2, direction, angle12,
              mindistx, mindisty)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        for tp_num, tp in enumerate(task):
            self.cursor.execute(sql, (wp_id, tp_num, tp['waypoint_id'],
                                 tp['radius1'], tp['angle1'],
                                 tp['radius2'], tp['angle2'],
                                 tp['direction'], tp['angle12'],
                                 tp['mindistx'], tp['mindisty']))

    def get_task(self, wp_id=-1):
        """Get turnpoints for specified task"""
        if wp_id == -1:
            # Default is to get active task
            wp_id = self.get_active_task_id()

        sql = '''SELECT * FROM Turnpoints INNER JOIN Waypoints
              ON Turnpoints.waypoint_id=Waypoints.id
              WHERE Turnpoints.task_id = ? ORDER BY Turnpoints.task_index'''
        self.cursor.execute(sql, (wp_id,))
        return self.cursor.fetchall()

    def get_active_task_id(self):
        """Get the current task id"""
        sql = 'SELECT * FROM Settings'
        self.cursor.execute(sql)
        return self.cursor.fetchone()['task_id']

    def set_active_task_id(self, task_id):
        """Set the current task id"""
        sql = 'UPDATE Settings SET task_id = ?'
        self.cursor.execute(sql, (task_id,))

    def delete_airspace(self):
        """Delete all airspace data"""
        self.cursor.execute('DELETE FROM Airspace')
        self.cursor.execute('DELETE FROM Airspace_Lines')
        self.cursor.execute('DELETE FROM Airspace_Arcs')

    def insert_airspace(self, as_id, name, base, top, xmin, ymin, xmax, ymax):
        """Insert new airspace record"""
        sql = '''INSERT INTO Airspace
              (id, name, base, top, x_min, y_min, x_max, y_max)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (as_id, name, base, top,
                                  int(xmin), int(ymin), int(xmax), int(ymax)))

    def insert_airspace_line(self, as_id, x1, y1, x2, y2):
        """Insert an airspace line segment"""
        sql = '''INSERT INTO Airspace_Lines (airspace_id, x1, y1, x2, y2)
              VALUES (?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (as_id, int(x1), int(y1), int(x2), int(y2)))

    def insert_airspace_arc(self, as_id, x, y, radius, start_angle, arc_length):
        """Insert an airspace arc segment"""
        sql = '''INSERT INTO Airspace_Arcs
              (airspace_id, x, y, radius, start, length)
              VALUES (?, ?, ?, ?, ?, ?)'''
        self.cursor.execute(sql, (as_id, int(x), int(y), int(radius),
                                  start_angle, arc_length))

    def insert_airspace_circle(self, as_id, x, y, radius):
        """Convenience function to add a 2 PI radian arc"""
        self.insert_airspace_arc(as_id, x, y, radius, 0, 2 * math.pi)

    def set_qne(self, qne):
        """Set QNE value and date"""
        time_stamp = int(time.time())
        sql = 'UPDATE Settings SET qne=?, qne_timestamp=?'
        self.cursor.execute(sql, (qne, time_stamp))

    def clear_qne(self):
        """Clear QNE data"""
        self.cursor.execute("UPDATE Settings SET qne_timestamp=0")

    def get_settings(self):
        """Returns setting values"""
        self.cursor.execute('SELECT * FROM Settings')
        return self.cursor.fetchone()

    def set_takeoff(self, tim, level, altitude):
        """Set takeoff pressure level, time and altitude"""
        sql = '''UPDATE Settings Set takeoff_pressure_level=?,
              takeoff_time=?, takeoff_altitude=?'''
        self.cursor.execute(sql, (level, tim, altitude))

    def set_start(self, tim):
        """Set start time"""
        sql = "UPDATE Settings Set start_time=?"
        self.cursor.execute(sql, (tim,))

    def set_gps_dev(self, gps_dev):
        """Set GPS device string"""
        sql = "UPDATE Settings SET gps_device=?"
        self.cursor.execute(sql, (gps_dev,))

    def set_bugs(self, bugs):
        """Set bugs value"""
        sql = "UPDATE Settings SET bugs=?"
        self.cursor.execute(sql, (bugs,))

    def set_ballast(self, ballast):
        """Set ballast value"""
        sql = "UPDATE Settings SET ballast=?"
        self.cursor.execute(sql, (ballast,))

    def set_safety_height(self, safety_height):
        """Set safety height value"""
        sql = "UPDATE Settings SET safety_height=?"
        self.cursor.execute(sql, (safety_height,))

    def get_nearest_landables(self, xpos, ypos):
        """Get list of landing fields sorted by distance"""
        sql = 'SELECT * FROM Landables'
        self.cursor.execute(sql)
        wps = self.cursor.fetchall()

        def dist_cmp(arg1, arg2):
            """Compare function for sort"""
            res = (((arg1['x'] - xpos)**2 + (arg1['y'] - ypos)**2) -
                   ((arg2['x'] - xpos)**2 + (arg2['y'] - ypos)**2))
            if res > 0:
                return 1
            elif res < 0:
                return -1
            else:
                return 0

        wps.sort(dist_cmp)
        return wps
