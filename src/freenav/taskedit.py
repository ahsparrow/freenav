"""Task editing program"""
import time

import gtk
import gobject

is_hildon_app = True
try:
    import hildon
    import osso
except ImportError:
    is_hildon_app = False

import freenav
import freenav.tasklist
import freenav.freenmea
import freenav.nmeaparser


OSSO_APPLICATION = "uk.org.freeflight.taskedit"

# List of task names
TASKS = 'ABCDEFGH'

TP_DIRNS = ['SYM', 'NEXT', 'PREV', 'FIX']
TP_TYPES = ['TURNPOINT', 'LINE', 'AREA']
START_TP_DIRNS = ['NEXT', 'FIX']
FINISH_TP_DIRNS = ['PREV', 'FIX']

class OzDialog(gtk.Dialog):
    """Observation zone parameter dialog box"""
    def __init__(self, parent, tp, tp_posn):
        """Class initialisation"""
        self.tp = tp

        title = 'Obs. Zone - ' + self.tp['waypoint_id']
        gtk.Dialog.__init__(self, title, parent,
                            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                            (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                             gtk.STOCK_OK, gtk.RESPONSE_OK))
        self.set_resizable(False)

        # Layout controls using table sizer
        table = gtk.Table(7, 2, True)
        table.set_col_spacing(0, 5)
        table.set_row_spacings(3)
        for n, txt in enumerate(["Outer Radius (m)", "Angle (deg)",
                                 "Inner Radius (m)", "Angle (deg)",
                                 "Dirn", "Bisect (deg)", "Type"]):
            label = gtk.Label(txt)
            label.set_alignment(1, 0.5)
            table.attach(label, 0, 1, n, n + 1)

        # Create spin buttons for ranges and angles
        rad1_adj = gtk.Adjustment(self.tp['radius1'], 0, 50000, 500)
        ang1_adj = gtk.Adjustment(self.tp['angle1'], 0, 360, 45)
        rad2_adj = gtk.Adjustment(self.tp['radius2'], 0, 50000, 500)
        ang2_adj = gtk.Adjustment(self.tp['angle2'], 0, 360, 45)
        ang12_adj = gtk.Adjustment(self.tp['angle12'], 0, 360, 1)

        self.rad1_spin = gtk.SpinButton(rad1_adj, 0, 0)
        self.ang1_spin = gtk.SpinButton(ang1_adj, 0, 1)
        self.rad2_spin = gtk.SpinButton(rad2_adj, 0, 0)
        self.ang2_spin = gtk.SpinButton(ang2_adj, 0, 1)
        self.ang12_spin = gtk.SpinButton(ang12_adj, 0.5, 1)

        for spin in [self.rad1_spin, self.ang1_spin, self.rad2_spin,
                     self.ang2_spin, self.ang12_spin]:
            spin.set_numeric(True)
        self.ang12_spin.set_wrap(True)

        table.attach(self.rad1_spin, 1, 2, 0, 1)
        table.attach(self.ang1_spin, 1, 2, 1, 2)
        table.attach(self.rad2_spin, 1, 2, 2, 3)
        table.attach(self.ang2_spin, 1, 2, 3, 4)
        table.attach(self.ang12_spin, 1, 2, 5, 6)

        # Create combo box for TP type
        self.tp_type_combobox = gtk.combo_box_new_text()
        for typ in TP_TYPES:
            self.tp_type_combobox.append_text(typ)
        self.tp_type_combobox.set_active(TP_TYPES.index(self.tp['tp_type']))
        table.attach(self.tp_type_combobox, 1, 2, 6, 7)
        self.tp_type_combobox.connect('changed', self.on_tp_type_select)

        self.on_tp_type_select(self.tp_type_combobox)

        # Create combobox for leg direction
        self.dirn_combobox = gtk.combo_box_new_text()
        if tp_posn == 'start':
            tp_dirns = START_TP_DIRNS
        elif tp_posn == 'finish':
            tp_dirns = FINISH_TP_DIRNS
        else:
            tp_dirns = TP_DIRNS
        for dirn in tp_dirns:
            self.dirn_combobox.append_text(dirn)
        self.dirn_combobox.set_active(tp_dirns.index(self.tp['direction']))
        table.attach(self.dirn_combobox, 1, 2, 4, 5)
        self.dirn_combobox.connect('changed', self.on_dirn_select)

        # (De-)active fixed leg angle adjustment
        self.on_dirn_select(self.dirn_combobox)

        self.vbox.pack_start(table)
        self.show_all()

    def on_dirn_select(self, combobox):
        """Set control sensitivity depending on direction"""
        dirn = combobox.get_active_text()

        # Set activate spin box if direction is FIX
        self.ang12_spin.set_sensitive(dirn == 'FIX')

    def on_tp_type_select(self, combobox):
        """Set control sensitivity depending on TP type"""
        tp_type = combobox.get_active_text()

        self.ang1_spin.set_sensitive(tp_type != 'LINE')
        self.ang2_spin.set_sensitive(tp_type != 'LINE')
        self.rad2_spin.set_sensitive(tp_type != 'LINE')

    def get_values(self):
        """Return values from the dialog box"""
        return {'radius1': self.rad1_spin.get_value_as_int(),
                'radius2': self.rad2_spin.get_value_as_int(),
                'angle1': self.ang1_spin.get_value(),
                'angle2': self.ang2_spin.get_value(),
                'angle12': self.ang12_spin.get_value(),
                'tp_type': self.tp_type_combobox.get_active_text(),
                'direction': self.dirn_combobox.get_active_text()}

if is_hildon_app:
    AppBase = hildon.Program
else:
    AppBase = object

SELECTION_FORMAT_STR = 8

class TaskApp(AppBase):
    """Main task application class"""
    def __init__(self, db, config):
        """Class initialisation"""
        AppBase.__init__(self)
        self.task_db = db

        self.window_in_fullscreen = False

        # Create window and add event handlers
        if is_hildon_app:
            self.osso_c = osso.Context(OSSO_APPLICATION, freenav.__version__,
                                       False)
            self.window = hildon.Window()
        else:
            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_name('freenav-taskedit')
        self.window.set_title('Task')
        self.window.set_border_width(3)
        self.window.connect('destroy', gtk.main_quit)
        self.window.connect('delete_event', self.on_delete)
        self.window.connect('key-press-event', self.on_keypress)
        self.window.connect('window-state-event', self.on_window_state_change)

        # Cell renderer for both waypoint and task lists
        cell = gtk.CellRendererText()

        # Create waypoint list
        wp_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        for wp in self.task_db.get_waypoint_list():
            wp_store.append((wp['id'], wp['name']))

        col1 = gtk.TreeViewColumn('ID')
        col1.pack_start(cell, True)
        col1.add_attribute(cell, 'text', 0)
        col1.set_sort_column_id(0)

        col2 = gtk.TreeViewColumn('Name')
        col2.pack_start(cell, True)
        col2.add_attribute(cell, 'text', 1)
        col2.set_sort_column_id(1)

        wp_view = gtk.TreeView(wp_store)
        wp_view.set_headers_visible(True)
        wp_view.append_column(col1)
        wp_view.append_column(col2)
        wp_view.connect('row-activated', self.on_wp_activated, wp_store)

        wp_window = gtk.ScrolledWindow()
        wp_window.add(wp_view)

        # Create task list with custom list store model
        self.task_saved = True
        self.task_store = freenav.tasklist.TaskListStore(self.task_db)
        self.task_store.load()
        self.task_store.connect('task_changed', self.on_task_change)

        col = gtk.TreeViewColumn('ID', cell)
        col.set_cell_data_func(cell, self.tp_cell)

        self.task_view = gtk.TreeView(self.task_store)
        self.task_view.set_headers_visible(False)
        self.task_view.set_reorderable(True)
        self.task_view.append_column(col)
        self.task_view.connect('row-activated', self.on_tp_activated,
                               self.task_store)

        # Task distance
        self.dist_label = gtk.Label('')
        self.dist_label.set_alignment(1, 0)
        self.update_distance()

        # Waypoint delete
        del_button = gtk.Button('Del')
        del_button.connect('clicked', self.on_tp_delete)

        # Observation zone set...
        oz_button = gtk.Button('OZ...')
        oz_button.connect('clicked', self.on_oz_set)

        # Task select
        combobox = gtk.combo_box_new_text()
        for t in TASKS:
            combobox.append_text(t)
        combobox.set_active(self.task_store.task_id)
        combobox.connect('changed', self.on_task_select)

        # Write declaration to flarmcfg.txt
        declare_button = gtk.Button('Declare')
        declare_button.connect('clicked', self.on_declare)

        # Task save
        save_button = gtk.Button('Save')
        save_button.connect('clicked', self.on_save)

        # Quit
        quit_button = gtk.Button('Quit')
        quit_button.connect('clicked', self.on_quit)

        # Packing
        vbox = gtk.VBox()
        vbox.set_spacing(5)
        vbox.pack_start(self.task_view, expand=True)
        vbox.pack_start(self.dist_label, expand=False)
        vbox.pack_start(del_button, expand=False)
        vbox.pack_start(oz_button, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_end(quit_button, expand=False)
        vbox.pack_end(save_button, expand=False)
        vbox.pack_end(declare_button, expand=False)
        vbox.pack_end(combobox, expand=False)

        hbox = gtk.HBox()
        hbox.set_spacing(3)
        hbox.pack_start(wp_window, expand=True)
        hbox.pack_end(vbox, expand=False)
        self.window.add(hbox)

        # Drag and drop
        wp_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
            [('WP_MODEL_ROW', gtk.TARGET_SAME_APP, 0)],
            gtk.gdk.ACTION_COPY)
        wp_view.connect('drag-data-get', self.on_wp_drag_data_get)

        self.task_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
            [('TASK_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0)],
            gtk.gdk.ACTION_COPY)
        self.task_view.enable_model_drag_dest(
            [('TASK_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0),
             ('WP_MODEL_ROW', gtk.TARGET_SAME_APP, 0)],
            gtk.gdk.ACTION_DEFAULT)
        self.task_view.connect('drag-data-get', self.on_task_drag_data_get)
        self.task_view.connect('drag-data-received',
                               self.on_drag_data_received)

        # Get GPS device
        dev_name = config.get('Device-Names', db.get_settings()['gps_device'])
        self.nmea_dev = config.get(dev_name, 'Device')
        if config.has_option(dev_name, 'Baud'):
            self.nmea_baud_rate = config.getint(dev_name, 'Baud')
        else:
            self.nmea_baud_rate = None

        # Create NMEA device (and connect signals)
        nmea_parser = freenav.nmeaparser.NmeaParser()
        self.nmea = freenav.freenmea.FreeNmea(nmea_parser)
        self.nmea.connect('flarm-declare', self.declare_callback)

    def tp_cell(self, _col, cell, model, model_iter):
        """Task list cell data function"""
        x = model.get_value(model_iter, 0)
        cell.set_property('text', x['waypoint_id'])

    def on_task_change(self, _widget):
        """Callback on task list model change"""
        self.update_distance()

    def on_delete(self, _widget, _event, _data=None):
        """Callback on application quit"""
        if not self.task_saved:
            resp = self.confirm_quit_dialog()
            return resp

    def confirm_quit_dialog(self):
        """Display quit confirmation dialog"""
        dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO,
            message_format='Task updated, are you sure you want to quit?',
            type=gtk.MESSAGE_QUESTION)
        ret = dialog.run()
        dialog.destroy()
        return (ret == gtk.RESPONSE_NO)

    def on_window_state_change(self, _widget, event, *_args):
        """Callback on window state change"""
        if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            self.window_in_fullscreen = True
        else:
            self.window_in_fullscreen = False

    def on_keypress(self, _widget, event, *_args):
        """Callback on keypress"""
        if event.keyval == gtk.keysyms.F6:
            if self.window_in_fullscreen:
                self.window.unfullscreen()
            else:
                self.window.fullscreen()

    def on_declare(self, _button):
        """Callback on declare button pressed"""
        self.dialog = gtk.MessageDialog(None,
                message_format="Sending declaration, wait...")
        self.dialog.show()

        # It's a complete mystery why this sleep is needed
        time.sleep(0.1)

        # Paint message dialog (won't work without previous sleep)
        while gtk.events_pending():
            gtk.main_iteration()

        self.timeout_id = gobject.timeout_add(10000, self.declare_timeout)

        wps = self.task_store.get_waypoints()
        self.nmea.open(self.nmea_dev, self.nmea_baud_rate)
        self.nmea.declare(wps)

    def declare_callback(self, _source, result):
        """Callback with declaration result"""
        self.nmea.close()
        self.dialog.destroy()

        gobject.source_remove(self.timeout_id)

    def declare_timeout(self):
        """Callback if declaration takes too long"""
        self.nmea.close()
        self.dialog.destroy()

        # Error message
        dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR,
            gtk.BUTTONS_OK, "Can't send declaration - timed out")
        dialog.run()
        dialog.destroy()

        return False

    def on_quit(self, _button):
        """Callback on quit button pressed"""
        if not self.task_saved:
            resp = self.confirm_quit_dialog()
        else:
            resp = False

        if not resp:
            self.window.destroy()

    def on_save(self, _button):
        """Callback on save button pressed"""
        self.task_store.save()
        self.task_store.commit()
        self.task_saved = True

    def on_wp_activated(self, _treeview, path, _column, model):
        """Callback on double click on waypoint"""
        wp_id = model[path][0]
        self.tp_dialog(wp_id)

    def on_tp_activated(self, _treeview, path, _column, model):
        """Callback on double click on turnpoint"""
        wp_id = model[path][0]['waypoint_id']
        self.tp_dialog(wp_id)

    def tp_dialog(self, wp_id):
        """Display waypoint info"""
        wp = self.task_db.get_waypoint(wp_id)
        msg = "%s\n%s\n\n%s\n\n%s" % (wp_id, wp['name'], wp['turnpoint'],
                                  wp['comment'])
        dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, 
                                   gtk.BUTTONS_CLOSE, msg)
        dialog.run()
        dialog.destroy()

    def on_tp_delete(self, _button):
        """Callback on turnpoint delete button press"""
        selection = self.task_view.get_selection()
        model, model_iter = selection.get_selected()
        if model_iter:
            path = model.get_path(model_iter)
            self.task_store.delete_tp(path[0])

            n = len(model)
            if n > 0:
                if n == path[0]:
                    selection.select_path(n-1)
                else:
                    selection.select_path(path)

        self.task_saved = False

    def on_oz_set(self, _button):
        """Pop up OZ setting dialog and get some new settings"""
        selection = self.task_view.get_selection()
        model, model_iter = selection.get_selected()
        if model_iter:
            tp_index = model.get_path(model_iter)[0]
            tp = model[tp_index][0]
            if tp_index == 0:
                tp_posn = 'start'
            elif tp_index == len(model) - 1:
                tp_posn = 'finish'
            else:
                tp_posn = 'tp'
            dialog = OzDialog(self.window, tp, tp_posn)
            response = dialog.run()

            if response == gtk.RESPONSE_OK:
                self.task_saved = False
                oz_values = dialog.get_values()
                model.set_tp(tp_index, oz_values)

            dialog.destroy()

    def on_task_select(self, combobox):
        """Task change callback"""
        task_id = combobox.get_active()
        self.task_store.save()
        self.task_store.load(task_id)
        self.task_saved = False

    def on_wp_drag_data_get(self, view, _context, selection, _info, _etime):
        """Drag starting from waypoint list"""
        sel = view.get_selection()
        model, model_iter = sel.get_selected()
        wp_id = model.get_value(model_iter, 0)
        selection.set('WP_DATA', SELECTION_FORMAT_STR, wp_id)

    def on_task_drag_data_get(self, view, _context, selection, _info, _etime):
        """Drag starting from turnpoint list"""
        sel = view.get_selection()
        _model, paths = sel.get_selected_rows()
        row = paths[0][0]
        selection.set('TASK_DATA', SELECTION_FORMAT_STR, str(row))

    def on_drag_data_received(self, view, _context, x, y, selection, _info,
                              _etime):
        """Drag finishing in turnpoint list"""
        model = view.get_model()
        drop_info = view.get_dest_row_at_pos(x, y)
        if drop_info:
            path, position = drop_info
            if (position == gtk.TREE_VIEW_DROP_BEFORE or
                position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                drop_posn = path[0]
            else:
                drop_posn = path[0] + 1
        else:
            drop_posn = len(model)

        if selection.type == 'WP_DATA':
            self.task_store.insert_tp(drop_posn, selection.data)
        else:
            from_posn = int(selection.data)
            self.task_store.move_tp(from_posn, drop_posn)

        self.task_saved = False

    def update_distance(self):
        """Refresh the task distance label"""
        dist = self.task_store.get_task_len()
        self.dist_label.set_text('%.1fkm' % (dist / 1000))

    def run(self):
        """Run the main loop"""
        self.window.show_all()
        gtk.main()
