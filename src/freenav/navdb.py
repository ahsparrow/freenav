import math
import freedb

class FreenavDb( freedb.Freedb):
    def __init__(self):
        freedb.Freedb.__init__(self)
        self.ref_x = 0
        self.ref_y = 0
        self.ref_width = 0
        self.ref_height = 0

    def set_view(self, x, y, width, height):
        """Set the centre and size of the current view."""
        if width==self.ref_width and height==self.ref_height and\
           abs(x-self.ref_x)<width/20 and abs(y-self.ref_y)<height/20:
            # If nothing's changed very much don't update
            return

        # Update view
        self.ref_x = x
        self.ref_y = y
        self.ref_width = width
        self.ref_height = height

        xmin = x-width/2
        xmax = x+width/2
        ymin = y-height/2
        ymax = y+height/2

        # Update (and cache) waypoints and airspace
        sql = 'SELECT * FROM Waypoints WHERE X>? AND X<? AND Y>? AND Y<?'
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        self.wps = self.c.fetchall()

        sql = '''SELECT * FROM Airspace
              WHERE ? < X_Max AND ? > X_Min AND ? < Y_Max AND ? > Y_Min'''
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        self.bdrys = self.c.fetchall()

        self.bdry_lines = {}
        self.bdry_arcs = {}
        for bdry in self.bdrys:
            id = bdry[0]
            sql = 'SELECT * FROM Airspace_Lines WHERE Airspace_Id=?'
            self.c.execute(sql, (id,))
            self.bdry_lines[id] = self.c.fetchall()

            sql = 'SELECT * FROM Airspace_Arcs WHERE Airspace_Id=?'
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
        """Returns landable waypoints close to the given x,y position."""
        xmin = x - self.ref_width/10
        xmax = x + self.ref_width/10
        ymin = y - self.ref_height/10
        ymax = y + self.ref_height/10
        sql = '''SELECT * FROM Waypoints
              WHERE X>? AND X<? AND Y>? AND Y<? AND Landable_Flag=1'''
        self.c.execute(sql, (xmin, xmax, ymin, ymax))
        landable_wps = self.c.fetchall()

        if landable_wps:
            wp = landable_wps[0]
            min_dist = (x - wp['x']) ** 2 + (y - wp['y']) ** 2
            closest_wp = wp['id']
            for wp in landable_wps[1:]:
                dist = (x - wp['x']) ** 2 + (y - wp['y']) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_wp = wp['id']

            return closest_wp
        else:
            return None

    def get_airspace(self, x, y):
        """Returns list of airspace segments at the given x,y position.

           Works by counting the number of times a line to the left of the
           position cross the boundary. If it's odd then point is inside."""

        airspace_segments = []
        for bdry in self.bdrys:
            odd_node = False

            # Count boundary line crossings
            for line in self.bdry_lines[bdry['id']]:
                x1, y1 = (line['x1'], line['y1'])
                x2, y2 = (line['x2'], line['y2'])
                if (y1 < y and y2 >= y) or (y2 < y and y1 >= y):
                    if (x1 + (y - y1) / (y2 - y1) * (x2 -x1)) < x:
                        odd_node = not odd_node

            # Count boundary arc (and circle) crossings
            for arc in self.bdry_arcs[bdry['id']]:
                xc, yc, radius = (arc['x'], arc['y'], arc['radius'])
                start, len = (arc['start'], arc['length'])
                if y >= (yc - radius) and y < (yc + radius):
                    # Each arc has potentially two crossings
                    ang1 = math.degrees(math.asin((y - yc) / radius)) * 64
                    ang2 = 180 * 64 - ang1

                    for ang in (ang1, ang2):
                        if (len > 0 and ((ang - start) % (360 * 64)) < len) or \
                           (len < 0 and ((start - ang) % (360 * 64)) < -len):
                            xp = xc + radius * math.cos(math.radians(ang/64.0)) 
                            if xp < x:
                                odd_node = not odd_node

            if odd_node:
                airspace_segments.append(
                        (bdry['name'], bdry['base'], bdry['top']))

        return airspace_segments
