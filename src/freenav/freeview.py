import math
import time

import gtk, gobject, pango
import gtk.gdk

is_hildon_app = True
try:
    import hildon
    AppBase = hildon.Program
except ImportError:
    is_hildon_app = False
    AppBase = object

import mapcache

# Constants for drawing arcs
ARC_LEN = 64
CIRCLE_LEN = 360 * ARC_LEN

M_TO_FT = 1 / 0.3048
MPS_TO_KTS = 3600 / 1852.0

# Map scale limits (metres per pixel)
SCALE = [6, 9, 12, 17, 25, 35, 50, 71, 100, 141, 200, 282, 400]
DEFAULT_SCALE = SCALE[4]

# Number and size of info boxes
NUM_INFO_BOXES = 3
INFO_BOX_SIZE = 90

# Size of waypoint symbol
WP_SIZE = 10

# Size of final glide indicator
FG_WIDTH = 30
FG_INC = 15

def html_escape(html):
    """Escape HTML specific characters from pango markup string"""
    html = html.replace('&', '&amp;')
    html = html.replace('"', '&quot;')
    html = html.replace("'", '&#39;')
    html = html.replace(">", '&gt;')
    html = html.replace("<", '&lt;')
    return html

def add_div(box):
    """Add a dividing bar between box elements"""
    div = gtk.EventBox()
    div.modify_bg(gtk.STATE_NORMAL, div.get_colormap().alloc_color("black"))
    if isinstance(box, gtk.VBox):
        div.set_size_request(-1, 3)
    else:
        div.set_size_request(3, -1)
    box.pack_start(div, expand=False)

class BigButtonDialog(gtk.Window):
    def __init__(self, title=None, buttons=None):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.set_title(title)

        self.connect("delete_event", self.delete_event)

        self.vbox = gtk.VBox(spacing=10)
        self.vbox.set_border_width(5)
        self.add(self.vbox)

        button_box = gtk.HBox(homogeneous=True, spacing=10)
        button_box.set_size_request(300, 150)
        for (b, resp) in zip(buttons[::2], buttons[1::2]):
            button = gtk.Button(stock=b)
            button.connect("clicked", self.callback, resp)
            button_box.pack_start(button)

        self.vbox.pack_end(button_box)

    def set_label(self, widget):
        self.vbox.pack_start(widget)

    def callback(self, widget, data):
        self.response = data
        gtk.main_quit()

    def delete_event(self, widget, event):
        self.response = gtk.RESPONSE_DELETE_EVENT
        gtk.main_quit()

    def run(self):
        gtk.main()
        return self.response

class FreeView(AppBase):
    def __init__(self, flight, fullscreen):
        AppBase.__init__(self)

        self.flight = flight

        # Font size juju
        self.font_size = pango.SCALE

        # viewx/viewy is geographic position at center of window
        self.viewx = 0
        self.viewy = 0
        self.view_scale = DEFAULT_SCALE

        # Cache of displayed waypoints and airspace
        self.mapcache = mapcache.MapCache(flight)

        self.divert_flag = False
        self.maccready_flag = False

        # Create top level window
        if is_hildon_app:
            self.window = hildon.Window()
        else:
            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK)

        # Top level box
        topbox = gtk.VBox(homogeneous=False)
        self.window.add(topbox)

        # Main drawing area
        self.drawing_area = gtk.DrawingArea()
        self.drawing_area.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.drawing_area.connect('expose-event', self.area_expose)
        topbox.pack_start(self.drawing_area, expand=True, fill=True)

        # Allocate some drawing colours
        cmap = self.drawing_area.get_colormap()
        self.airspace_color = cmap.alloc_color("blue")
        self.bg_color = cmap.alloc_color("white")
        self.fg_color = cmap.alloc_color("black")

        # Box for info boxes
        add_div(topbox)
        info_sizer = gtk.HBox(homogeneous=False)
        info_sizer.set_size_request(-1, INFO_BOX_SIZE)
        topbox.pack_end(info_sizer, expand=False)

        # Array of info boxes with event boxes to capture button presses
        self.info_box = []
        self.info_label = []
        self.size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        for i in range(NUM_INFO_BOXES):
            label = gtk.Label()
            attr_list = pango.AttrList()
            attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 40,
                                                    0, 999))
            attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
            label.set_attributes(attr_list)

            align = gtk.Alignment(xalign=0.5, yalign=0.5)
            align.add(label)
            ebox = gtk.EventBox()
            ebox.add(align)
            ebox.add_events(gtk.gdk.BUTTON_PRESS_MASK)
            ebox.modify_bg(gtk.STATE_NORMAL,
                           ebox.get_colormap().alloc_color("white"))
            self.info_box.append(ebox)
            self.info_label.append(label)
            self.size_group.add_widget(ebox)

        info_sizer.pack_start(self.info_box[0])
        for ibox in self.info_box[1:]:
            add_div(info_sizer)
            info_sizer.pack_start(ibox)

        # Pango layouts for text on map display
        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 25, 0, 999))
        self.wp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.wp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 40, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.tp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.tp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 35, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.fg_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.fg_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 35, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.wind_layout = pango.Layout(
                self.drawing_area.create_pango_context())
        self.wind_layout.set_attributes(attr_list)

        # Show the window
        if fullscreen:
            self.window.fullscreen()
        else:
            self.window.set_size_request(480, 750)
        self.window.show_all()

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
        self.draw_waypoints(win, gc)

        # Next turnpoint annotation and course
        self.draw_turnpoint(gc, win, win_height)

        # Final glide indicator
        gc.line_width = 3
        self.draw_glide(gc, win, win_height)

        # Heading symbol
        gc.line_width = 2
        self.draw_heading(gc, win, win_height, win_width)

        # Wind arrow
        gc.line_width = 2
        self.draw_wind(gc, win, win_width, win_height)

        # Number of satellites
        self.draw_satellites(gc, win, win_width, win_height)

        return True

    def draw_waypoints(self, win, gc):
        """Draw waypoints"""
        tps = [tp['id'] for tp in self.flight.task.tp_list]
        for wp in self.mapcache.wps:
            if self.view_scale <= 71 or wp['landable_flag'] or wp['id'] in tps:
                x, y = self.view_to_win(wp['x'], wp['y'])
                delta = WP_SIZE / 2
                win.draw_arc(gc, wp['landable_flag'],
                             x - delta, y - delta,
                             WP_SIZE, WP_SIZE, 0, CIRCLE_LEN)

                self.wp_layout.set_text(wp['id'])
                win.draw_layout(gc, x + delta, y + delta, self.wp_layout)

    def draw_airspace(self, gc, win):
        """Draw airspace boundary lines and arcs"""
        # Airspace lines
        for id in self.mapcache.airspace_lines:
            for line in self.mapcache.airspace_lines[id]:
                x1, y1 = self.view_to_win(line['x1'], line['y1'])
                x2, y2 = self.view_to_win(line['x2'], line['y2'])
                win.draw_line(gc, x1, y1, x2, y2)

        # Airspace arcs & circles
        for id in self.mapcache.airspace_arcs:
            for arc in self.mapcache.airspace_arcs[id]:
                radius = arc['radius']
                x, y = self.view_to_win(arc['x'] - radius, arc['y'] + radius)
                width = 2 * arc['radius'] / self.view_scale
                win.draw_arc(gc, False, x, y, width, width, arc['start'],
                             arc['length'])

    def draw_task(self, gc, win):
        """Draw task and turnpoint sectors"""
        pts = [self.view_to_win(tp['mindistx'], tp['mindisty'])
               for tp in self.flight.task.tp_list]
        win.draw_lines(gc, pts)

        # Draw sectors
        if len(self.flight.task.tp_list) > 1:
            for tp in self.flight.task.tp_list[:-1]:
                self.draw_tp_sector(gc, win, tp)

            # Draw finish line
            self.draw_tp_line(gc, win, self.flight.task.tp_list[-1])

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

    def draw_turnpoint(self, gc, win, win_height):
        """Draw turnpoint annotation and direction pointer"""
        nav = self.flight.get_nav()
        bearing = math.degrees(nav['bearing']) % 360

        dist_km = nav['distance'] / 1000
        self.tp_layout.set_text('%s %.1f/%.0f' % (nav['id'], dist_km, bearing))
        x, y = self.tp_layout.get_pixel_size()

        win.draw_layout(gc, 2, win_height - y, self.tp_layout,
                        background=self.bg_color)

        # Draw arrow for relative bearing to TP
        rb = nav['bearing'] - self.flight.get_velocity()['track']
        x, y = math.sin(rb), -math.cos(rb)

        xc = 40
        yc = 40
        a, b, c = 30, 10, 20

        x0, y0 = x * a, y * a
        xp = [x0, -x0 - y * c, -x * b, -x0 + y * c]
        yp = [y0, -y0 + x * c, -y * b, -y0 - x * c]
        poly = [(int(x + xc + 0.5), int(y + yc + 0.5)) for x, y in zip(xp, yp)]

        filled = (self.divert_flag == False)
        win.draw_polygon(gc, filled, poly)

    def draw_glide(self, gc, win, win_height):
        """Draw final glide information"""
        glide = self.flight.task.get_glide()

        # Draw origin
        y = win_height / 2
        win.draw_line(gc, 1, y, FG_WIDTH + 1, y)

        # Draw chevrons
        num_arrows = abs(int(glide['margin'] * 20))
        if glide['margin'] > 0:
            yinc = -FG_INC
        else:
            yinc =  FG_INC
        y = y - yinc / 2

        for i in range(min(num_arrows, 5)):
            y =  y + yinc
            win.draw_lines(gc, [(1, y), ((FG_WIDTH / 2) + 1, y + yinc),
                                (FG_WIDTH + 1, y)])
        # Draw limit bar
        if num_arrows > 5:
            if yinc > 0:
                y = y + yinc + gc.line_width
            else:
                y = y + yinc - gc.line_width
            win.draw_line(gc, 1, y, FG_WIDTH + 1, y)

        # Arrival height, MacCready and ETE
        ete_mins = glide['ete'] / 60
        if ete_mins >= 600:
            ete_str = '-:--'
        else:
            ete_str = "%d:%02d" % (ete_mins / 60, ete_mins % 60)

        if self.maccready_flag:
            fmt = '%d\n%s\n%.1f*'
        else:
            fmt = '%d\n%s\n%.1f'
        self.fg_layout.set_text(fmt % (glide['height'] * M_TO_FT, ete_str,
                                       glide['maccready'] * MPS_TO_KTS))
        x, y = self.fg_layout.get_pixel_size()
        win.draw_layout(gc, FG_WIDTH + 5, (win_height / 2) - (2 * y / 3),
                        self.fg_layout, background=None)

    def draw_heading(self, gc, win, win_height, win_width):
        """Draw heading glider symbol"""
        xc = win_width / 2
        yc = win_height / 2

        vel = self.flight.get_velocity()
        x = math.sin(vel['track'])
        y = -math.cos(vel['track'])
        a, b, c, d = 15, 30, 45, 15
        cf = [x * a, y * a, -x * b, -y * b]
        cw = [y * c, -x * c, -y * c, x * c]
        ct = [-x * b + y * d, -y * b - x * d, -x * b - y * d, -y * b + x * d]

        for x1, y1, x2, y2 in (cf, cw, ct):
            win.draw_line(gc, int(xc + x1 + 0.5), int(yc + y1 + 0.5),
                              int(xc + x2 + 0.5), int(yc + y2 + 0.5))

    def draw_wind(self, gc, win, win_width, win_height):
        """Draw wind speed/direction"""
        wind = self.flight.get_wind()
        x = math.sin(wind['direction'])
        y = -math.cos(wind['direction'])
        xc = win_width - 40 
        yc = 40
        a, b, c = 30, 6, 14

        x0, y0 = x * a, y * a
        xp = [x0, -x0 - y * c, -x * b, -x0 + y * c]
        yp = [y0, -y0 + x * c, -y * b, -y0 - x * c]
        poly = [(int(x + xc + 0.5), int(y + yc + 0.5)) for x, y in zip(xp, yp)]

        win.draw_polygon(gc, False, poly)

        speed = wind['speed'] * MPS_TO_KTS
        self.wind_layout.set_text(str(int(speed)))
        x, y = self.wind_layout.get_pixel_size()

        win.draw_layout(gc, xc - x - 40, yc - y / 2, self.wind_layout,
                        background=None)

        ground_speed = self.flight.get_velocity()['speed'] * MPS_TO_KTS
        self.wind_layout.set_text(str(int(ground_speed)))
        x, y = self.wind_layout.get_pixel_size()

        win.draw_layout(gc, win_width - x - 2, win_height - y,
                        self.wind_layout, background=None)

    def draw_satellites(self, gc, win, win_width, win_height):
        """Draw number of satellites in view"""
        self.wind_layout.set_text('%d' % self.flight.get_num_satellites())
        x, y = self.wind_layout.get_pixel_size()
        win.draw_layout(gc, win_width - x - 2, win_height - (2 * y),
                        self.wind_layout, background=None)

    # External methods - for use by controller
    def redraw(self):
        """Redraw display"""
        self.window.queue_draw()

    def update_position(self, x, y):
        """Update position of view and redraw"""
        self.viewx = x
        self.viewy = y

        width, height = self.get_view_size()
        self.mapcache.update(x, y, width, height)

        self.redraw()

    def zoom_out(self):
        """See some more"""
        ind = SCALE.index(self.view_scale)
        if ind < (len(SCALE) - 1):
            self.view_scale = SCALE[ind + 1]

            # Big change in view, so reload the cache
            width, height = self.get_view_size()
            self.mapcache.reload(self.viewx, self.viewy, width, height)

    def zoom_in(self):
        """See some less"""
        ind = SCALE.index(self.view_scale)
        if ind > 0:
            self.view_scale = SCALE[ind - 1]

            # Big change in view, so reload the cache
            width, height = self.get_view_size()
            self.mapcache.reload(self.viewx, self.viewy, width, height)

    def show_airspace_info(self, airspace_info):
        """Show message dialog with aispace info message"""
        msgs = []
        for info in airspace_info:
            msgs.append("%s\n%s, %s" % info)

        if msgs:
            msg = "\n\n".join(msgs)
            dialog = BigButtonDialog("Airspace",
                                     (gtk.STOCK_OK, gtk.RESPONSE_OK))

            attr_list = pango.AttrList()
            attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 30,
                                                    0, 999))
            label = gtk.Label(msg)
            label.set_attributes(attr_list)
            dialog.set_label(label)

            dialog.show_all()
            dialog.run()
            dialog.destroy()

    def task_start_dialog(self):
        """ Puts up a dialog to ask whether or not task to be started"""
        dialog = BigButtonDialog("Start", (gtk.STOCK_YES, gtk.RESPONSE_YES,
                                           gtk.STOCK_NO, gtk.RESPONSE_NO))
        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 40, 0, 999))

        label = gtk.Label("Start?")
        label.set_attributes(attr_list)
        dialog.set_label(label)

        dialog.show_all()
        ret = dialog.run()
        dialog.destroy()

        return ret

    def set_divert_indicator(self, flag):
        # Set indicator showing divert select is active
        self.divert_flag = flag
        self.redraw()

    def set_maccready_indicator(self, flag):
        # Set indicator showing Maccready is active
        self.maccready_flag = flag
        self.redraw()

    def get_button_region(self, x, y):
        win_width, win_height = self.drawing_area.window.get_size()
        if x < 75:
            if y < 100:
                return 'divert'
            elif y > (win_height - 100):
                return 'turnpoint'
            elif abs(y - (win_height / 2)) < 50:
                return 'glide'
            else:
                return 'background'
        else:
            return 'background'

