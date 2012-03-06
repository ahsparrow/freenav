"""This module provides the view for the freenav program"""

import math
import os.path

import gobject
import gtk
import gtk.gdk
import pango

IS_HILDON_APP = True
try:
    import hildon
    APP_BASE = hildon.Program
except ImportError:
    IS_HILDON_APP = False
    APP_BASE = object

import mapcache
import nmeaparser

# Constants for drawing arcs
M_2PI = 2 * math.pi

# Conversion constants
M_TO_FT = 1 / 0.3048
MPS_TO_KTS = 3600 / 1852.0

# Map scale limits (metres per pixel)
SCALE = [6, 9, 12, 17, 25, 35, 50, 71, 100, 200, 400]
DEFAULT_SCALE = SCALE[4]
ZOOM_LABELS = ["2.5", "4", "6", "8", "12", "16", "25", "35",
               "50", "100", "200"]

# Number and size of info boxes
NUM_INFO_BOXES = 3
INFO_BOX_SIZE = 90

# Size of waypoint symbol
WP_SIZE = 5

# Size of final glide indicator
FG_WIDTH = 30
FG_INC = 15

# Time to display airspace info
AIRSPACE_TIMEOUT = 10000
LANDING_TIMEOUT = 10000

# Threshold (in feet) to display final glide indicator
FG_THRESHOLD = -3000

# Maximum flarm radar range
MAX_FLARM_RADAR = 2000.0

# Input matrix
NX_MATRIX = 3
NY_MATRIX = 4
MATRIX_SIZE = NX_MATRIX * NY_MATRIX

PIXMAP_DIRS = ['.', '/usr/share/pixmaps', '../../pixmaps']

def find_pixbuf(filename):
    """Searches for pixmap file and returns corresponding gtk.gdk.Pixbuf"""
    for pix_dir in PIXMAP_DIRS:
        path = os.path.join(pix_dir, filename)
        if os.path.isfile(path):
            pixbuf = gtk.gdk.pixbuf_new_from_file(path)

    return pixbuf

def add_div(box):
    """Add a dividing bar between box elements"""
    div = gtk.EventBox()
    div.modify_bg(gtk.STATE_NORMAL, div.get_colormap().alloc_color("black"))

    # Detect whether we are using horizontal or vertical layout
    if isinstance(box, gtk.VBox):
        # Horizontal bar
        div.set_size_request(-1, 3)
    else:
        # Vertical bar
        div.set_size_request(3, -1)

    box.pack_start(div, expand=False)

class BigButtonDialog(gtk.Window):
    """A dialog box with unusually big buttons"""
    def __init__(self, title=None, buttons=None, timeout=None):
        """Create all of the dialog box - except the message label"""
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_name('freenav-bigbuttondialog')
        self.set_modal(True)
        self.set_resizable(False)
        self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.set_title(title)

        self.timeout = timeout
        self.timeout_id = None

        self.connect("delete_event", self.delete_event)
        self.connect("map-event", self.map_event)

        self.vbox = gtk.VBox(spacing=10)
        self.vbox.set_border_width(5)
        self.add(self.vbox)

        button_box = gtk.HBox(homogeneous=True, spacing=10)
        button_box.set_size_request(300, 150)

        # buttons is list of button#1 name, response#1, button#2 name, ...
        for but, resp in zip(buttons[::2], buttons[1::2]):
            button = gtk.Button(stock=but)
            button.connect("clicked", self.callback, resp)
            button_box.pack_start(button)

        self.vbox.pack_end(button_box)

    def callback(self, _widget, data):
        """Button press callback"""
        self.response = data

        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        gtk.main_quit()

    def delete_event(self, _widget, _event):
        """Delete event callback"""
        self.response = gtk.RESPONSE_DELETE_EVENT

        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
        gtk.main_quit()

    def map_event(self, _widget, _event):
        if self.timeout:
            self.timeout_id = gobject.timeout_add(self.timeout, self.on_timeout)
        return False

    def run(self, label):
        """Add label, wait for button press, return response"""
        self.vbox.pack_start(label)
        self.show_all()

        gtk.main()
        return self.response

    def on_timeout(self):
        self.response = None
        gtk.main_quit()
        return False

class FreeView(APP_BASE):
    """Main view class"""
    def __init__(self, flight, fullscreen):
        """Class initialisation"""
        APP_BASE.__init__(self)

        self.flight = flight

        # Font size juju
        self.font_size = pango.SCALE

        # viewx/viewy is geographic position at center of window
        self.viewx = 0
        self.viewy = 0
        self.view_scale = DEFAULT_SCALE

        # Cache of displayed waypoints and airspace
        self.mapcache = mapcache.MapCache(flight)

        # Display element states
        self.divert_flag = False
        self.mute_flag = False
        self.track_log = False
        self.flarm_radar_flag = False
        self.matrix_flag = False

        # Pixmaps
        self.glider_pixbuf = find_pixbuf("free_glider.png")
        self.navarrow_pixbuf = find_pixbuf("free_navarrow.png")
        self.wind_pixbuf = find_pixbuf("free_wind.png")
        self.mute_pixbuf = find_pixbuf("free_muted.png")
        self.flarm_pixbuf = find_pixbuf("free_flarm.png")
        self.stealth_pixbuf = find_pixbuf("free_stealth.png")
        self.north_pixbuf = find_pixbuf("free_north.png")

        # Create top level window
        if IS_HILDON_APP:
            self.window = hildon.Window()
        else:
            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK)

        # Top level box
        topbox = gtk.VBox(homogeneous=False)
        self.window.add(topbox)

        # Main drawing area
        self.drawing_area = gtk.DrawingArea()
        self.drawing_area.add_events(gtk.gdk.BUTTON_PRESS_MASK |
                                     gtk.gdk.BUTTON_RELEASE_MASK)
        self.drawing_area.connect('expose-event', self.area_expose)
        topbox.pack_start(self.drawing_area, expand=True, fill=True)

        # Box for info boxes
        add_div(topbox)
        info_sizer = gtk.HBox(homogeneous=False)
        info_sizer.set_size_request(-1, INFO_BOX_SIZE)
        topbox.pack_end(info_sizer, expand=False)

        # Array of info boxes with event boxes to capture button presses
        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 45, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))

        self.info_box = []
        self.info_label = []
        self.size_group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
        for _dummy in range(NUM_INFO_BOXES):
            label = gtk.Label()
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

        # Create info boxes with dividing bars between
        info_sizer.pack_start(self.info_box[0])
        for ibox in self.info_box[1:]:
            add_div(info_sizer)
            info_sizer.pack_start(ibox)

        # Pango layouts for text on map display
        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 30, 0, 999))
        self.wp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.wp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 45, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.tp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.tp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 35, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.fg_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.fg_layout.set_attributes(attr_list)

        # Show the window
        if fullscreen:
            self.window.fullscreen()
        else:
            self.window.set_size_request(480, 700)
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

    def area_expose(self, area, _event):
        """Repaint the display"""
        win = area.window
        win_width, win_height = win.get_size()

        # Start with a clean white sheet...
        cr = win.cairo_create()
        cr.set_source_rgba(0, 0, 0, 1)
        cr.rectangle(0, 0, win_width, win_height)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 1)

        if self.matrix_flag:
            # Input button matrix
            self.draw_matrix(cr, win_width, win_height)
            return True

        if self.flarm_radar_flag:
            self.draw_flarm_radar(cr, win_width, win_height)
        else:
            # Airspace
            self.draw_airspace(cr, win_width, win_height)

            # Draw track log
            if self.track_log:
                self.draw_track_log(cr, win_width, win_height)

            # Task and turnpoint sectors
            self.draw_task(cr, win_width, win_height)

            # Waypoints
            self.draw_waypoints(cr)

            # Heading symbol
            self.draw_heading(cr, win_height, win_width)

            # Number of satellites
            self.draw_satellites(cr, win_width, win_height)

        # Final glide indicator
        self.draw_glide(cr, win_height)

        # Next turnpoint annotation and navigation
        self.draw_nav(cr, win_height)

        # Wind arrow
        self.draw_wind(cr, win_width, win_height)

        # Mute indicator
        self.draw_mute(cr, win_width)

        return True

    def draw_matrix(self, cr, win_width, win_height):
        """Draw user input matrix"""
        x_inc = win_width / NX_MATRIX
        y_inc = win_height / NY_MATRIX

        # Draw grid
        for x in range(1, NX_MATRIX):
            cr.move_to(x * x_inc, 0)
            cr.line_to(x * x_inc, win_height - 1)
            cr.stroke()

        for y in range(1, NY_MATRIX):
            cr.move_to(0, y * y_inc)
            cr.line_to(win_width - 1, y * y_inc)
            cr.stroke()

        # Draw labels
        font_size = self.font_size * 40
        markup_template = '<span weight="bold" size="%d" underline="%s">%s</span>'
        for n, txt in enumerate(self.matrix_labels):
            layout = pango.Layout(self.drawing_area.create_pango_context())
            if self.matrix_selected[n]:
                underline = "single"
            else:
                underline = "none"

            markup = markup_template % (font_size, underline, txt)
            layout.set_markup(markup)
            xs, ys = layout.get_pixel_size()

            x = ((n % NX_MATRIX) * x_inc) + (x_inc / 2) - (xs / 2)
            y = ((n / NX_MATRIX) * y_inc) + (y_inc / 2) - (ys / 2)
            cr.move_to(x, y)
            cr.show_layout(layout)

    def draw_flarm_radar(self, cr, win_width, win_height):
        """Display FLARM radar"""
        # Translate origin to center of screen
        cr.save()
        cr.translate(0.5 * win_width, 0.55 * win_height)

        # Draw range rings
        scale = (min(win_width, win_height) - 50) / (2.0 * MAX_FLARM_RADAR)
        cr.new_sub_path()
        cr.arc(0, 0, scale * MAX_FLARM_RADAR, 0, M_2PI)
        cr.new_sub_path()
        cr.arc(0, 0, scale * MAX_FLARM_RADAR / 2, 0, M_2PI)

        cr.save()
        cr.set_source_rgba(0.5, 0.65, 1, 1)
        cr.stroke()
        cr.restore()

        # North marker bug
        offset = self.north_pixbuf.get_width() / 2
        sin_track = math.sin(self.flight.track)
        cos_track = math.cos(self.flight.track)
        x = -scale * MAX_FLARM_RADAR * sin_track
        y = scale * MAX_FLARM_RADAR * cos_track

        cr.save()
        cr.translate(x, -y)
        cr.set_source_pixbuf(self.north_pixbuf, -offset, -offset)
        cr.paint()
        cr.restore()

        # Traffic
        offset = self.flarm_pixbuf.get_width() / 2
        for f in self.flight.flarm_traffic.values():
            x = scale * f.east
            y = scale * f.north
            xf = x * cos_track - y * sin_track
            yf = x * sin_track + y * cos_track

            cr.save()
            cr.translate(xf, -yf)

            # Annotation
            level = round(f.vertical * M_TO_FT / 100)
            self.wp_layout.set_text("%d" % level)
            pw, ph = self.wp_layout.get_pixel_size()
            if f.stealth:
                cr.move_to(offset - 4, -ph - 4)
                cr.show_layout(self.wp_layout)
            else:
                cr.move_to(offset, -ph + 4)
                cr.show_layout(self.wp_layout)
                if f.climb_rate > 0:
                    climb_rate = int(round(f.climb_rate))
                    self.wp_layout.set_text(str(climb_rate))
                    cr.move_to(offset, -2)
                    cr.show_layout(self.wp_layout)

            # Symbol
            cr.move_to(0, 0)
            if not f.stealth:
                cr.rotate(f.track - self.flight.track)
                pb = self.flarm_pixbuf
            else:
                pb = self.stealth_pixbuf

            cr.set_source_pixbuf(pb, -offset, -offset)
            cr.paint()
            cr.restore()

        # Restore transformation
        cr.restore()

    def draw_track_log(self, cr, win_width, win_height):
        """Draw track snail trail"""
        if len(self.flight.track_log) == 0:
            return

        cr.save()
        cr.translate(win_width / 2, win_height / 2)
        cr.scale(1.0 / self.view_scale, -1.0 / self.view_scale)
        cr.translate(-self.viewx, -self.viewy)

        utc, sp = self.flight.track_log[0]
        cr.move_to(*sp)
        for utc, p in self.flight.track_log:
            cr.line_to(*p)

        cr.restore()
        cr.set_line_width(1)
        cr.stroke()

    def draw_waypoints(self, cr):
        """Draw waypoints"""
        if self.divert_flag or self.flight.get_state() == 'Divert':
            # Landable waypoints
            fill = True
            wps = self.flight.db.get_landable_list()
        else:
            fill = False
            if self.view_scale > 71:
                # Task waypoints
                tps = [tp['id'] for tp in self.flight.task.tp_list]
                wps = filter(lambda x: x['id'] in tps, self.mapcache.wps)
            else:
                # All waypoints
                wps = self.mapcache.wps

        for wp in wps:
            # Draw a circle
            x, y = self.view_to_win(wp['x'], wp['y'])
            cr.new_sub_path()
            cr.arc(x, y, WP_SIZE, 0, M_2PI)

            # Waypoint ID text
            self.wp_layout.set_text(wp['id'])
            cr.move_to(x + WP_SIZE, y + WP_SIZE)
            cr.show_layout(self.wp_layout)

        if fill:
            # Draw landables as filled circle
            cr.fill()
        else:
            # Draw normal waypoints as outline circles
            cr.set_line_width(2)
            cr.stroke()

    def draw_airspace(self, cr, win_width, win_height):
        """Draw airspace boundary lines and arcs"""
        # Transform view to window coordinates
        cr.save()
        cr.translate(win_width / 2, win_height / 2)
        cr.scale(1.0 / self.view_scale, -1.0 / self.view_scale)
        cr.translate(-self.viewx, -self.viewy)

        # Airspace lines
        for as_id in self.mapcache.airspace_lines:
            for line in self.mapcache.airspace_lines[as_id]:
                cr.move_to(line['x1'], line['y1'])
                cr.line_to(line['x2'], line['y2'])

        # Airspace arcs & circles
        for as_id in self.mapcache.airspace_arcs:
            for arc in self.mapcache.airspace_arcs[as_id]:
                angle1 = arc['start']
                angle2 = angle1 + arc['length']

                cr.new_sub_path()
                if arc['length'] > 0:
                    cr.arc(arc['x'], arc['y'], arc['radius'], angle1, angle2)
                else:
                    cr.arc_negative(arc['x'], arc['y'], arc['radius'], angle1,
                                    angle2)

        # Restore transform
        cr.restore()

        # Draw lines... a beautiful shade of blue
        cr.save()
        cr.set_source_rgba(0.5, 0.65, 1, 1)
        cr.stroke()

        cr.restore()

    def draw_task(self, cr, win_width, win_height):
        """Draw task and turnpoint sectors"""
        task_points = [(tp['mindistx'], tp['mindisty'])
                       for tp in self.flight.task.tp_list]

        # Transform view to window coordinates
        cr.save()
        cr.translate(win_width / 2, win_height / 2)
        cr.scale(1.0 / self.view_scale, -1.0 / self.view_scale)
        cr.translate(-self.viewx, -self.viewy)

        # Draw task legs
        cr.move_to(*task_points[0])
        for task_point in task_points[1:]:
            cr.line_to(*task_point)

        # Draw sectors
        if len(self.flight.task.tp_list) > 1:
            for tp in self.flight.task.tp_list:
                if tp['tp_type'] == 'LINE':
                    self.draw_tp_line(cr, tp)
                else:
                    self.draw_tp_sector(cr, tp)

        cr.restore()
        cr.set_line_width(2)
        cr.stroke()

    def draw_tp_line(self, cr, tp):
        """Draw turnpoint (finish) line"""
        angle = math.radians(tp['angle12'])
        dx = -tp['radius1'] * math.cos(angle)
        dy = tp['radius1'] * math.sin(angle)

        x1, y1 = tp['x'] + dx, tp['y'] + dy
        x2, y2 = tp['x'] - dx, tp['y'] - dy
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)

    def draw_tp_sector(self, cr, tp):
        """Draw turnpoint sector"""
        x, y = tp['x'], tp['y']
        radius1 = tp['radius1']
        radius2 = tp['radius2']
        oz_angle1 = math.radians(tp['angle1'])
        oz_angle2 = math.radians(tp['angle2'])
        oz_angle = -math.radians(90 + tp['angle12'])

        # Outer arc
        ang1 = oz_angle - (oz_angle1 / 2)
        ang2 = oz_angle + (oz_angle1 / 2)
        cr.new_sub_path()
        cr.arc(x, y, radius1, ang1, ang2)

        if abs(oz_angle1 - M_2PI) < 0.01:
            return

        # Outer radials
        self.draw_radial(cr, x, y, ang1, radius1, radius2)
        self.draw_radial(cr, x, y, ang2, radius1, radius2)

        if radius2 == 0:
            return

        # Inner arc
        ang1_inner = oz_angle - (oz_angle2 / 2)
        ang2_inner = oz_angle + (oz_angle2 / 2)

        cr.new_sub_path()
        if oz_angle1 > oz_angle2:
            cr.arc(x, y, radius2, ang1, ang1_inner)
            cr.new_sub_path()
            cr.arc(x, y, radius2, ang2_inner, ang2)
        else:
            cr.arc_negative(x, y, radius2, ang1, ang1_inner)
            cr.new_sub_path()
            cr.arc_negative(x, y, radius2, ang2_inner, ang2)

        if (oz_angle2 == 0) or abs(oz_angle2 - M_2PI) < 0.01:
            return

        # Inner radials
        self.draw_radial(cr, x, y, ang1_inner, 0, radius2)
        self.draw_radial(cr, x, y, ang2_inner, 0, radius2)

    def draw_radial(self, cr, x, y, angle, radius1, radius2):
        """Draw a radial line"""
        cos_ang = math.cos(angle)
        sin_ang = math.sin(angle)

        x1, y1 = x + radius1 * cos_ang, y + radius1 * sin_ang
        x2, y2 = x + radius2 * cos_ang, y + radius2 * sin_ang
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)

    def draw_nav(self, cr, win_height):
        """Draw turnpoint annotation and direction pointer"""
        nav = self.flight.task.get_nav()

        # Annotation
        bearing = math.degrees(nav['bearing']) % 360
        dist_km = nav['distance'] / 1000

        self.tp_layout.set_text('%s %.1f/%.0f' % (nav['id'], dist_km, bearing))
        x, y = self.tp_layout.get_pixel_size()
        cr.move_to(2, win_height - y)

        # Draw text with black outline
        cr.layout_path(self.tp_layout)
        cr.save()
        cr.set_line_width(5)
        cr.set_source_rgba(0, 0, 0, 1)
        cr.stroke_preserve()
        cr.set_source_rgba(1, 1, 1, 1)
        cr.fill()

        # Draw arrow for relative bearing to TP
        relative_bearing = nav['bearing'] - self.flight.get_velocity()['track']

        width = self.navarrow_pixbuf.get_width()
        height = self.navarrow_pixbuf.get_height()

        cr.save()
        cr.translate(40, 40)
        cr.rotate(relative_bearing)
        cr.set_source_pixbuf(self.navarrow_pixbuf, -width / 2, -height / 2)
        cr.paint()
        cr.restore()

    def draw_glide(self, cr, win_height):
        """Draw final glide information"""
        glide = self.flight.task.get_glide()
        glide_height = glide['height'] * M_TO_FT

        if glide_height < FG_THRESHOLD:
            return

        cr.save()
        cr.set_line_width(3)
        cr.translate(0, win_height / 2)

        # Draw origin line
        cr.move_to(0, 0)
        cr.line_to(FG_WIDTH + 2, 0)

        # Draw chevrons
        num_arrows = abs(int(glide['margin'] * 20))
        cr.save()
        if glide['margin'] > 0:
            # Reverse scale if above glide
            cr.scale(1, -1)

        for n in range(min(num_arrows, 5)):
            y = FG_INC * (n  + 0.5)
            cr.move_to(1, y)
            cr.line_to((FG_WIDTH / 2) + 1, y + FG_INC)
            cr.line_to(FG_WIDTH + 1, y)

        # Draw limit bar
        if num_arrows > 5:
            y = y + FG_INC + 4
            cr.move_to(0, y)
            cr.line_to(FG_WIDTH + 2, y)

        cr.stroke()
        cr.restore()

        # Arrival height, MacCready and ETE
        ete_mins = glide['ete'] / 60
        if ete_mins >= 600:
            ete_str = '-:--'
        else:
            ete_str = "%d:%02d" % (ete_mins / 60, ete_mins % 60)

        fmt = '%d\n%s\n%.1f'
        self.fg_layout.set_text(fmt % (glide_height, ete_str,
                                       glide['maccready'] * MPS_TO_KTS))
        x, y = self.fg_layout.get_pixel_size()
        cr.move_to(FG_WIDTH + 5, -(2 * y / 3))
        cr.show_layout(self.fg_layout)

        cr.restore()

    def draw_heading(self, cr, win_height, win_width):
        """Draw heading glider symbol"""
        width = self.glider_pixbuf.get_width()
        height = self.glider_pixbuf.get_height()

        cr.save()
        cr.translate(win_width / 2, win_height / 2)
        cr.rotate(self.flight.get_velocity()['track'])

        cr.set_source_pixbuf(self.glider_pixbuf, -width / 2, -height / 2)
        cr.paint()
        cr.restore()

    def draw_wind(self, cr, win_width, win_height):
        """Draw wind speed/direction"""
        wind = self.flight.get_wind()

        cr.save()
        cr.translate(win_width - 40, 40)

        # Draw wind speed value
        speed = wind['speed'] * MPS_TO_KTS
        self.fg_layout.set_text(str(int(speed)))

        x, y = self.fg_layout.get_pixel_size()
        cr.move_to(-x - 40, -y / 2)
        cr.show_layout(self.fg_layout)

        # Draw wind speed direction
        width = self.wind_pixbuf.get_width()
        height = self.wind_pixbuf.get_height()

        cr.rotate(wind['direction'])
        cr.set_source_pixbuf(self.wind_pixbuf, -width / 2, -height / 2)
        cr.paint()
        cr.restore()

        # Draw ground speed value
        ground_speed = self.flight.get_velocity()['speed'] * MPS_TO_KTS
        self.fg_layout.set_text("%d" % ground_speed)

        x, y = self.fg_layout.get_pixel_size()
        cr.move_to(win_width - x - 2, win_height - y)
        cr.show_layout(self.fg_layout)

    def draw_satellites(self, cr, win_width, win_height):
        """Draw number of satellites in view"""
        fix_quality = self.flight.get_fix_quality()
        txt = "%d" % fix_quality['satellites']
        if fix_quality['quality'] == nmeaparser.FIX_QUALITY_DGPS:
            txt += "D"

        self.fg_layout.set_text(txt)
        x, y = self.fg_layout.get_pixel_size()
        cr.move_to(win_width - x - 2, win_height - (2 * y))
        cr.show_layout(self.fg_layout)

    def draw_mute(self, cr, win_width):
        """Draw mute indicator"""
        if self.mute_flag:
            width = self.mute_pixbuf.get_width()

            cr.save()
            cr.translate(win_width / 2, 4)
            cr.set_source_pixbuf(self.mute_pixbuf, -width / 2, 0)
            cr.paint()
            cr.restore()

    # External methods - for use by controller
    def redraw(self, reload_map=False):
        """Redraw display"""
        if reload_map:
            width, height = self.get_view_size()
            self.mapcache.reload(self.viewx, self.viewy, width, height)

        self.window.queue_draw()

    def update_position(self, x, y):
        """Update position of view and redraw"""
        self.viewx = x
        self.viewy = y

        width, height = self.get_view_size()
        self.mapcache.update(x, y, width, height)

        self.redraw()

    def set_zoom(self, level, reload_map=True):
        """Set zoom level"""
        if (level >= 0) and (level < len(SCALE)):
            self.view_scale = SCALE[level]

        # Big change in view, so reload the cache
        if reload_map:
            width, height = self.get_view_size()
            self.mapcache.reload(self.viewx, self.viewy, width, height)

    def zoom_out(self, reload_map=True):
        """See some more"""
        ind = SCALE.index(self.view_scale)
        self.set_zoom(ind + 1, reload_map)

    def zoom_in(self, reload_map=True):
        """See some less"""
        ind = SCALE.index(self.view_scale)
        self.set_zoom(ind - 1, reload_map)

    def show_airspace_info(self, airspace_info):
        """Show message dialog with aispace info message"""
        msgs = []
        for info in airspace_info:
            msgs.append("%s\n%s, %s" % info)

        if msgs:
            msg = "\n\n".join(msgs)
            dialog = BigButtonDialog("Airspace",
                                     (gtk.STOCK_OK, gtk.RESPONSE_OK),
                                     timeout=AIRSPACE_TIMEOUT)

            attr_list = pango.AttrList()
            attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 30,
                                                    0, 999))
            label = gtk.Label(msg)
            label.set_attributes(attr_list)

            dialog.run(label)
            dialog.destroy()

    def confirm_dialog(self, question):
        """Puts up a dialog box to ask whether to send an SMS"""
        dialog = BigButtonDialog("SMS", (gtk.STOCK_YES, gtk.RESPONSE_YES,
                                         gtk.STOCK_NO, gtk.RESPONSE_NO),
                                         timeout=LANDING_TIMEOUT)
        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 40, 0, 999))

        label = gtk.Label(question)
        label.set_attributes(attr_list)

        result = dialog.run(label)
        dialog.destroy()

        return result

    def set_divert_indicator(self, flag):
        """Set indicator showing divert select is active"""
        self.divert_flag = flag
        self.redraw()

    def set_mute_indicator(self, flag):
        """Set indicator showing mute is active"""
        self.mute_flag = flag
        self.redraw()

    def set_flarm_radar(self, flag):
        """Set flarm radar display mode"""
        self.flarm_radar_flag = flag
        self.redraw()

    def set_matrix(self, labels, selected):
        """Display input matrix"""
        self.matrix_flag = True
        self.matrix_labels = labels
        self.matrix_selected = selected
        self.redraw()

    def cancel_matrix(self):
        """Cancel input matrix display"""
        self.matrix_flag = False
        self.redraw()

    def get_button_region(self, x, y):
        """Return "button" id of drawing area"""
        win_width, win_height = self.drawing_area.window.get_size()

        if self.matrix_flag:
            # Input matrix mode
            mode = "matrix"
            val = (int((float(x) / win_width) * NX_MATRIX) +
                   int((float(y) / win_height) * NY_MATRIX) * NX_MATRIX)

            # Return None if label is blank
            if val >= len(self.matrix_labels):
                val = None

        else:
            # Normal display mode
            mode = "view"
            delta = win_width / 3
            left = x < delta
            right = x > (win_width - delta)
            top = y < 75
            bottom = y > (win_height - 75)
            vertical_middle = abs(y - (win_height / 2)) < 50

            if top:
                if left:
                    val = 'divert'
                elif right:
                    val = 'flarm'
                else:
                    val = 'zoom'
            elif bottom:
                if left:
                    val = 'next'
                elif right:
                    val = 'prev'
                else:
                    val = 'menu'
            elif vertical_middle and (x < 50):
                val = 'glide'
            else:
                val = 'background'

        return (mode, val)
