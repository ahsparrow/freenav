#!/usr/bin/env python

import getopt
import math
import socket
import sys
import time
import gtk, gobject, pango
import gtk.gdk
import gps
import nav, projection, logger, wind_calc, freenavdb

M_TO_FT = 1/0.3048
MPS_TO_KTS = 1/nav.KTS_TO_MPS

# Glider polar (metres per second/meters per second)
POLAR_A = -0.002117
POLAR_B = 0.08998
POLAR_C = -1.560

# Map scale limits (metres per pixel)
SCALE = [25, 35, 50, 71, 100, 141, 200]

# Log file location
LOG_DIR = "/media/card/igc"

def html_escape(text):
    text = text.replace('&', '&amp;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    text = text.replace(">", '&gt;')
    text = text.replace("<", '&lt;')
    return text

class Base:
    def __init__(self, gps, nav, db, logger, fullscreen, invert):
        self.gps = gps
        self.nav = nav
        self.db = db
        self.logger = logger
        self.wind_calc = wind_calc.WindCalc()

        self.viewx = 0
        self.viewy = 0
        self.view_scale = SCALE[-3]

        self.wp_select_flag = False

        if time.localtime().tm_isdst:
            self.tz_offset = time.altzone/3600
        else:
            self.tz_offset = time.timezone/3600

        self.task = self.db.get_task()
        self.wp_index = 0
        wp = self.task[0]
        self.nav.set_dest(wp[0], wp[1], wp[2], wp[3])

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        self.area = gtk.DrawingArea()
        self.area_expose_handler_id = \
            self.area.connect('expose-event', self.area_expose)
        self.window.add_events(gtk.gdk.BUTTON_PRESS_MASK)

        cmap = self.area.get_colormap()
        self.airspace_color = cmap.alloc_color("blue")
        if invert:
            self.bg_color = cmap.alloc_color("black")
            self.fg_color = cmap.alloc_color("white")
        else:
            self.bg_color = cmap.alloc_color("white")
            self.fg_color = cmap.alloc_color("black")

        self.window.connect('button_press_event', self.button_press)
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

    def button_press(self, widget, event, *args):
        if event.button != 1:
            # Ignore button 3 event generated by GPE when screen is tapped
            return True

        win_width, win_height = self.window.get_size()

        # Change to WP select mode if click is in bottom left corner
        if event.x < 60 and event.y > (win_height - 40):
            self.wp_select_flag = True
            self.window.queue_draw()
            return True

        x, y = self.win_to_view(event.x, event.y)

        if self.wp_select_flag:
            # Select waypoint
            wp_id = self.db.find_landable(x, y)
            if wp_id:
                # Change to alternate waypoint
                x, y, alt = self.db.get_waypoint(wp_id)
                self.nav.set_dest(wp_id, x, y, alt)
            else:
                # Revert to existing task waypoint
                wp_id, x, y, alt = self.task[self.wp_index]
                self.nav.set_dest(wp_id, x, y, alt)

            self.window.queue_draw()
            self.wp_select_flag = False
        else:
            # Get airspace info
            x, y = self.win_to_view(event.x, event.y)
            airspace_segments = self.db.get_airspace(x, y)

            msgs = []
            for seg in airspace_segments:
                msgs.append("<big><b>%s</b>\n%s, %s</big>" %
                            tuple(map(html_escape, seg)))
            if msgs:
                dialog = gtk.Dialog("Airspace", None,
                                    gtk.DIALOG_MODAL | gtk.DIALOG_NO_SEPARATOR,
                                    (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
                msg = "\n\n".join(msgs)
                label = gtk.Label(msg)
                label.set_use_markup(True)
                dialog.vbox.pack_start(label)
                label.show()
                dialog.run()
                dialog.destroy()

        return True

    def key_press(self, widget, event, *args):
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname == 'Up':
            ind = SCALE.index(self.view_scale)
            self.view_scale = SCALE[min(len(SCALE)-1, ind+1)]
        elif keyname == 'Down':
            ind = SCALE.index(self.view_scale)
            self.view_scale = SCALE[max(0, ind-1)]
        elif keyname == 'Right':
            self.incr_waypoint()
        elif keyname == 'Left':
            self.decr_waypoint()
        elif keyname == 'XF86Calendar' or keyname == 'Page_Down':
            self.nav.set_headwind(self.nav.headwind-2*nav.KTS_TO_MPS)
        elif keyname == 'telephone' or keyname == 'Page_Up':
            self.nav.set_headwind(self.nav.headwind+2*nav.KTS_TO_MPS)
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
        self.nav.set_dest(wp[0], wp[1], wp[2], wp[3])
        self.wp_index = wp_index

    def decr_waypoint(self):
        self.task = self.db.get_task()
        wp_index = self.wp_index - 1 
        if wp_index < 0:
            wp_index = len(self.task) - 1
            if self.task[wp_index][0]==self.task[0][0] and wp_index:
                wp_index -= 1
        wp = self.task[wp_index]
        self.nav.set_dest(wp[0], wp[1], wp[2], wp[3])
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
        utc = self.gps.utc

        if self.nav.update(utc, fix, borgelt):
            self.logger.log(self.nav.utc, fix.latitude, fix.longitude,
                            fix.altitude, fix.speed, borgelt.air_speed,
                            fix.track)

            self.viewx = self.nav.x
            self.viewy = self.nav.y
            self.wind_calc.update(self.nav.x, self.nav.y, self.nav.utc)

            self.window.queue_draw()

        return True

    def view_to_win(self, x, y):
        win_width, win_height = self.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x1 = (x-self.viewx)*win_width/view_width+win_width/2
        y1 = win_height/2-(y-self.viewy)*win_height/view_height
        return x1, y1

    def win_to_view(self, x1, y1):
        win_width, win_height = self.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x = view_width * (x1 - win_width/2) / win_width + self.viewx
        y = (win_height/2 - y1) * view_height / win_height + self.viewy
        return x, y

    def draw_airspace(self, gc, win):
        # Draw airspace lines
        for bdry in self.db.view_bdry():
            for x1, y1, x2, y2 in self.db.view_bdry_lines(bdry[0]):
                x1, y1 = self.view_to_win(x1, y1)
                x2, y2 = self.view_to_win(x2, y2)
                win.draw_line(gc, x1, y1, x2, y2)

            # Draw airspace arcs & circles
            for x, y, radius, start, arc_len in self.db.view_bdry_arcs(bdry[0]):
                x, y = self.view_to_win(x-radius, y+radius)
                width = 2*radius/self.view_scale
                win.draw_arc(gc, False, x, y, width, width, start, arc_len)

    def draw_task(self, gc, win):
        # Task
        points = [self.view_to_win(x, y) for wp, x, y, alt in self.task]
        win.draw_lines(gc, points)

        # Start line
        if len(self.task) > 1:
            wps, xs, ys, alts = self.task[0]
            wp1, x1, y1, alt1 = self.task[1]

            bearing = math.atan2(x1 - xs, y1 - ys) + math.pi/2
            dx = int(3000 * math.sin(bearing))
            dy = int(3000 * math.cos(bearing))
            p1 = self.view_to_win(xs - dx, ys - dy)
            p2 = self.view_to_win(xs + dx, ys + dy)
            win.draw_lines(gc, [p1, p2])

    def draw_waypoints(self, gc, pl, win):
        # Draw waypoints
        for wp_id, x, y, landable_flag in self.db.view_wps():
            x, y = self.view_to_win(x, y)
            win.draw_arc(gc, landable_flag, x-3, y-3, 6, 6, 0, 23040)

            pl.set_markup(wp_id)
            win.draw_layout(gc, x+3, y+3, pl)

    def draw_annotation(self, gc, pl, win, win_height, win_width):
        bg = self.bg_color
        pl.set_markup('<big>ALT:<b>%d</b></big>' % (self.nav.altitude*M_TO_FT))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, 2, win_height-y, pl, background=bg)

        pl.set_markup('<big>GS:<b>%d/%d</b></big>' %
            (self.nav.ground_speed*MPS_TO_KTS,
             (self.nav.air_speed - self.nav.ground_speed)*MPS_TO_KTS))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, win_width/2-27, win_height-y, pl, background=bg)

        if self.nav.utc:
            hour = (self.nav.utc.tm_hour - self.tz_offset) % 24
            mins = self.nav.utc.tm_min
            pl.set_markup('<big><b>%d:%02d</b></big>' % (hour, mins))
            x, y = pl.get_pixel_size()
            win.draw_layout(gc, win_width-x-3, win_height-y, pl, background=bg)

        row_height = y
        bearing = math.degrees(self.nav.bearing)
        if bearing < 0:
            bearing += 360
        if self.wp_select_flag:
            markup = '<big><b><u>%s %.1f/%.0f</u></b></big>'
        else:
            markup = '<big><b>%s %.1f/%.0f</b></big>'
        pl.set_markup(markup % (self.nav.tp_name, self.nav.dist/1000, bearing))
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

    def draw_glide(self, gc, pl, win, win_height, win_width):
        # Draw chevrons
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
                        background=None)

    def draw_heading(self, gc, win, win_height, win_width):
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

    def draw_course_indicator(self, gc, win, win_width):
        ci = self.nav.bearing - self.nav.track
        x = math.sin(ci)
        y = -math.cos(ci)

        xc = win_width-24
        yc = 23
        a, b, c = 21, 5, 13

        x0, y0 = x*a, y*a
        xp = [x0, -x0-y*c, -x*b, -x0+y*c]
        yp = [y0, -y0+x*c, -y*b, -y0-x*c]
        poly = [(int(x+xc+0.5), int(y+yc+0.5)) for x, y in zip(xp, yp)]

        win.draw_polygon(gc, True, poly)

    def draw_wind(self, gc, win, pl):
        # Draw wind speed/direction
        x = math.sin(self.wind_calc.wind_direction)
        y = -math.cos(self.wind_calc.wind_direction)
        xc = yc = 17
        a, b, c = 15, 3, 7

        x0, y0 = x*a, y*a
        xp = [x0, -x0-y*c, -x*b, -x0+y*c]
        yp = [y0, -y0+x*c, -y*b, -y0-x*c]
        poly = [(int(x+xc+0.5), int(y+yc+0.5)) for x, y in zip(xp, yp)]

        win.draw_polygon(gc, False, poly)

        speed = self.wind_calc.wind_speed * MPS_TO_KTS
        pl.set_markup('<big><b>%d</b></big>' % speed)
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, xc+a+5, yc-y/2, pl, background=None)

    def area_expose(self, area, event):
        win = area.window
        gc = win.new_gc()

        pl = pango.Layout(self.area.create_pango_context())
        font_description = pango.FontDescription('sans normal 10')
        pl.set_font_description(font_description)

        win_width, win_height = self.window.get_size()
        view_width = win_width*self.view_scale
        view_height = win_height*self.view_scale
        self.db.set_view(self.viewx, self.viewy, view_width, view_height)

        # Start with a blank sheet...
        gc.foreground = self.bg_color
        win.draw_rectangle(gc, True, 0, 0, win_width, win_height)

        gc.foreground = self.airspace_color
        gc.line_width = 2
        self.draw_airspace(gc, win)

        gc.foreground = self.fg_color
        gc.line_width = 1
        self.draw_task(gc, win)
        self.draw_waypoints(gc, pl, win)
        self.draw_annotation(gc, pl, win, win_height, win_width)

        gc.line_width = 2
        self.draw_glide(gc, pl, win, win_height, win_width)
        self.draw_heading(gc, win, win_height, win_width)

        gc.line_width = 1
        self.draw_course_indicator(gc, win, win_width)
        self.draw_wind(gc, win, pl)

        return True

    def main(self):
        gtk.main()

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'fg:il:')
    except getopt.GetoptError:
        print "Bad options"
        sys.exit(2)

    gpshost = 'localhost'
    fullscreen = False
    log_dir = LOG_DIR
    invert = False
    for o, a in opts:
        if o == '-g':
            gpshost = a
        elif o == '-f':
            fullscreen = True
        elif o == '-i':
            invert = True
        elif o == '-l':
            log_dir = a

    db = freenavdb.FreenavDb()
    lambert = projection.Lambert(*db.get_projection())

    height_margin = 305
    polar = {'a': -0.002117, 'b': 0.08998, 'c': -1.56}
    asi_cal = {'v1': 33.3, 'a1': 0.775, 'b1': 6.1, 'a2': 0.95, 'b2': 0.3}

    nv = nav.Nav(lambert, polar, asi_cal, height_margin)

    log = logger.Logger(log_dir)

    base = Base(gps.gps(host=gpshost), nv, db, log, fullscreen, invert)
    base.main()

if __name__ == '__main__':
    main()
