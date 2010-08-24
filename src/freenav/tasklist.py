"""This module provides the backing store for the task list in freetask"""

import math

import gobject
import gtk

import freenav.projection
import freenav.util

# Default observation zone values
RAD1 = 500
ANG1 = 360
RAD2 = 0
ANG2 = 0
START_RAD = 5000
FINISH_RAD = 500

def make_tp(wp_id, tp_type='TURNPOINT', rad1=RAD1, ang1=ANG1, rad2=RAD2,
            ang2=ANG2, dirn='SYM', ang12=0, mindistx=None, mindisty=None):
    """Generate a default turnpoint"""
    return {'waypoint_id': wp_id, 'tp_type': tp_type,
            'radius1': rad1, 'angle1': ang1,
            'radius2': rad2, 'angle2': ang2,
            'direction': dirn, 'angle12': ang12,
            'mindistx': mindistx, 'mindisty': mindisty}

def make_start_tp(wp_id, rad1=START_RAD, ang1=180, dirn='NEXT', ang12=0):
    """Generate a default start point"""
    return make_tp(wp_id, rad1=rad1, ang1=ang1, dirn=dirn, ang12=ang12)

def make_finish_tp(wp_id, tp_type='LINE', rad1=FINISH_RAD, ang1=0, dirn='PREV',
                   ang12=0):
    """Generate a default finish point"""
    return make_tp(wp_id, tp_type=tp_type, rad1=rad1, ang1=ang1, dirn=dirn,
                   ang12=ang12)

class TaskListStore(gtk.ListStore):
    """Model for the task list"""
    def __init__(self, db):
        gtk.ListStore.__init__(self, object)
        self.db = db

        proj = self.db.get_projection()
        self.projection = freenav.projection.Lambert(
            proj['parallel1'], proj['parallel2'],
            proj['latitude'], proj['longitude'])

        gobject.signal_new("task_changed", TaskListStore,
                           gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, ())

    def get_task(self):
        """Return array of turnpoints"""
        return [x[0] for x in self]

    def load(self, task_id=-1):
        """Load task from database"""
        self.clear()
        if task_id == -1:
            task_id = self.db.get_active_task_id()
        self.task_id = task_id

        for tp in self.db.get_task(task_id):
            self.append([tp])
        self.emit("task_changed")

    def declare(self):
        """Save FLARM declaration to flarmcfg.txt"""
        try:
            f = open('/media/mmc1/flarmcfg.txt', 'w')
            f.write("$PFLAC,S,NEWTASK,My Task\n")
            f.write("$PFLAC,S,ADDWP,0000000N,00000000W,Takeoff\n")

            for tp in self:
                wp = self.db.get_waypoint(tp[0]['waypoint_id'])
                lat = "%(deg)02d%(min)02d%(dec)03d%(ns)s" %\
                        freenav.util.dmm(wp['latitude'], 3)
                lon = "%(deg)03d%(min)02d%(dec)03d%(ew)s" %\
                        freenav.util.dmm(wp['longitude'], 3)
                str = "$PFLAC,S,ADDWP,%s,%s,%s\n" % (lat, lon, wp['id'])
                f.write(str)
            f.write("$PFLAC,S,ADDWP,0000000N,00000000W,Land\n")
            f.close()
        except IOError:
            return False

        return True

    def save(self):
        """Save task to database"""
        self.update_min_dist()
        task = [x[0] for x in self]
        self.db.set_task(task, self.task_id)
        self.db.set_active_task_id(self.task_id)

    def commit(self):
        """Commit database changes"""
        self.db.commit()

    def delete_tp(self, index):
        """Delete TP, and make new start or finish if old one was deleted"""
        task_len = len(self)
        del self[index]

        if task_len > 1:
            if index == 0:
                # Start point was deleted so make new start
                self[0] = [make_start_tp(self[0][0]['waypoint_id'])]
            elif index == (task_len - 1):
                # Finish point was deleted so make new finish
                self[-1] = [make_finish_tp(self[-1][0]['waypoint_id'])]
        self.update_angles()
        self.emit("task_changed")

    def insert_tp(self, index, wp_id):
        """Insert TP, making it start, finish or TP depending on position"""
        if len(self) == 0:
            # Task currently empty
            self.append([make_start_tp(wp_id)])
        elif index == 0:
            # Inserting at start of task
            old_id = self[0][0]['waypoint_id']
            if len(self) == 1:
                self[0] = [make_finish_tp(old_id)]
            else:
                self[0] = [make_tp(old_id)]
            self.insert(0, [make_start_tp(wp_id)])
        elif index == len(self):
            # Appending to end of task
            old_id = self[-1][0]['waypoint_id']
            if len(self) == 1:
                self[-1] = [make_start_tp(old_id)]
            else:
                self[-1] = [make_tp(old_id)]
            self.append([make_finish_tp(wp_id)])
        else:
            # Inserting in middle of task
            self.insert(index, [make_tp(wp_id)])

        self.update_angles()
        self.emit("task_changed")

    def move_tp(self, source, dest):
        """Move TP in task"""
        if (dest == source) or (dest == source + 1):
            return

        if (source in (0, len(self) - 1)) or (dest in (0, len(self))):
            # Source or dest is start or finish so delete souce and
            # re-create at dest
            wp_id = self[source][0]['waypoint_id']
            self.delete_tp(source)

            if dest > source:
                dest = dest - 1
            self.insert_tp(dest, wp_id)

        else:
            # Both source and dest are in the middle of the task, so just move
            source_iter = self.get_iter((source,))
            dest_iter = self.get_iter((dest,))
            self.move_before(source_iter, dest_iter)

        self.update_angles()
        self.emit("task_changed")

    def set_tp(self, index, vals):
        """Set turnpoint values"""
        tp = self[index][0]
        for k in vals:
            tp[k] = vals[k]
        self.update_angles()

        self.emit("task_changed")

    def get_task_len(self):
        """Returns task length, in m"""
        tp_list = [tp[0]['waypoint_id'] for tp in self]
        if len(tp_list) == 0:
            dist = 0
        else:
            wp = self.db.get_waypoint(tp_list[0])
            dist = self.calc_distance(wp, tp_list[1:])

        return dist

    def calc_distance(self, wp, tp_list):
        """Recursive task length calculation"""
        if len(tp_list) == 0:
            dist = 0
        else:
            wp1 = self.db.get_waypoint(tp_list[0])
            dist = (self.projection.dist(wp['x'], wp['y'],
                                         wp1['x'], wp1['y']) +
                    self.calc_distance(wp1, tp_list[1:]))
        return dist

    def update_angles(self):
        """Recalculate TP angles"""
        task = [tp[0] for tp in self]
        wps = [self.db.get_waypoint(t['waypoint_id']) for t in task]

        if len(task) == 1:
            task[0]['angle12'] = 0
        else:
            for n, (tp, wp) in enumerate(zip(task, wps)):
                if tp['direction'] == 'FIX':
                    continue

                x, y = wp['x'], wp['y']
                if tp['direction'] == 'NEXT':
                    wp1 = wps[n + 1]
                    x1, y1 = wp1['x'], wp1['y']
                    dx, dy = x1 - x, y1 - y
                elif tp['direction'] == 'PREV':
                    wp1 = wps[n - 1]
                    x1, y1 = wp1['x'], wp1['y']
                    dx, dy = x1 - x, y1 - y
                elif tp['direction'] == 'SYM':
                    wp1 = wps[n - 1]
                    x1, y1 = wp1['x'], wp1['y']
                    dist1 = math.hypot((x - x1), (y - y1))

                    wp2 = wps[n + 1]
                    x2, y2 = wp2['x'], wp2['y']
                    dist2 = math.hypot((x - x2), (y - y2))

                    if dist2 == 0:
                        dx = dy = 0
                    else:
                        dx = ((x1 - x) + ((x2 - x) * dist1 / dist2)) / 2
                        dy = ((y1 - y) + ((y2 - y) * dist1 / dist2)) / 2
                ang = math.atan2(dx, dy) % (2 * math.pi)
                tp['angle12'] = math.degrees(ang)

    def update_min_dist(self):
        """Calculate (simplistic) minimum distance TP positions"""
        task = [tp[0] for tp in self]
        wps = [self.db.get_waypoint(t['waypoint_id']) for t in task]

        for tp, wp in zip(task, wps):
            ang12 = math.radians(tp['angle12'])

            if tp['tp_type'] == 'AREA':
                if tp['angle1'] == 360:
                    dx = tp['radius1'] * math.sin(ang12)
                    dy = tp['radius1'] * math.cos(ang12)
                elif tp['angle2'] == 360:
                    dx = tp['radius2'] * math.sin(ang12)
                    dy = tp['radius2'] * math.cos(ang12)
                elif tp['angle1'] == 0:
                    dx = 0
                    dy = 0
                else:
                    dx = -tp['radius2'] * math.sin(ang12)
                    dy = -tp['radius2'] * math.cos(ang12)
            else:
                dx = dy = 0

            tp['mindistx'] = wp['x'] + dx
            tp['mindisty'] = wp['y'] + dy
