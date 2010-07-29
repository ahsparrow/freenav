"""This module provides a cache store of waypoing and airspace for the freenav
program"""

import math
M_2PI = 2 * math.pi

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
        self.airspace_lines = {}
        self.airspace_arcs = {}

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
        db = self.flight.db
        for airspace in self.airspace:
            as_id = airspace['id']
            self.airspace_lines[as_id] = db.get_airspace_lines(as_id)
            self.airspace_arcs[as_id] = db.get_airspace_arcs(as_id)

    def get_airspace_info(self, x, y):
        """Returns list of airspace info at the given x,y position.

           Works by counting the number of times a line to the left of the
           position cross the boundary. If it's odd then point is inside."""
        airspace_info = []
        for airspace in self.airspace:
            odd_node = count_crossings(x, y, airspace['id'],
                                       self.airspace_lines, self.airspace_arcs)
            if odd_node:
                airspace_info.append((airspace['name'], airspace['base'],
                                      airspace['top']))

        return airspace_info

def count_crossings(x, y, as_id, airspace_lines, airspace_arcs):
    """Count boundary crossings"""
    odd_node = False

    # Count boundary line crossings
    for line in airspace_lines[as_id]:
        x1, y1 = (line['x1'], line['y1'])
        x2, y2 = (line['x2'], line['y2'])
        if (y1 < y and y2 >= y) or (y2 < y and y1 >= y):
            if (x1 + (y - y1) / (y2 - y1) * (x2 -x1)) < x:
                odd_node = not odd_node

    # Count boundary arc (and circle) crossings
    for arc in airspace_arcs[as_id]:
        x_cent, y_cent, radius = (arc['x'], arc['y'], arc['radius'])
        start, arc_len = (arc['start'], arc['length'])
        if y >= (y_cent - radius) and y < (y_cent + radius):
            # Each arc has potentially two crossings
            ang1 = math.asin((y - y_cent) / radius)
            ang2 = math.pi - ang1

            for ang in (ang1, ang2):
                if ((arc_len > 0 and ((ang - start) % M_2PI) < arc_len) or
                    (arc_len < 0 and ((start - ang) % M_2PI) < -arc_len)):
                    x1 = x_cent + radius * math.cos(ang)
                    if x1 < x:
                        odd_node = not odd_node

    return odd_node
