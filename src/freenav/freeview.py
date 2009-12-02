import math
import time

import gtk, gobject, pango
import gtk.gdk

# Constants for drawing arcs
ARC_LEN = 64
CIRCLE_LEN = 360 * ARC_LEN

M_TO_FT = 1 / 0.3048
MPS_TO_KTS = 3600 / 1852.0

# Map scale limits (metres per pixel)
SCALE = [6, 9, 12, 17, 25, 35, 50, 71, 100, 141, 200, 282, 400]
DEFAULT_SCALE = SCALE[8]

# Number and size of info boxes
NUM_INFO_BOXES = 4
INFO_BOX_SIZE = 150

# Size of waypoint symbol
WP_SIZE = 10

# Size of final glide indicator
FG_WIDTH = 40
FG_INC = 20

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

        # viewx/viewy is geographic position at center of window
        self.viewx = 0
        self.viewy = 0
        self.view_scale = DEFAULT_SCALE

        # Font size juju
        self.font_size = int(100000.0 * gtk.gdk.screen_height_mm() /
                             gtk.gdk.screen_height())

        # Create top level window
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK)

        # Horizontal box
        hbox = gtk.HBox(homogeneous=False)
        self.window.add(hbox)

        # Main drawing area
        self.drawing_area = gtk.DrawingArea()
        self.drawing_area.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.drawing_area.connect('expose-event', self.area_expose)
        hbox.pack_start(self.drawing_area, expand=True, fill=True)

        # Allocate some drawing colours
        cmap = self.drawing_area.get_colormap()
        self.airspace_color = cmap.alloc_color("blue")
        self.bg_color = cmap.alloc_color("white")
        self.fg_color = cmap.alloc_color("black")

        # Divider between map and info boxes
        add_div(hbox)

        # Vertical box for info boxes
        vbox = gtk.VBox(homogeneous=False)
        vbox.set_size_request(INFO_BOX_SIZE, -1)
        hbox.pack_end(vbox, expand=False)

        # Array of info boxes
        self.info_box = []
        self.info_label = []
        for i in range(NUM_INFO_BOXES):
            label = gtk.Label("xxx")
            align = gtk.Alignment(xalign=0.5, yalign=0.5)
            align.add(label)
            ebox = gtk.EventBox()
            ebox.add(align)
            ebox.add_events(gtk.gdk.BUTTON_PRESS_MASK)
            ebox.modify_bg(gtk.STATE_NORMAL,
                           ebox.get_colormap().alloc_color("white"))
            self.info_box.append(ebox)
            self.info_label.append(label)

        vbox.pack_start(self.info_box[0])
        for ibox in self.info_box[1:]:
            add_div(vbox)
            vbox.pack_start(ibox)

        # Show the window
        if fullscreen:
            self.window.fullscreen()
        else:
            self.window.set_size_request(800, 480)
        self.window.show_all()

        # Initialise waypoint/airspace cache
        self.update_cache()

    def view_to_win(self, x, y):
        """Convert real world coordinates to window coordinates"""
        win_width, win_height = self.drawing_area.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x1 = ((x - self.viewx) * win_width / view_width) + (win_width / 2)
        y1 = (win_height / 2) - ((y - self.viewy) * win_height / view_height)
        return int(x1), int(y1)

    def win_to_view(self, x1, y1):
        """Convert window coordinates to real world coordinates"""
        win_width, win_height = self.drawing_area.window.get_size()
        view_width = win_width * self.view_scale
        view_height = win_height * self.view_scale

        x = (view_width * (x1 - win_width/2) / win_width) + self.viewx
        y = ((win_height/2 - y1) * view_height / win_height) + self.viewy
        return x, y

    def get_view_size(self):
        """Return size of view area, in metres"""
        win_width, win_height = self.drawing_area.window.get_size()
        width = win_width * self.view_scale
        height = win_height * self.view_scale
        return width, height

    def area_expose(self, area, event):
        """Repaint the display"""
        win = area.window
        win_width, win_height = win.get_size()

        pl = pango.Layout(area.create_pango_context())
        font_description = pango.FontDescription('sans normal 14')
        pl.set_font_description(font_description)

        # Start with a blank sheet...
        gc = win.new_gc()
        gc.foreground = self.bg_color
        win.draw_rectangle(gc, True, 0, 0, win_width, win_height)

        # Airspace
        gc.foreground = self.airspace_color
        gc.line_width = 2
        self.draw_airspace(gc, win)

        # Task and turnpoint sectors
        gc.foreground = self.fg_color
        gc.line_width = 2
        self.draw_task(gc, win)

        # Waypoints
        gc.line_width = 1
        self.draw_waypoints(win, gc, pl)

        # Turnpoint annotation
        self.draw_annotation(gc, pl, win, win_height)

        # Final glide indicator
        gc.line_width = 3
        self.draw_glide(gc, pl, win, win_height)

        # Draw heading symbol
        gc.line_width = 2
        self.draw_heading(gc, win, win_height, win_width)

        # Draw course arrow
        gc.line_width = 1
        self.draw_course_indicator(gc, win)

        # Draw wind arrow
        gc.line_width = 2
        self.draw_wind(gc, pl, win, win_width)

        self.draw_info()

        return True

    def draw_waypoints(self, win, gc, layout):
        """Draw waypoints"""
        tps = [tp['waypoint_id'] for tp in self.flight.task]
        for wp in self.view_wps:
            if self.view_scale<=100 or wp['landable_flag'] or wp['id'] in tps:
                x, y = self.view_to_win(wp['x'], wp['y'])
                delta = WP_SIZE / 2
                win.draw_arc(gc, wp['landable_flag'],
                             x - delta, y - delta,
                             WP_SIZE, WP_SIZE, 0, CIRCLE_LEN)

                layout.set_markup(wp['id'])
                win.draw_layout(gc, x + delta, y + delta, layout)

    def draw_airspace(self, gc, win):
        """Draw airspace boundary lines and arcs"""
        # Airspace lines
        for line in self.airspace_lines:
            x1, y1 = self.view_to_win(line['x1'], line['y1'])
            x2, y2 = self.view_to_win(line['x2'], line['y2'])
            win.draw_line(gc, x1, y1, x2, y2)

        # Airspace arcs & circles
        for arc in self.airspace_arcs:
            radius = arc['radius']
            x, y = self.view_to_win(arc['x'] - radius, arc['y'] + radius)
            width = 2 * arc['radius'] / self.view_scale
            win.draw_arc(gc, False, x, y, width, width, arc['start'],
                         arc['length'])

    def draw_task(self, gc, win):
        """Draw task and turnpoint sectors"""
        pts = [self.view_to_win(tp['x'], tp['y']) for tp in self.flight.task]
        win.draw_lines(gc, pts)

        # Draw sectors
        if len(self.flight.task) > 1:
            for tp in self.flight.task[:-1]:
                self.draw_tp_sector(gc, win, tp)

            # Draw finish line
            self.draw_tp_line(gc, win, self.flight.task[-1])

    def draw_tp_line(self, gc, win, tp):
        """Draw turnpoint (finish) line"""
        x, y = tp['x'], tp['y']
        radius = tp['radius1']
        angle = math.radians(tp['angle12'])
        dx = -radius * math.cos(angle)
        dy = radius * math.sin(angle)

        x1, y1 = self.view_to_win(x + dx, y + dy)
        x2, y2 = self.view_to_win(x - dx, y - dy)
        win.draw_line(gc, x1, y1, x2, y2)

    def draw_tp_sector(self, gc, win, tp):
        """Draw turnpoint sector"""
        oz_x, oz_y = tp['x'], tp['y']
        oz_radius1 = tp['radius1']
        oz_radius2 = tp['radius2']
        oz_angle1 = tp['angle1']
        oz_angle2 = tp['angle2']
        oz_angle = tp['angle12']

        # Outer arc
        x, y = self.view_to_win(oz_x - oz_radius1, oz_y + oz_radius1)
        width = height = int(2 * oz_radius1 / self.view_scale)
        ang1 = int(((90 - (180 + oz_angle + (oz_angle1 / 2.0))) % 360) * 64)
        ang2 = int(oz_angle1 * 64)
        win.draw_arc(gc, False, x, y, width, height, ang1, ang2)

        if abs(oz_angle1 - 360) < 0.1:
            return

        # Outer radials
        ang = 180 + oz_angle + (oz_angle1 / 2.0)
        self.draw_radial(gc, win, oz_x, oz_y, ang, oz_radius1, oz_radius2)
        ang = 180 + oz_angle - (oz_angle1 / 2.0)
        self.draw_radial(gc, win, oz_x, oz_y, ang, oz_radius1, oz_radius2)

        if oz_radius2 == 0:
            return

        # Inner arc
        x, y = self.view_to_win(oz_x - oz_radius2, oz_y + oz_radius2)
        width = height = int(2 * oz_radius2 / self.view_scale)
        arc_len = int((oz_angle1 - oz_angle2) * 32)

        win.draw_arc(gc, False, x, y, width, height, ang1, arc_len)
        ang = (ang1 + ang2) % 23040
        win.draw_arc(gc, False, x, y, width, height, ang, -arc_len)

        if (oz_angle2 == 0) or (abs(oz_angle2 - 360) < 0.1):
            return

        # Inner radials
        ang = 180 + oz_angle + (oz_angle2 / 2.0)
        self.draw_radial(gc, win, oz_x, oz_y, ang, oz_radius2, 0)
        ang = 180 + oz_angle - (oz_angle2 / 2.0)
        self.draw_radial(gc, win, oz_x, oz_y, ang, oz_radius2, 0)

    def draw_radial(self, gc, win, x, y, angle, radius1, radius2):
        """Draw a radial line"""
        a = math.radians(angle)
        ca = math.cos(a)
        sa = math.sin(a)

        x1, y1 = self.view_to_win(x + radius1 * sa, y + radius1 * ca)
        x2, y2 = self.view_to_win(x + radius2 * sa, y + radius2 * ca)
        win.draw_line(gc, x1, y1, x2, y2)

    def draw_annotation(self, gc, pl, win, win_height):
        """Draw turnpoint annotation"""
        nav = self.flight.get_nav()
        bearing = math.degrees(nav['bearing'])
        if bearing < 0:
            bearing += 360

        markup = '<big><b>%s %.1f/%.0f</b></big>'
        pl.set_markup(markup % (nav['id'], nav['distance'] / 1000, bearing))
        x, y = pl.get_pixel_size()

        win.draw_layout(gc, 2, win_height - y, pl, background=self.bg_color)

    def draw_glide(self, gc, pl, win, win_height):
        """Draw final glide information"""
        glide = self.flight.get_glide()

        # Draw origin
        y = win_height / 2
        win.draw_line(gc, 1, y, FG_WIDTH + 1, y)

        # Draw chevrons
        num_arrows = int(glide['margin'] * 20)
        if num_arrows > 0:
            y = y + (FG_INC / 2)
            yinc = -FG_INC
        else:
            y = y - (FG_INC / 2)
            yinc =  FG_INC
        num_arrows = abs(num_arrows)

        for i in range(min(num_arrows, 5)):
            y =  y + yinc
            win.draw_lines(gc, [(1, y), ((FG_WIDTH / 2) + 1, y + yinc),
                                (FG_WIDTH + 1, y)])

        # Draw limit bar
        if num_arrows > 5:
            y = y + yinc
            if yinc > 0:
                y = y + gc.line_width
            else:
                y = y - gc.line_width
            win.draw_line(gc, 1, y, FG_WIDTH + 1, y)

        # Arrival height, MacCready and ETE
        ete_mins = glide['ete'] / 60
        if ete_mins >= 600:
            ete_str = '-:--'
        else:
            ete_str = "%d:%02d" % (ete_mins / 60, ete_mins % 60)

        pl.set_markup('<big><b>%d\n%s\n%.1f</b></big>' %
                      (glide['height'] * M_TO_FT, ete_str,
                       glide['maccready'] * MPS_TO_KTS))
        x, y = pl.get_pixel_size()
        win.draw_layout(gc, FG_WIDTH + 5, (win_height / 2) - (2 * y / 3), pl,
                        background=None)

    def draw_heading(self, gc, win, win_height, win_width):
        """Draw heading glider symbol"""
        xc = win_width / 2
        yc = win_height / 2

        vel = self.flight.get_velocity()
        x = math.sin(vel['track'])
        y = -math.cos(vel['track'])
        a, b, c, d = 15, 30, 45, 15
        cf = [x*a, y*a, -x*b, -y*b]
        cw = [y*c, -x*c, -y*c, x*c]
        ct = [-x*b+y*d, -y*b-x*d, -x*b-y*d, -y*b+x*d]

        for x1, y1, x2, y2 in cf, cw, ct:
            win.draw_line(gc, int(xc + x1 + 0.5), int(yc + y1 + 0.5),
                              int(xc + x2 + 0.5), int(yc + y2 + 0.5))

    def draw_course_indicator(self, gc, win):
        """Draw arrow for relative bearing to TP"""
        rb = self.flight.get_nav()['relative_bearing']
        x, y = math.sin(rb), -math.cos(rb)

        xc = 40
        yc = 40
        a, b, c = 30, 10, 20

        x0, y0 = x * a, y * a
        xp = [x0, -x0 - y * c, -x * b, -x0 + y * c]
        yp = [y0, -y0 + x * c, -y * b, -y0 - x * c]
        poly = [(int(x + xc + 0.5), int(y + yc + 0.5)) for x, y in zip(xp, yp)]

        win.draw_polygon(gc, True, poly)

    def draw_wind(self, gc, pl, win, win_width):
        # Draw wind speed/direction
        wind = self.flight.get_wind()
        x = math.sin(wind['direction'])
        y = -math.cos(wind['direction'])
        xc = win_width - 35 
        yc = 35
        a, b, c = 30, 6, 14

        x0, y0 = x * a, y * a
        xp = [x0, -x0 - y * c, -x * b, -x0 + y * c]
        yp = [y0, -y0 + x * c, -y * b, -y0 - x * c]
        poly = [(int(x + xc + 0.5), int(y + yc + 0.5)) for x, y in zip(xp, yp)]

        win.draw_polygon(gc, False, poly)

        speed = wind['speed'] * MPS_TO_KTS
        pl.set_markup('<big><b>%d</b></big>' % speed)
        x, y = pl.get_pixel_size()

        win.draw_layout(gc, xc - x - 35, yc - y / 2, pl, background=None)

    def draw_info(self):
        time_str = time.strftime("%H:%M",
                                 time.localtime(self.flight.get_secs()))
        self.info_label[3].set_markup('<span size="%d" weight="bold">%s</span>' % (self.font_size, time_str))

    def update_cache(self):
        """Update cached waypoints and airspace"""
        width, height = self.get_view_size()
        self.view_wps = self.flight.get_area_waypoint_list(
                                    self.viewx, self.viewy, width, height)

        airspace = self.flight.get_area_airspace(self.viewx, self.viewy,
                                                 width, height)
        self.airspace_lines = [x for a in airspace
                for x in self.flight.get_airspace_lines(a['id'])]
        self.airspace_arcs = [x for a in airspace
                for x in self.flight.get_airspace_arcs(a['id'])]

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
