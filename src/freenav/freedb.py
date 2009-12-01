#!/usr/bin/env python
#
# Database management class
#

import os

import sqlite3

SCHEMA = {
    'Projection': [
        ('Parallel1', 'REAL'), ('Parallel2', 'REAL'),
        ('Latitude', 'REAL'), ('Longitude', 'REAL')],

    'Waypoints': [
        ('Id', 'TEXT'), ('Name', 'TEXT'), ('X', 'INTEGER'), ('Y', 'INTEGER'),
        ('Altitude', 'INTEGER'), ('Turnpoint', 'TEXT'),
        ('Landable_Flag', 'INTEGER'), ('Comment', 'TEXT')],

    'Airspace': [
        ('Id', 'TEXT'), ('Name', 'TEXT'), ('Base', 'TEXT'), ('Top', 'TEXT'),
        ('X_Min', 'INTEGER'), ('Y_Min', 'INTEGER'),
        ('X_Max', 'INTEGER'), ('Y_Max', 'INTEGER')],

    'Airspace_Lines': [
        ('Airspace_Id', 'TEXT'), ('X1', 'INTEGER'), ('Y1', 'INTEGER'),
        ('X2', 'INTEGER'), ('Y2', 'INTEGER')],

    'Airspace_Arcs': [
        ('Airspace_Id', 'TEXT'), ('X', 'INTEGER'), ('Y', 'INTEGER'),
        ('Radius', 'INTEGER'), ('Start', 'INTEGER'), ('Length', 'INTEGER')],

    'Tasks' : [('Id', 'INTEGER'), ('AAT_Flag', 'INTEGER')],

    'Turnpoints': [
        ('Task_Id', 'INTEGER'), ('Task_Index', 'INTEGER'),
        ('Waypoint_Id', 'TEXT'),
        ('Radius1', 'INTEGER'), ('Angle1', 'REAL'),
        ('Radius2', 'INTEGER'), ('Angle2', 'REAL'),
        ('Direction', 'TEXT'), ('Angle12', 'REAL')],

    'Config': [('Task_Id', 'INTEGER')]}

class Freedb:
    def __init__(self, file=''):
        if not file:
            file = os.path.join(os.getenv('HOME'), '.freeflight', 'free.db')
        self.db = sqlite3.connect(file)
        self.db.row_factory = sqlite3.Row
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
              (Parallel1, Parallel2, Latitude, Longitude)
              VALUES (?, ?, ?, ?)'''
        self.c.execute(sql, (parallel1, parallel2, latitude, longitude))

        sql = 'INSERT INTO Config (Task_Id) VALUES (0)'
        self.c.execute(sql)

        self.c.execute('CREATE INDEX X_Index ON Waypoints (X)')
        self.c.execute('CREATE INDEX Y_Index ON Waypoints (Y)')
        self.c.execute('CREATE INDEX Xmin_Index ON Airspace (X_Min)')
        self.c.execute('CREATE INDEX Xmax_Index ON Airspace (X_Max)')
        self.c.execute('CREATE INDEX Ymin_Index ON Airspace (Y_Min)')
        self.c.execute('CREATE INDEX Ymax_Index ON Airspace (Y_Max)')

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
              (Name, Id, X, Y, Altitude, Turnpoint, Comment, Landable_Flag)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql, (name, id, x, y,altitude, turnpoint, comment,
                             landable_flag))

    def get_waypoint(self, id):
        """Return waypoint data"""
        sql = 'SELECT * FROM Waypoints WHERE Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def get_waypoint_list(self):
        """Return a list of all waypoints"""
        sql = 'SELECT * FROM Waypoints ORDER BY Id'
        self.c.execute(sql)
        return self.c.fetchall()

    def get_area_waypoint_list(self, x, y, width, height):
        """Return list of waypoints filtered by area"""
        sql = 'SELECT * FROM Waypoints WHERE X>? AND X<? AND Y>? AND Y<?'
        self.c.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.c.fetchall()

    def get_area_airspace(self, x, y, width, height):
        """Return list of airspace filtered by area"""
        sql = '''SELECT * FROM Airspace
              WHERE ? < X_Max AND ? > X_Min AND ? < Y_Max AND ? > Y_Min'''
        self.c.execute(sql, (x - width/2, x + width/2,
                             y - height/2, y + height/2))
        return self.c.fetchall()

    def get_airspace_lines(self, id):
        """Return list of boundary lines for given airspace id"""
        sql = 'SELECT * FROM Airspace_Lines WHERE Airspace_Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def get_airspace_arcs(self, id):
        """Return list of boundary arcs for given airspace id"""
        sql = 'SELECT * FROM Airspace_Arcs WHERE Airspace_Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def set_task(self, task, id=0):
        """Delete old task data and add new"""
        sql = 'DELETE FROM Tasks WHERE Id=? '
        self.c.execute(sql, (id,))
        sql = 'DELETE FROM Turnpoints WHERE Task_Id=?'
        self.c.execute(sql, (id,))

        sql = 'INSERT INTO Tasks (Id, AAT_Flag) VALUES (?, ?)'
        self.c.execute(sql, (id, 0))

        sql = '''INSERT INTO Turnpoints (Task_Id, Task_Index, Waypoint_Id,
              Radius1, Angle1, Radius2, Angle2, Direction, Angle12)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''
        for tp_num, tp in enumerate(task):
            self.c.execute(sql, (id, tp_num, tp['waypoint_id'],
                                 tp['radius1'], tp['angle1'],
                                 tp['radius2'], tp['angle2'],
                                 tp['direction'], tp['angle12']))

    def get_task(self, id=0):
        """Get turnpoints for specified task"""
        sql = '''SELECT * FROM Turnpoints INNER JOIN Waypoints
              ON Turnpoints.Waypoint_Id=Waypoints.Id
              WHERE Turnpoints.Task_Id = ? ORDER BY Turnpoints.Task_Index'''
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def get_active_task_id(self):
        """Get the current task id"""
        sql = 'SELECT Task_Id FROM Config'
        self.c.execute(sql)
        return self.c.fetchone()[0]

    def set_active_task_id(self, task_id):
        """Set the current task id"""
        sql = 'UPDATE Config SET Task_Id = ?'
        self.c.execute(sql, (task_id,))

    def delete_airspace(self):
        """Delete all airspace data"""
        self.c.execute('DELETE FROM Airspace')
        self.c.execute('DELETE FROM Airspace_Lines')
        self.c.execute('DELETE FROM Airspace_Arcs')

    def insert_airspace(self, id, name, base, top, xmin, ymin, xmax, ymax):
        """Insert new airspace record"""
        sql = '''INSERT INTO Airspace
              (Id, Name, Base, Top, X_Min, Y_Min, X_Max, Y_Max)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql,
            (id, name, base, top, int(xmin), int(ymin), int(xmax), int(ymax)))

    def insert_airspace_line(self, id, x1, y1, x2, y2):
        """Insert an airspace line segment"""
        sql = '''INSERT INTO Airspace_Lines (Airspace_Id, X1, Y1, X2, Y2)
              VALUES (?, ?, ?, ?, ?)'''
        self.c.execute(sql, (id, int(x1), int(y1), int(x2), int(y2)))

    def insert_airspace_arc(self, id, x, y, radius, startAngle, arcLength):
        """Insert an airspace arc segment"""
        sql = '''INSERT INTO Airspace_Arcs
              (Airspace_Id, X, Y, Radius, Start, Length)
              VALUES (?, ?, ?, ?, ?, ?)'''
        self.c.execute(sql, (id, int(x), int(y), int(radius),
                             int(startAngle * 64), int(arcLength * 64)))

    def insert_airspace_circle(self, id, x, y, radius):
        """Convenience function to add a 360 degree arc"""
        self.insert_airspace_arc(id, x, y, radius, 0, 360)
