import freedb

class FreenavDb( freedb.Freedb):
    def __init__(self):
        freedb.Freedb.__init__(self)
        self.ref_x = 0
        self.ref_y = 0
        self.ref_width = 0
        self.ref_height = 0

    def set_view(self, x, y, width, height):
        if width==self.ref_width and height==self.ref_height and\
           abs(x-self.ref_x)<width/20 and abs(y-self.ref_y)<height/20:
            return

        self.ref_x = x
        self.ref_y = y
        self.ref_width = width
        self.ref_height = height

        xmin = x-width/2
        xmax = x+width/2
        ymin = y-height/2
        ymax = y+height/2

        sql = 'SELECT ID, X, Y, Landable_Flag FROM Waypoint '\
              'WHERE X>? AND X<? AND Y>? AND Y<?'
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        self.wps = self.c.fetchall()

        sql = 'SELECT Id, Name, X_Min, Y_Min, X_Max, Y_Max FROM Airspace_Par '\
              'WHERE ?<X_Max AND ?>X_Min AND ?<Y_Max AND ?>Y_Min'
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        self.bdrys = self.c.fetchall()

        self.bdry_lines = {}
        self.bdry_arcs = {}
        for bdry in self.bdrys:
            id = bdry[0]
            sql = 'SELECT X1, Y1, X2, Y2 FROM Airspace_Lines WHERE Id=?'
            self.c.execute(sql, (id,))
            self.bdry_lines[id] = self.c.fetchall()

            sql = 'SELECT X, Y, Radius, Start_Angle, Arc_Length '\
                  'FROM Airspace_Arcs WHERE Id=?'
            self.c.execute(sql, (id,))
            self.bdry_arcs[id] = self.c.fetchall()

    def view_wps(self):
        return self.wps

    def view_bdry(self):
        return self.bdrys

    def view_bdry_lines(self, id):
        return self.bdry_lines[id]

    def view_bdry_arcs(self, id):
        return self.bdry_arcs[id]

    def find_landable(self, x, y):
        xmin = x - self.ref_width/10
        xmax = x + self.ref_width/10
        ymin = y - self.ref_height/10
        ymax = y + self.ref_height/10
        sql = "SELECT Id, X, Y FROM Waypoint "\
              "WHERE X>? AND X<? AND Y>? AND Y<? AND Landable_Flag=1"
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        landable_wps = self.c.fetchall()

        if landable_wps:
            wp = landable_wps[0]
            min_dist = (x - wp[1]) ** 2 + (y - wp[2]) ** 2
            closest_wp = wp[0]
            for wp in landable_wps[1:]:
                dist = (x - wp[1]) ** 2 + (y - wp[2]) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_wp = wp[0]

            return closest_wp
        else:
            return None
