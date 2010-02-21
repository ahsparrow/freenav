import math

class MapCache():
    """Cached waypoints and airspace"""
    def __init__(self, flight):
        self.flight = flight

        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

        self.wps = []
        self.airspace = []
        self.airspace_lines = []
        self.airspace_arcs = []

    def update(self, x, y, width, height):
        """Reload cache if there has been significant movement"""
        dx = abs(x - self.x)
        dy = abs(y - self.y)
        if (dx > (width / 20)) or (dy > (height / 20)):
            self.reload(x, y, width, height)

    def reload(self, x, y, width, height):
        """Reload waypoint and airspace caches"""
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        # Get waypoints
        self.wps = self.flight.db.get_area_waypoint_list(x, y, width, height)

        # Get airspace
        self.airspace = self.flight.db.get_area_airspace(x, y, width, height)
        self.airspace_lines = {}
        self.airspace_arcs = {}
        for a in self.airspace:
            id = a['id']
            self.airspace_lines[id] = self.flight.db.get_airspace_lines(id)
            self.airspace_arcs[id] = self.flight.db.get_airspace_arcs(id)

    def get_airspace_info(self, x, y):
        """Returns list of airspace info at the given x,y position.

           Works by counting the number of times a line to the left of the
           position cross the boundary. If it's odd then point is inside."""
        airspace_info = []
        for airspace in self.airspace:
            odd_node = False

            # Count boundary line crossings
            for line in self.airspace_lines[airspace['id']]:
                x1, y1 = (line['x1'], line['y1'])
                x2, y2 = (line['x2'], line['y2'])
                if (y1 < y and y2 >= y) or (y2 < y and y1 >= y):
                    if (x1 + (y - y1) / (y2 - y1) * (x2 -x1)) < x:
                        odd_node = not odd_node

            # Count boundary arc (and circle) crossings
            for arc in self.airspace_arcs[airspace['id']]:
                xc, yc, radius = (arc['x'], arc['y'], arc['radius'])
                start, len = (arc['start'], arc['length'])
                if y >= (yc - radius) and y < (yc + radius):
                    # Each arc has potentially two crossings
                    ang1 = math.degrees(math.asin((y - yc) / radius)) * 64
                    ang2 = 180 * 64 - ang1

                    for ang in (ang1, ang2):
                        if ((len > 0 and ((ang - start) % (360 * 64)) < len) or
                            (len < 0 and ((start - ang) % (360 * 64)) < -len)):
                            xp = xc + radius * math.cos(math.radians(ang/64.0)) 
                            if xp < x:
                                odd_node = not odd_node

            if odd_node:
                airspace_info.append((airspace['name'], airspace['base'],
                                      airspace['top']))

        return airspace_info
