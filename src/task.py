#!/usr/bin/env python

import gtk
import gobject
from pysqlite2 import dbapi2 as sqlite
is_hildon_app = True
try:
    import hildon
except ImportError:
    is_hildon_app = False

import freedb
import projection

TASKS = 'ABCDEFGH'
NUM_TASKS = len(TASKS)

if is_hildon_app:
    AppBase = hildon.Program
else:
    AppBase = object

class TaskApp(AppBase):
    def __init__(self):
        AppBase.__init__(self)

        self.task_db = freedb.Freedb()
        self.lambert = projection.Lambert(*self.task_db.get_projection())
        self.task_index, self.tasks = self.load_tasks()

        # Create window and add event handlers
        if is_hildon_app:
            self.window = hildon.Window()
        else:
            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title('Task')
        self.window.set_border_width(3)
        self.window.connect('destroy', gtk.main_quit)
        self.window.connect('delete_event', self.quit)
        self.window.connect('key-press-event', self.on_keypress)
        self.window.connect('window-state-event', self.on_window_state_change)

        # Create waypoint list
        wp_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        for wp in self.task_db.get_waypoint_list():
            wp_store.append((wp[0], wp[1]))

        cell = gtk.CellRendererText()
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
        wp_window = gtk.ScrolledWindow()
        wp_window.add(wp_view)
        wp_view.connect('row-activated', self.wp_activated, wp_store)

        # Create task list
        self.task_saved = True
        self.task_store = gtk.ListStore(gobject.TYPE_STRING)
        self.load_task_store(self.task_index)

        col = gtk.TreeViewColumn('ID')
        col.pack_start(cell, True)
        col.add_attribute(cell, 'text', 0)

        self.task_view = gtk.TreeView(self.task_store)
        self.task_view.set_headers_visible(False)
        self.task_view.set_reorderable(True)
        self.task_view.append_column(col)
        self.task_view.connect('row-activated', self.wp_activated,
                               self.task_store)

        # Task distance
        self.dist_label = gtk.Label('')
        self.dist_label.set_alignment(1, 0)

        # Waypoint delete
        del_button = gtk.Button('Del')
        del_button.connect('clicked', self.delete_wp)

        # Observation zone set...
        oz_button = gtk.Button('OZ...')
        oz_button.connect('clicked', self.set_oz)

        # Task select
        combobox = gtk.combo_box_new_text()
        for t in TASKS:
            combobox.append_text(t)
        combobox.set_active(self.task_index)
        combobox.connect('changed', self.change_task)

        # Task save
        save_button = gtk.Button('Save')
        save_button.connect('clicked', self.save_task)

        # Packing
        vbox = gtk.VBox()
        vbox.set_spacing(5)
        vbox.pack_start(self.task_view, expand=True)
        vbox.pack_start(self.dist_label, expand=False)
        vbox.pack_start(del_button, expand=False)
        vbox.pack_start(oz_button, expand=False)
        vbox.pack_start(gtk.HSeparator(), expand=False)
        vbox.pack_end(save_button, expand=False)
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
        wp_view.connect('drag-data-get', self.wp_drag_data_get)

        self.task_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
            [('TASK_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0)],
            gtk.gdk.ACTION_COPY)
        self.task_view.enable_model_drag_dest(
            [('TASK_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0),
             ('WP_MODEL_ROW', gtk.TARGET_SAME_APP, 0)],
            gtk.gdk.ACTION_DEFAULT)
        self.task_view.connect('drag-data-get', self.task_drag_data_get)
        self.task_view.connect('drag-data-received', self.drag_data_received)

        self.update_distance()

    def wp_drag_data_get(self, view, context, selection, info, etime):
        sel = view.get_selection()
        model, iter = sel.get_selected()
        id = model.get_value(iter, 0)
        selection.set('WP_DATA', 8, id)

    def task_drag_data_get(self, view, context, selection, info, etime):
        sel = view.get_selection()
        model, paths = sel.get_selected_rows()
        row = paths[0][0]
        selection.set('TASK_DATA', 8, str(row))

    def drag_data_received(self, view, context, x, y, selection, info, etime):
        model = view.get_model()
        wp = selection.data
        print "Received", wp, selection.type
        if selection.type == 'TASK_DATA':
            model.clear()
            return

        drop_info = view.get_dest_row_at_pos(x, y)
        if drop_info:
            path, position = drop_info
            iter = model.get_iter(path)
            if (position == gtk.TREE_VIEW_DROP_BEFORE or
                position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                model.insert_before(iter, [wp])
            else:
                model.insert_after(iter, [wp])
        else:
             model.append([wp])

        self.update_distance()
        self.task_saved = False

    def wp_activated(self, treeview, path, column, model):
        id = model[path][0]
        (name, turnpoint, comment) = self.task_db.get_waypoint_info(id)
        msg = "%s\n%s\n%s\n%s" % (id, name, turnpoint, comment)
        md = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, 
                               gtk.BUTTONS_CLOSE, msg)
        md.run()
        md.destroy()

    def delete_wp(self, button):
        selection = self.task_view.get_selection()
        model, iter = selection.get_selected()
        if iter:
            path = model.get_path(iter)
            model.remove(iter)

            n = len(model)
            if n > 0:
                if n == path[0]:
                    selection.select_path(n-1)
                else:
                    selection.select_path(path)

        self.update_distance()
        self.task_saved = False

    def set_oz(self, button):
        selection = self.task_view.get_selection()
        model, iter = selection.get_selected()
        if iter:
            n = model.get_path(iter)[0]
            if n > 0 and n < (len(model) - 1):
                print n

    def load_tasks(self):
        tasks = {}
        for i in range(NUM_TASKS):
            tasks[i] = self.task_db.get_task(i)

        task_index = self.task_db.get_task_index()
        return (task_index, tasks)

    def save_task(self, button):
        self.save_task_store(self.task_index)
        for i in range(NUM_TASKS):
            self.task_db.set_task(self.tasks[i], i)
        self.task_db.set_task_index(self.task_index)
        self.task_saved = True

    def change_task(self, combobox):
        self.save_task_store(self.task_index)
        self.task_index = combobox.get_active()
        self.load_task_store(self.task_index)
        self.task_saved = False
        self.update_distance()

    def load_task_store(self, task_index):
        self.task_store.clear()
        for wp in self.tasks[task_index]:
            self.task_store.append((wp,))

    def save_task_store(self, task_index):
        task = [wp[0] for wp in self.task_store]
        self.tasks[task_index] = task

    def update_distance(self):
        task = [wp[0] for wp in self.task_store]
        dist = self.calc_distance(task)
        self.dist_label.set_text('%.1fkm' % (dist/1000))

    def calc_distance(self, task):
        if len(task) <= 1:
            return 0
        else:
            x1, y1, alt = self.task_db.get_waypoint(task[0])
            x2, y2, alt = self.task_db.get_waypoint(task[1])
            dist = self.lambert.dist(x1, y1, x2, y2) + \
                self.calc_distance(task[1:])
            return dist

    def on_window_state_change(self, widget, event, *args):
        if event.new_window_state & gtk.gdk.WINDOW_STATE_FULLSCREEN:
            self.window_in_fullscreen = True
        else:
            self.window_in_fullscreen = False

    def on_keypress(self, widget, event, *args):
        if event.keyval == gtk.keysyms.F6:
            if self.window_in_fullscreen:
                self.window.unfullscreen()
            else:
                self.window.fullscreen()

    def quit(self, widget, event, data=None):
        if not self.task_saved:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO,
                message_format='Task updated, are you sure you want to quit?',
                type=gtk.MESSAGE_QUESTION)
            ret = dialog.run()
            dialog.destroy()
            return (ret == gtk.RESPONSE_NO)

    def run(self):
        self.window.show_all()
        gtk.main()

if __name__ == '__main__':
    task_app = TaskApp()
    task_app.run()