"""This module provides the view for the freenav program"""

import math
import os.path

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

# Constants for drawing arcs
M_2PI = 2 * math.pi

M_TO_FT = 1 / 0.3048
MPS_TO_KTS = 3600 / 1852.0

# Map scale limits (metres per pixel)
SCALE = [6, 9, 12, 17, 25, 35, 50, 71, 100, 141, 200, 282, 400]
DEFAULT_SCALE = SCALE[4]

# Number and size of info boxes
NUM_INFO_BOXES = 3
INFO_BOX_SIZE = 90

# Size of waypoint symbol
WP_SIZE = 5

# Size of final glide indicator
FG_WIDTH = 30
FG_INC = 15

# Threshold (in feet) to display final glide indicator
FG_THRESHOLD = -3000

ICON = [
"32 32 9 1",
" 	c None",
".	c #FFFFFF",
"+	c #494949",
"@	c #000000",
"#	c #B6B6B6",
"$	c #DBDBDB",
"%	c #242424",
"&	c #929292",
"*	c #6D6D6D",
"...............+@#..............",
".....$$$.......%@%..............",
"....$+%+#......@@@%#$...........",
"....$%@@+#....$@@@@@@@+&#.......",
"....$+@@@+$...#@@@@@@@@@@@&.....",
".....#+@@%#...#@%.%@@@@@@@@%#...",
"......#%@@+#..&@%.$%@@@@@@@@@#..",
"......$+@@@+#.*@+...#*+@@@@@@@$.",
".......#+@@@+$+@*.......$*%@@@*.",
"........#+@@%#+@&..........+@@+.",
".........#%@@+%@&...........+@%.",
".........$+@@@@@#...........$@%.",
"..........#+@@@@#............+@.",
"...........#+@@@&............#@.",
"............#%@@+#............$.",
"............$%@@@+#.............",
".............+@@@@+$............",
".............*@%@@%#............",
".............+@+%@@+#...........",
".............%@*+@@@+#..........",
"....$#***&$..%@##+@@@+$.........",
"..$+@@@@@@@+$@@#.#+@@%#.........",
".$%@@%+++%@@@@@$..#%@@+#........",
".%%&......$&%@@$..$+@@@+#.......",
"&%...........%@....#+@@@+$......",
"+#...........#%.....#+@@%#......",
"*#...........#%......#%@@+#.....",
"&%$.........$%*......$+@@@+$....",
".+@*$.....#*@@$.......#+@@%$....",
".$%@@@%%%@@@%#.........#+%+$....",
"...&%@@@@@@*$...........$$$.....",
".....$&&&#......................"]

PIXMAP_DIRS = ['.', '/usr/share/pixmaps', '../../pixmaps']

def find_pixbuf(filename):
    """Searches for pixmap file and returns corresponding gtk.gdk.Pixbuf"""
    for dir in PIXMAP_DIRS:
        path = os.path.join(dir, filename)
        if os.path.isfile(path):
            pixbuf = gtk.gdk.pixbuf_new_from_file(path)

    return pixbuf

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
    """Dialog box with unusually big buttons"""
    def __init__(self, title=None, buttons=None):
        gtk.Window.__init__(self, gtk.WINDOW_TOPLEVEL)
        self.set_name('freenav-bigbuttondialog')
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
        for but, resp in zip(buttons[::2], buttons[1::2]):
            button = gtk.Button(stock=but)
            button.connect("clicked", self.callback, resp)
            button_box.pack_start(button)

        self.vbox.pack_end(button_box)

    def set_label(self, widget):
        """Set dialog box label"""
        self.vbox.pack_start(widget)

    def callback(self, _widget, data):
        """Button press callback"""
        self.response = data
        gtk.main_quit()

    def delete_event(self, _widget, _event):
        """Delete event callback"""
        self.response = gtk.RESPONSE_DELETE_EVENT
        gtk.main_quit()

    def run(self):
        """Start the dialog box and return button press response"""
        gtk.main()
        return self.response

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

        self.divert_flag = False
        self.maccready_flag = False
        self.mute_flag = False

        # Pixmaps
        self.glider_pixbuf = find_pixbuf("free_glider.png")
        self.navarrow_pixbuf = find_pixbuf("free_navarrow.png")
        self.wind_pixbuf = find_pixbuf("free_wind.png")

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
        self.drawing_area.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.drawing_area.connect('expose-event', self.area_expose)
        topbox.pack_start(self.drawing_area, expand=True, fill=True)

        # Allocate some drawing colours
        cmap = self.drawing_area.get_colormap()
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
        for _dummy in range(NUM_INFO_BOXES):
            label = gtk.Label()
            attr_list = pango.AttrList()
            attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 45,
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
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 30, 0, 999))
        self.wp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.wp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 45, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.tp_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.tp_layout.set_attributes(attr_list)

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrSizeAbsolute(self.font_size * 40, 0, 999))
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, 999))
        self.fg_layout = pango.Layout(self.drawing_area.create_pango_context())
        self.fg_layout.set_attributes(attr_list)

        # Show the window
        if fullscreen:
            self.window.fullscreen()
        else:
            self.window.set_size_request(480, 700)
        self.window.show_all()

        # Mute pixmap
        self.mute_pixmap, _mask = gtk.gdk.pixmap_create_from_xpm_d(
            self.drawing_area.window, None, ICON)

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

        gc = win.new_gc()
        cr = win.cairo_create()

        # Start with a blank sheet...
        gc.foreground = self.bg_color
        win.draw_rectangle(gc, True, 0, 0, win_width, win_height)
        gc.foreground = self.fg_color

        # Airspace
        self.draw_airspace(cr, win_width, win_height)

        # Task and turnpoint sectors
        self.draw_task(cr, win_width, win_height)

        # Waypoints
        self.draw_waypoints(win, gc, cr)

        # Next turnpoint annotation and course
        self.draw_turnpoint(cr, gc, win, win_height)

        # Final glide indicator
        self.draw_glide(gc, win, win_height)

        # Heading symbol
        self.draw_heading(self.flight.get_velocity()['track'], cr, win_height,
                          win_width)

        # Wind arrow
        self.draw_wind(cr, gc, win, win_width, win_height)

        # Number of satellites
        self.draw_satellites(gc, win, win_width, win_height)

        # Mute indicator
        self.draw_mute(gc, win, win_width)

        return True

    def draw_waypoints(self, win, gc, cr):
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
                wps = self.mapcache.wps

        cr.save()
        for wp in wps:
            # Draw a circle
            x, y = self.view_to_win(wp['x'], wp['y'])
            cr.new_sub_path()
            cr.arc(x, y, WP_SIZE, 0, M_2PI)

            # Waypoint ID
            self.wp_layout.set_text(wp['id'])
            win.draw_layout(gc, x + WP_SIZE, y + WP_SIZE, self.wp_layout)

        if fill:
            cr.fill()
        else:
            cr.set_line_width(2)
            cr.stroke()
        cr.restore()

    def draw_airspace(self, cr, win_width, win_height):
        """Draw airspace boundary lines and arcs"""
        cr.save()
        cr.set_line_width(2)
        cr.set_source_rgba(0, 0, 1, 1)

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
        cr.stroke()

        cr.restore()

    def draw_task(self, cr, win_width, win_height):
        """Draw task and turnpoint sectors"""
        pts = [(tp['mindistx'], tp['mindisty'])
               for tp in self.flight.task.tp_list]

        # Transform view to window coordinates
        cr.save()
        cr.translate(win_width / 2, win_height / 2)
        cr.scale(1.0 / self.view_scale, -1.0 / self.view_scale)
        cr.translate(-self.viewx, -self.viewy)

        # Draw task legs
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)

        # Draw sectors
        if len(self.flight.task.tp_list) > 1:
            for tp in self.flight.task.tp_list[:-1]:
                self.draw_tp_sector(cr, tp)

            # Draw finish line
            self.draw_tp_line(cr, self.flight.task.tp_list[-1])

        cr.restore()
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

    def draw_turnpoint(self, cr, gc, win, win_height):
        """Draw turnpoint annotation and direction pointer"""
        nav = self.flight.get_nav()

        # Annotation
        bearing = math.degrees(nav['bearing']) % 360
        dist_km = nav['distance'] / 1000

        self.tp_layout.set_text('%s %.1f/%.0f' % (nav['id'], dist_km, bearing))
        x, y = self.tp_layout.get_pixel_size()
        win.draw_layout(gc, 2, win_height - y, self.tp_layout)

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

    def draw_glide(self, gc, win, win_height):
        """Draw final glide information"""
        glide = self.flight.task.get_glide()
        glide_height = glide['height'] * M_TO_FT

        gc.line_width = 3

        if (glide_height < FG_THRESHOLD) and not self.maccready_flag:
            return

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

        for _dummy in range(min(num_arrows, 5)):
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
        self.fg_layout.set_text(fmt % (glide_height, ete_str,
                                       glide['maccready'] * MPS_TO_KTS))
        x, y = self.fg_layout.get_pixel_size()
        win.draw_layout(gc, FG_WIDTH + 5, (win_height / 2) - (2 * y / 3),
                        self.fg_layout, background=None)

    def draw_heading(self, heading, cr, win_height, win_width):
        """Draw heading glider symbol"""
        x_cent = win_width / 2
        y_cent = win_height / 2

        width = self.glider_pixbuf.get_width()
        height = self.glider_pixbuf.get_height()

        cr.save()
        cr.translate(x_cent, y_cent)
        cr.rotate(heading)

        cr.set_source_pixbuf(self.glider_pixbuf, -width / 2, -height / 2)
        cr.paint()
        cr.restore()

    def draw_wind(self, cr, gc, win, win_width, win_height):
        """Draw wind speed/direction"""
        wind = self.flight.get_wind()

        # Draw wind direction
        width = self.wind_pixbuf.get_width()
        height = self.wind_pixbuf.get_height()

        xc = win_width - 40
        yc = 40

        cr.save()
        cr.translate(xc, yc)
        cr.rotate(wind['direction'])

        cr.set_source_pixbuf(self.wind_pixbuf, -width / 2, -height / 2)
        cr.paint()
        cr.restore()

        # Draw wind speed value
        speed = wind['speed'] * MPS_TO_KTS
        self.fg_layout.set_text(str(int(speed)))
        x, y = self.fg_layout.get_pixel_size()

        win.draw_layout(gc, xc - x - 40, yc - y / 2, self.fg_layout,
                        background=None)

        ground_speed = self.flight.get_velocity()['speed'] * MPS_TO_KTS
        self.fg_layout.set_text(str(int(ground_speed)))
        x, y = self.fg_layout.get_pixel_size()

        win.draw_layout(gc, win_width - x - 2, win_height - y,
                        self.fg_layout, background=None)

    def draw_satellites(self, gc, win, win_width, win_height):
        """Draw number of satellites in view"""
        self.fg_layout.set_text('%d' % self.flight.get_num_satellites())
        x, y = self.fg_layout.get_pixel_size()
        win.draw_layout(gc, win_width - x - 2, win_height - (2 * y),
                        self.fg_layout, background=None)

    def draw_mute(self, gc, win, win_width):
        """Draw mute indicator"""
        if self.mute_flag:
            pm_width, pm_height = self.mute_pixmap.get_size()
            win.draw_drawable(gc, self.mute_pixmap, 0, 0,
                              win_width / 2 - pm_width / 2,
                              pm_height / 2, -1, -1)

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
        result = dialog.run()
        dialog.destroy()

        return result

    def set_divert_indicator(self, flag):
        """Set indicator showing divert select is active"""
        self.divert_flag = flag
        self.redraw()

    def set_maccready_indicator(self, flag):
        """Set indicator showing Maccready is active"""
        self.maccready_flag = flag
        self.redraw()

    def set_mute_indicator(self, flag):
        """Set indicator showing mute is active"""
        self.mute_flag = flag
        self.redraw()

    def get_button_region(self, x, y):
        """Return "button" id of drawing area"""
        win_width, win_height = self.drawing_area.window.get_size()

        left = x < 75
        right = x > (win_width - 75)
        top = y < 100
        bottom = y > (win_height - 100)
        vertical_middle = abs(y - (win_height / 2)) < 50

        if left and top:
            region = 'divert'
        elif left and bottom:
            region = 'next'
        elif right and bottom:
            region = 'prev'
        elif right and top:
            region = 'user'
        elif left and vertical_middle:
            region = 'glide'
        else:
            region = 'background'

        return region
