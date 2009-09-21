#!/usr/bin/env python
#
# Database management class
#

import os

#from pysqlite2 import dbapi2 as sqlite3
import sqlite3

SCHEMA = {
    'Projection': [
        ('Parallel1', 'REAL'), ('Parallel2', 'REAL'),
        ('Ref_Lat', 'REAL'), ('Ref_Lon', 'REAL')],

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
        ('Radius', 'INTEGER'), ('Start_Angle', 'INTEGER'),
        ('Arc_Length', 'INTEGER')],

    'Tasks': [
        ('Id', 'INTEGER'), ('Seq_Num', 'INTEGER'), ('Waypoint_Id', 'TEXT'),
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
        col_str = ','.join([cname + ' ' + ctype for (cname, ctype) in columns])
        sql = 'CREATE TABLE %s (%s)' % (table_name, col_str)
        self.c.execute(sql)

    def commit(self):
        self.db.commit()

    def vacuum(self):
        self.c.execute('vacuum')

    def create(self, parallel1, parallel2, refLat, refLon):
        """Create tables from schema and add initial values"""
        for table_name in SCHEMA:
            self.create_table(table_name, SCHEMA[table_name])

        sql = 'INSERT INTO Projection '\
              '(Parallel1, Parallel2, Ref_Lat, Ref_Lon) '\
              'VALUES (?, ?, ?, ?)'
        self.c.execute(sql, (parallel1, parallel2, refLat, refLon))

        sql = 'INSERT INTO Config (Task_Id) VALUES (0)'
        self.c.execute(sql)

        self.commit()

    def get_projection(self):
        sql = 'SELECT Parallel1, Parallel2, Ref_Lat, Ref_Lon FROM Projection'
        self.c.execute(sql)
        return self.c.fetchone()

    def delete_waypoints(self):
        """Delete all the waypoints"""
        self.c.execute('DELETE FROM Waypoints')

    def insert_waypoint(self, name, id, x, y, altitude, turnpoint, comment,
                        landable_flag):
        sql = 'INSERT INTO Waypoints '\
              '(Name, Id, X, Y, Altitude, Turnpoint, Comment, Landable_Flag) '\
              'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        self.c.execute(sql, (name, id, x, y,altitude, turnpoint, comment,
                             landable_flag))

    def get_waypoint(self, id):
        """Return waypoint data"""
        sql = 'SELECT X, Y, Altitude, Name, Turnpoint, Comment '\
              'FROM Waypoints WHERE Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def get_waypoint_list(self):
        """Return a list of waypoint Id's and names"""
        sql = 'SELECT Id, Name FROM Waypoints ORDER BY Id'
        self.c.execute(sql)
        return self.c.fetchall()

    def create_waypoint_indices(self):
        """Create waypoint indices on X and Y"""
        self.c.execute('CREATE INDEX X_Index ON Waypoints (X)')
        self.c.execute('CREATE INDEX Y_Index ON Waypoints (Y)')

    def set_task(self, task, id=0):
        sql = 'DELETE FROM Tasks WHERE Id=? '
        self.c.execute(sql, (id,))

        sql = 'INSERT INTO Tasks (Id, Seq_Num, Waypoint_Id, '\
              'Radius1, Angle1, Radius2, Angle2, Direction, Angle12) '\
              'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        for tp_num, tp in enumerate(task):
            self.c.execute(sql, (id, tp_num, tp['wp_id'],
                                 tp['rad1'], tp['ang1'],
                                 tp['rad2'], tp['ang2'],
                                 tp['dirn'], tp['ang12']))
        self.commit()

    def get_task(self, id=0):
        sql = 'SELECT * FROM Tasks WHERE Id = ? ORDER BY Seq_Num'
        self.c.execute(sql, (id,))

        task = []
        for tp in self.c:
            task.append({'wp_id': tp['Waypoint_Id'],
                         'rad1':  tp['Radius1'],
                         'ang1':  tp['Angle1'],
                         'rad2':  tp['Radius2'],
                         'ang2':  tp['Angle2'],
                         'dirn':  tp['Direction'],
                         'ang12': tp['Angle12']})
        return task

    def get_task_id(self):
        sql = 'SELECT Task_Id FROM Config'
        self.c.execute(sql)
        return self.c.fetchone()[0]

    def set_task_id(self, task_id):
        sql = 'UPDATE Config SET Task_Id = ?'
        self.c.execute(sql, (task_id,))
        self.commit()

    def delete_airspace(self):
        self.c.execute('DROP INDEX Xmin_Index')
        self.c.execute('DROP INDEX Xmax_Index')
        self.c.execute('DROP INDEX Ymin_Index')
        self.c.execute('DROP INDEX Ymax_Index')

        self.c.execute('DELETE FROM Airspace_Par')
        self.c.execute('DELETE FROM Airspace_Lines')
        self.c.execute('DELETE FROM Airspace_Arcs')

    def insert_airspace_parent(self,
                               id, name, base, top, xmin, ymin, xmax, ymax):
        sql = 'INSERT INTO Airspace_Par '\
              '(Id, Name, Base, Top, X_Min, Y_Min, X_Max, Y_Max) '\
              'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        self.c.execute(sql,
            (id, name, base, top, int(xmin), int(ymin), int(xmax), int(ymax)))

    def insert_airspace_line(self, id, x1, y1, x2, y2):
        sql = 'INSERT INTO Airspace_Lines (Id, X1, Y1, X2, Y2) '\
              'VALUES (?, ?, ?, ?, ?)'
        self.c.execute(sql, (id, int(x1), int(y1), int(x2), int(y2)))

    def insert_airspace_arc(self, id, x, y, radius, startAngle, arcLength):
        sql = 'INSERT INTO Airspace_Arcs '\
              '(Id, X, Y, Radius, Start_Angle, Arc_Length)'\
              'VALUES (?, ?, ?, ?, ?, ?)'
        self.c.execute(sql, (id, int(x), int(y), int(radius),
                             int(startAngle * 64), int(arcLength * 64)))

    def insert_airspace_circle(self, id, x, y, radius):
        self.insert_airspace_arc(id, x, y, radius, 0, 360)

    def create_airspace_indices(self):
        self.c.execute('CREATE INDEX Xmin_Index ON Airspace_Par (X_Min)')
        self.c.execute('CREATE INDEX Xmax_Index ON Airspace_Par (X_Max)')
        self.c.execute('CREATE INDEX Ymin_Index ON Airspace_Par (Y_Min)')
        self.c.execute('CREATE INDEX Ymax_Index ON Airspace_Par (Y_Max)')
