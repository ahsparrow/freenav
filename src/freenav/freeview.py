import math
import time

import gtk, gobject, pango
import gtk.gdk

M_TO_FT = 1 / 0.3048
MPS_TO_KTS = 3600 / 1852.0

# Map scale limits (metres per pixel)
SCALE = [25, 35, 50, 71, 100, 141, 200]
DEFAULT_SCALE = SCALE[4]

WP_SIZE = 10
WP_ARC_LEN = 360 * 64

def html_escape(text):
    text = text.replace('&', '&amp;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    text = text.replace(">", '&gt;')
    text = text.replace("<", '&lt;')
    return text

def add_div(box):
    """Add a dividing bar between box elements"""
    div = gtk.EventBox()
    div.modify_bg(gtk.STATE_NORMAL, div.get_colormap().alloc_color("black"))
    if isinstance(box, gtk.VBox):
        div.set_size_request(-1, 3)
    else:
        div.set_size_request(3, -1)
    box.pack_start(div, expand=False)

class FreeView:
    def __init__(self, flight, fullscreen):
        self.flight = flight
        self.fullscreen = fullscreen

        # viewx/viewy is geographic position at center of window
        self.viewx = 0
        self.viewy = 0
        self.view_scale = DEFAULT_SCALE

        if time.localtime().tm_isdst:
            self.tz_offset = time.altzone / 3600
        else:
            self.tz_offset = time.timezone / 3600

        # Create top level window
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK)

        # Horizontal box
        hbox = gtk.HBox(homogeneous=False)
        self.window.add(hbox)

        # Main drawing area
        self.draw_area = gtk.DrawingArea()
        self.draw_area.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.draw_area.connect('expose-event', self.area_expose)
        hbox.pack_start(self.draw_area, expand=True, fill=True)

        # Allocate some drawing colours
        cmap = self.draw_area.get_colormap()
        self.airspace_color = cmap.alloc_color("blue")
        self.bg_color = cmap.alloc_color("white")
        self.fg_color = cmap.alloc_color("black")

        add_div(hbox)

        # Vertical box for info boxes
        vbox = gtk.VBox(homogeneous=False)
        vbox.set_size_request(150, -1)
        hbox.pack_end(vbox, expand=False)

        # Array of info boxes
        self.info_box = []
        self.info_label = []
        for i in range(4):
            ebox = gtk.EventBox()
            align = gtk.Alignment(xalign=0.5, yalign=0.5)
            label = gtk.Label("xxx")
            ebox.add(align)
            align.add(label)
            ebox.add_events(gtk.gdk.BUTTON_PRESS_MASK)
            ebox.modify_bg(gtk.STATE_NORMAL,
                           ebox.get_colormap().alloc_color("white"))
            self.info_box.append(ebox)
            self.info_label.append(label)

        vbox.pack_start(self.info_box[0])
        for a in self.info_box[1:]:
            add_div(vbox)
            vbox.pack_start(a)

        # Show the window
        if fullscreen:
            self.window.fullscreen()
        else:
            self.window.set_size_request(800, 480)
        self.window.show_all()

        self.update_cache()

    def view_to_win(self, x, y):
        """Convert real world coordinates to window coordinates"""
        win_width, win_height = self.draw_area.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x1 = ((x - self.viewx) * win_width / view_width) + (win_width / 2)
        y1 = (win_height / 2) - ((y - self.viewy) * win_height / view_height)
        return x1, y1

    def win_to_view(self, x1, y1):
        """Convert window coordinates to real world coordinates"""
        win_width, win_height = self.draw_area.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x = (view_width * (x1 - win_width/2) / win_width) + self.viewx
        y = ((win_height/2 - y1) * view_height / win_height) + self.viewy
        return x, y

    def get_view_size(self):
        """Return size of view area, in metres"""
        win_width, win_height = self.draw_area.window.get_size()
        width = win_width * self.view_scale
        height = win_height * self.view_scale
        return width, height


    def draw_waypoints(self, win, gc, layout):
        """Draw waypoints"""
        for wp in self.view_wps:
            x, y = self.view_to_win(wp['x'], wp['y'])
            delta = WP_SIZE / 2
            win.draw_arc(gc, wp['landable_flag'],
                         x - delta, y - delta,
                         WP_SIZE, WP_SIZE, 0, WP_ARC_LEN)

            layout.set_markup(wp['id'])
            win.draw_layout(gc, x + delta, y + delta, layout)

    def draw_airspace(self, gc, win):
        # Draw airspace lines
        for bdry in self.db.view_bdry():
            for line in self.db.view_bdry_lines(bdry['id']):
                x1, y1 = self.view_to_win(line['x1'], line['y1'])
                x2, y2 = self.view_to_win(line['x2'], line['y2'])
                win.draw_line(gc, x1, y1, x2, y2)

            # Draw airspace arcs & circles
            for arc in self.db.view_bdry_arcs(bdry[0]):
                radius = arc['radius']
                x, y = self.view_to_win(arc['x'] - radius, arc['y'] + radius)
                width = 2 * arc['radius'] / self.view_scale
                win.draw_arc(gc, False, x, y, width, width, arc['start'],
                             arc['length'])

    def draw_task(self, gc, win):
        # XXX Task
        points = [self.view_to_win(tp['x'], tp['y']) for tp in self.task]
        win.draw_lines(gc, points)

        # Start line
        if len(self.task) > 1:
            tps = self.task[0]
            tp1 = self.task[1]

            bearing = (math.atan2(tp1['x'] - tps['x'], tp1['y'] - tps['y']) +
                       math.pi/2)
            dx = int(3000 * math.sin(bearing))
            dy = int(3000 * math.cos(bearing))
            p1 = self.view_to_win(tps['x'] - dx, tps['y'] - dy)
            p2 = self.view_to_win(tps['x'] + dx, tps['y'] + dy)
            win.draw_lines(gc, [p1, p2])

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
        win.draw_layout(gc, 2, win_height - row_height - y, pl, background=bg)

        # XXX pl.set_markup('<big><b>%d</b></big>' % self.gps.satellites_used)
        # XXX x, y = pl.get_pixel_size()
        # XXX win.draw_layout(gc, 2, win_height-2*row_height-y, pl, background=bg)

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
        # XXX Draw wind speed/direction
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
        win_width, win_height = win.get_size()

        pl = pango.Layout(area.create_pango_context())
        font_description = pango.FontDescription('sans normal 14')
        pl.set_font_description(font_description)

        # Start with a blank sheet...
        gc = win.new_gc()
        gc.foreground = self.bg_color
        win.draw_rectangle(gc, True, 0, 0, win_width, win_height)

        gc.foreground = self.airspace_color
        gc.line_width = 2
        # XXX self.draw_airspace(gc, win)

        gc.foreground = self.fg_color
        gc.line_width = 1
        # XXX self.draw_task(gc, win)
        self.draw_waypoints(win, gc, pl)
        # XXX self.draw_annotation(gc, pl, win, win_height, win_width)

        gc.line_width = 2
        # XXX self.draw_glide(gc, pl, win, win_height, win_width)
        # XXX self.draw_heading(gc, win, win_height, win_width)

        gc.line_width = 1
        # self.draw_course_indicator(gc, win, win_width)
        # XXX self.draw_wind(gc, win, pl)

        return True

    def update_cache(self):
        """Update cached waypoints and airspace"""
        width, height = self.get_view_size()
        self.view_wps = self.flight.get_area_waypoint_list(
                                    self.viewx, self.viewy, width, height)

    # External methods - for use by controller
    def redraw(self):
        """Redraw display"""
        self.window.queue_draw()

    def update_position(self, x, y):
        """Update position of view and redraw"""
        self.viewx = x
        self.viewy = y
        self.update_cache()
        self.redraw()

    def zoom_out(self):
        """See some more"""
        ind = SCALE.index(self.view_scale)
        if ind < (len(SCALE) - 1):
            self.view_scale = SCALE[ind + 1]
        self.update_cache()

    def zoom_in(self):
        """See some less"""
        ind = SCALE.index(self.view_scale)
        if ind > 0:
            self.view_scale = SCALE[ind - 1]
        self.update_cache()
