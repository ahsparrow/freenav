#!/usr/bin/env python

import gps
import freedb, nav, projection, logger
import gtk, gobject, pango
import getopt, math, os.path, sys, time
import socket

M_TO_FT = 1/0.3048
MPS_TO_KTS = 1/nav.KTS_TO_MPS

# Glider polar (metres per second/meters per second)
POLAR_A = -0.002117
POLAR_B = 0.08998
POLAR_C = -1.560

# Map scale limits (metres per pixel)
MAX_SCALE = 200
MIN_SCALE = 25

# Log file location
LOG_DIR = "/mnt/card/igc"

class FreeflightDb(freedb.Freedb):
    def set_view(self, x, y, width, height):
        self.xmin = x-width/2
        self.xmax = x+width/2
        self.ymin = y-height/2
        self.ymax = y+height/2

    def view_wps(self):
        sql = 'SELECT ID, X, Y FROM Waypoint WHERE X>? AND X<? AND Y>? AND Y<?'
        self.c.execute(sql, (self.xmin, self.xmax, self.ymin, self.ymax))
        return self.c.fetchall()

    def view_bdry_lines(self, id):
        sql = 'SELECT X1, Y1, X2, Y2 FROM Airspace_Lines WHERE Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def view_bdry_arcs(self, id):
        sql = 'SELECT X, Y, Radius, Start_Angle, Arc_Length '\
              'FROM Airspace_Arcs WHERE Id=?'
        self.c.execute(sql, (id,))
        return self.c.fetchall()

    def view_bdry(self):
        sql = 'SELECT Id, Name, X_Min, Y_Min, X_Max, Y_Max FROM Airspace_Par '\
              'WHERE ?<X_Max AND ?>X_Min AND ?<Y_Max AND ?>Y_Min'
        self.c.execute(sql, (self.xmin, self.xmax, self.ymin, self.ymax))
        return self.c.fetchall()

class Base:
    def __init__(self, gps, nav, db, logger, fullscreen):
        self.gps = gps
        self.nav = nav
        self.db = db
        self.logger = logger

        self.viewx = 0
        self.viewy = 0
        self.view_scale = MAX_SCALE/2

        if time.localtime().tm_isdst:
            self.tz_offset = time.altzone/3600
        else:
            self.tz_offset = time.timezone/3600

        self.task = self.db.get_task()
        self.wp_index = 0
        wp = self.task[0]
        self.nav.set_dest(wp[1], wp[2], wp[3])

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.area = gtk.DrawingArea()
        self.area_expose_handler_id = \
            self.area.connect('expose-event', self.area_expose)
        self.window.add(self.area)

        self.window.add_events(gtk.gdk.KEY_PRESS_MASK)
        self.window.connect('key_press_event', self.key_press)
        gobject.timeout_add(2000, self.timeout)

        self.window.connect('destroy', gtk.main_quit)

        if fullscreen:
            self.window.fullscreen()
        self.area.set_size_request(240, 360)
        self.area.show()
        self.window.show()

        self.airspace_gc = self.area.window.new_gc(line_width=2)
        cmap = self.area.get_colormap()
        c = cmap.alloc_color('blue')
        self.airspace_gc.set_foreground(c)

    def key_press(self, widget, event, *args):
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname == 'Up':
            self.view_scale = max(MIN_SCALE, self.view_scale/2)
        elif keyname == 'Down':
            self.view_scale = min(MAX_SCALE, self.view_scale*2)
        elif keyname == 'Right':
            self.incr_waypoint()
        elif keyname == 'Left':
            self.decr_waypoint()
        elif keyname == 'XF86Calendar' or keyname == 'Page_Down':
            self.nav.set_headwind(self.nav.headwind-nav.KTS_TO_MPS)
        elif keyname == 'telephone' or keyname == 'Page_Up':
            self.nav.set_headwind(self.nav.headwind+nav.KTS_TO_MPS)
        elif keyname == 'XF86Start' or  keyname == 'q':
            gtk.main_quit()

        self.window.queue_draw()
        return True

    def incr_waypoint(self):
        self.task = self.db.get_task()
        wp_index = self.wp_index+1
        if wp_index>=len(self.task) or self.task[wp_index][0]==self.task[0][0]:
            wp_index = 0
        wp = self.task[wp_index]
        self.nav.set_dest(wp[1], wp[2], wp[3])
        self.wp_index = wp_index

    def decr_waypoint(self):
        self.task = self.db.get_task()
        wp_index = self.wp_index - 1 
        if wp_index < 0:
            wp_index = len(self.task) - 1
            if self.task[wp_index][0]==self.task[0][0] and wp_index:
                wp_index -= 1
        wp = self.task[wp_index]
        self.nav.set_dest(wp[1], wp[2], wp[3])
        self.wp_index = wp_index

    def timeout(self):
        try:
            self.gps.query('patvdg\n')
        except socket.error:
            md = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
                type=gtk.MESSAGE_ERROR,
                message_format='Lost connection to gpsd server')
            md.run()
            gtk.main_quit()
            return True

        fix = self.gps.fix
        borgelt = self.gps.borgelt
        self.nav.update(self.gps.utc, fix, borgelt)
        self.logger.log(self.gps.utc, fix.latitude, fix.longitude, fix.altitude,
                        fix.speed, borgelt.air_speed)

        self.viewx = self.nav.x
        self.viewy = self.nav.y
        self.window.queue_draw()
        return True

    def view_to_win(self, x, y):
        win_width, win_height = self.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x1 = (x-self.viewx)*win_width/view_width+win_width/2
        y1 = win_height/2-(y-self.viewy)*win_height/view_height

        return x1, y1

    def area_expose(self, area, event):
        win = area.window
        gc = win.new_gc()
        pl = pango.Layout(self.area.create_pango_context())
        font_description = pango.FontDescription('sans normal 9')
        pl.set_font_description(font_description)

        win_width, win_height = self.window.get_size()
        view_width = win_width*self.view_scale
        view_height = win_height*self.view_scale
        self.db.set_view(self.viewx, self.viewy, view_width, view_height)

        # Start with a blank sheet...
        win.draw_rectangle(self.area.get_style().white_gc, True,
                           0, 0, win_width, win_height)

        # Draw airspace lines
        cmap = self.area.get_colormap()
        c = cmap.alloc_color('#00F')
        gc.set_foreground(c)
        for id in self.db.view_bdry():
            for x1, y1, x2, y2 in self.db.view_bdry_lines(id[0]):
                x1, y1 = self.view_to_win(x1, y1)
                x2, y2 = self.view_to_win(x2, y2)
                win.draw_line(self.airspace_gc, x1, y1, x2, y2)

            # Draw airspace arcs & circles
            for x, y, radius, start, len in self.db.view_bdry_arcs(id[0]):
                x, y = self.view_to_win(x-radius, y+radius)
                width = 2*radius/self.view_scale
                win.draw_arc(self.airspace_gc, False, x, y, width, width, start, len)

        # Draw task
        c = cmap.alloc_color('#000')
        gc.set_foreground(c)
        gc.line_width = 1
        points = [self.view_to_win(x, y) for wp, x, y, alt in self.task]
        win.draw_polygon(gc, False, points)

        # Draw waypoints
        for wp_id, x, y in self.db.view_wps():
            x, y = self.view_to_win(x, y)
            win.draw_arc(gc, False, x-3, y-3, 6, 6, 0, 23040)

            pl.set_markup(wp_id)
            win.draw_layout(gc, x+3, y+3, pl)

        # Draw annotation
        bg = gtk.gdk.color_parse('white')
        pl.set_markup('<big>ALT:<b>%d</b></big>' % (self.nav.altitude*M_TO_FT))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, 2, win_height-y, pl, background=bg)

        pl.set_markup('<big>GS:<b>%d/%d</b></big>' %
            (self.nav.ground_speed*MPS_TO_KTS,
             (self.nav.air_speed - self.nav.ground_speed)*MPS_TO_KTS))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, win_width/2-27, win_height-y, pl, background=bg)

        if self.nav.utc:
            hour = (int(self.nav.utc[11:13]) - self.tz_offset) % 24
            mins = self.nav.utc[14:16]
            pl.set_markup('<big><b>%d:%s</b></big>' % (hour, mins))
            x, y = pl.get_pixel_size()
            win.draw_layout(gc, win_width-x-3, win_height-y, pl, background=bg)

        row_height = y
        bearing = math.degrees(self.nav.bearing)
        if bearing < 0:
            bearing += 360
        pl.set_markup('<big><b>%s %.1f/%.0f</b></big>' % 
            (self.task[self.wp_index][0], self.nav.dist/1000, bearing))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, 2, win_height-row_height-y, pl, background=bg)

        if self.nav.ete == nav.INVALID_ETE:
            timestr = '-:--'
        else:
            tim = time.gmtime(self.nav.ete)
            timestr = '%d:%02d' % (tim.tm_hour, tim.tm_min)
        pl.set_markup('<big><b>%s</b></big>' % timestr)
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, win_width-x-3, win_height-row_height-y, pl,
                        background=bg)

        # Draw final glide chevrons
        gc.line_width = 2
        y = win_height/2
        win.draw_line(gc, win_width-25, y, win_width-1, y)

        num_arrows = int(self.nav.glide_margin*20)
        if num_arrows > 0:
            y += 5
            yinc = -8
        else:
            y -= 5
            yinc = 8
            num_arrows = -num_arrows

        for i in range(min(num_arrows, 5)):
            y += yinc
            win.draw_lines(gc,
                ((win_width-1, y), (win_width-13, y+yinc), (win_width-25, y)))

        if num_arrows > 5:
            y = y + yinc
            if yinc > 0:
                y += 1
            win.draw_line(gc, win_width-25, y, win_width-1, y)

        # Arrival height, MacCready and headwind setting
        pl.set_markup('<big><b>%d\n%.1f\n%d</b></big>' %
                      (self.nav.arrival_height*M_TO_FT,
                       self.nav.maccready*MPS_TO_KTS,
                       self.nav.headwind*MPS_TO_KTS))
        pl.set_alignment(pango.ALIGN_RIGHT)
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, win_width-x-27, win_height/2-y/3, pl, 
                        background=bg)

        # Draw glider heading
        xc = win_width/2
        yc = win_height/2

        x = math.sin(self.nav.track)
        y = -math.cos(self.nav.track)
        a, b, c, d = 10, 20, 30, 10
        cf = [x*a, y*a, -x*b, -y*b]
        cw = [y*c, -x*c, -y*c, x*c]
        ct = [-x*b+y*d, -y*b-x*d, -x*b-y*d, -y*b+x*d]

        for x1, y1, x2, y2 in cf, cw, ct:
            win.draw_line(gc, int(xc+x1+0.5), int(yc+y1+0.5),
                              int(xc+x2+0.5), int(yc+y2+0.5))

        # Draw course indicator
        ci = self.nav.bearing - self.nav.track
        x = math.sin(ci)
        y = -math.cos(ci)

        xc = yc = 25
        a, b, c = 21, 5, 13

        x0, y0 = x*a, y*a
        xp = [x0, -x0-y*c, -x*b, -x0+y*c]
        yp = [y0, -y0+x*c, -y*b, -y0-x*c]
        poly = [(int(x+xc+0.5), int(y+yc+0.5)) for x, y in zip(xp, yp)]
        win.draw_polygon(gc, True, poly)

        return True

    def main(self):
        gtk.main()

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'fg:l:')
    except getopt.GetoptError:
        print "Bad options"
        sys.exit(2)

    gpshost = 'localhost'
    fullscreen = False
    log_dir = LOG_DIR
    for o, a in opts:
        if o == '-g':
            gpshost = a
        elif o == '-f':
            fullscreen = True
        elif o == '-l':
            log_dir = a

    db = FreeflightDb()
    lambert = projection.Lambert(*db.get_projection())

    height_margin = 305
    polar = {'a': -0.002117, 'b': 0.08998, 'c': -1.56}
    asi_cal = {'v1': 33.3, 'a1': 0.775, 'b1': 6.1, 'a2': 0.95, 'b2': 0.3}

    nv = nav.Nav(lambert, polar, asi_cal, height_margin)

    log = logger.Logger(log_dir)

    base = Base(gps.gps(host=gpshost), nv, db, log, fullscreen)
    base.main()

if __name__ == '__main__':
    main()
