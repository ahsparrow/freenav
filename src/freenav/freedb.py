#!/usr/bin/env python
#
# Database management class
#

from pysqlite2 import dbapi2 as sqlite
import math, os

PARALLEL1 = math.radians(49)
PARALLEL2 = math.radians(55)
REF_LAT = math.radians(52)
REF_LON = math.radians(0)

class Freedb:
    def __init__(self, file=''):
        if not file:
            file = os.path.join(os.getenv('HOME'), '.freeflight', 'free.db')
        self.db = sqlite.connect(file)
        self.c = self.db.cursor()

    def commit(self):
        self.db.commit()

    def vacuum(self):
        self.c.execute('vacuum')

    def create(self, parallel1, parallel2, refLat, refLon):
        sql = 'CREATE TABLE Projection '\
              '(Parallel1 REAL, Parallel2 REAL, Ref_Lat REAL, Ref_Lon REAL)'
        self.c.execute(sql)

        sql = 'INSERT INTO Projection '\
              '(Parallel1, Parallel2, Ref_Lat, Ref_Lon) '\
              'VALUES (?, ?, ?, ?)'
        self.c.execute(sql, (parallel1, parallel2, refLat, refLon))

        sql = 'CREATE TABLE Waypoint '\
              '(Name TEXT, ID TEXT, X INTEGER, Y INTEGER, Altitude INTEGER, '\
              'Turnpoint TEXT, Landable_Flag INTEGER, Comment TEXT)'
        self.c.execute(sql)

        sql = 'CREATE TABLE Task '\
              '(Task_Index INTEGER, Seq_Num INTEGER, Waypoint_ID TEXT)'
        self.c.execute(sql)

        sql = 'CREATE TABLE Airspace_Par '\
              '(Id TEXT, Name TEXT, Base TEXT, Top TEXT, '\
               'X_Min INTEGER, Y_Min INTEGER, X_Max INTEGER, Y_Max INTEGER)'
        self.c.execute(sql)

        sql = 'CREATE TABLE Airspace_Lines '\
              '(Id TEXT, X1 INTEGER, Y1 INTEGER, X2 INTEGER, Y2 INTEGER)'
        self.c.execute(sql)

        sql = 'CREATE TABLE Airspace_Arcs '\
              '(Id TEXT, X INTEGER, Y INTEGER, Radius INTEGER, '\
               'Start_Angle INTEGER, Arc_Length INTEGER)'
        self.c.execute(sql)

        sql = 'CREATE TABLE Config (Task_Index INTEGER)'
        self.c.execute(sql)

        sql = 'INSERT INTO Config (Task_Index) VALUES (0)'
        self.c.execute(sql)

        self.commit()

    def get_projection(self):
        sql = 'SELECT Parallel1, Parallel2, Ref_Lat, Ref_Lon FROM Projection'
        self.c.execute(sql)
        return self.c.fetchone()

    def delete_waypoints(self):
        self.c.execute('DELETE FROM Waypoint')

    def insert_waypoint(self, name, id, x, y, altitude, turnpoint, comment,
                        landable_flag):
        sql = 'INSERT INTO Waypoint '\
              '(Name, ID, X, Y, Altitude, Turnpoint, Comment, Landable_Flag) '\
              'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        self.c.execute(sql, (name, id, x, y,altitude, turnpoint, comment,
                             landable_flag))

    def get_waypoint_list(self):
        sql = 'SELECT ID, Name FROM Waypoint ORDER BY ID'
        self.c.execute(sql)
        return self.c.fetchall()

    def get_waypoint(self, id):
        sql = 'SELECT X, Y, Altitude FROM Waypoint WHERE ID=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def get_waypoint_info(self, id):
        sql = 'SELECT Name, Turnpoint, Comment FROM Waypoint WHERE ID=?'
        self.c.execute(sql, (id,))
        return self.c.fetchone()

    def drop_waypoint_indices(self):
        try:
            self.c.execute('DROP INDEX X_Index')
            self.c.execute('DROP INDEX Y_Index')
        except:
            pass

    def create_waypoint_indices(self):
        self.c.execute('CREATE INDEX X_Index ON Waypoint (X)')
        self.c.execute('CREATE INDEX Y_Index ON Waypoint (Y)')

    def set_task(self, task, task_index=0):
        sql = 'DELETE FROM Task WHERE Task_Index=? '
        self.c.execute(sql, (task_index,))

        sql = 'INSERT INTO Task (Task_Index, Seq_Num, Waypoint_Id) '\
              'VALUES (?, ?, ?)'
        for wp_num, wp in enumerate(task):
            self.c.execute(sql, (task_index, wp_num, wp))

        self.commit()

    def get_task(self, task_index=0):
        sql = 'SELECT Waypoint_Id FROM Task WHERE Task_Index = ? '\
              'ORDER BY Seq_Num'
        self.c.execute(sql, (task_index,))

        task = [wp for (wp,) in self.c.fetchall()]
        return task

    def get_task_index(self):
        sql = 'SELECT Task_Index FROM Config'
        self.c.execute(sql)
        return self.c.fetchone()[0]

    def set_task_index(self, task_index):
        sql = 'UPDATE Config SET Task_Index = ?'
        self.c.execute(sql, (task_index,))
        self.commit()

    def delete_airspace(self):
        try:
            self.c.execute('DROP INDEX Xmin_Index')
            self.c.execute('DROP INDEX Xmax_Index')
            self.c.execute('DROP INDEX Ymin_Index')
            self.c.execute('DROP INDEX Ymax_Index')
        except:
            pass

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


def main():
    db = Freedb()
    db.create(PARALLEL1, PARALLEL2, REF_LAT, REF_LON)

if __name__ == '__main__':
    main()
