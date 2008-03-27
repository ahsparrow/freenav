#!/usr/bin/env python

import freedb
import gtk
import gobject
from pysqlite2 import dbapi2 as sqlite
import projection

class TaskApp:
    def __init__(self):
        self.task_db = freedb.Freedb()
        self.lambert = projection.Lambert(*self.task_db.get_projection())

        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title('Task')
        self.window.set_border_width(3)
        self.window.connect('destroy', gtk.main_quit)
        self.window.connect('delete_event', self.quit)

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
        wp_view.append_column(col1)
        wp_view.append_column(col2)
        wp_window = gtk.ScrolledWindow()
        wp_window.add(wp_view)
        wp_view.connect('row-activated', self.wp_activated, wp_store)

        # Create task list
        self.task_saved = True
        self.task_store = gtk.ListStore(gobject.TYPE_STRING)
        for wp, x, y, alt in self.task_db.get_task():
            self.task_store.append((wp,))

        col = gtk.TreeViewColumn('ID')
        col.pack_start(cell, True)
        col.add_attribute(cell, 'text', 0)

        task_view = gtk.TreeView(self.task_store)
        self.task_view = task_view
        task_view.set_headers_visible(False)
        task_view.set_reorderable(True)
        task_view.append_column(col)
        task_view.connect('row-activated', self.wp_activated, self.task_store)

        self.dist_label = gtk.Label('')
        self.dist_label.set_alignment(1, 0)

        del_button = gtk.Button('Del')
        del_button.connect('clicked', self.delete_wp)
        save_button = gtk.Button('Save')
        save_button.connect('clicked', self.save_task)

        # Packing
        vbox = gtk.VBox()
        vbox.set_spacing(5)
        vbox.pack_start(task_view, expand=True)
        vbox.pack_start(self.dist_label, expand=False)
        vbox.pack_end(save_button, expand=False)
        vbox.pack_end(del_button, expand=False)

        hbox = gtk.HBox()
        hbox.set_spacing(3)
        hbox.pack_start(wp_window, expand=True)
        hbox.pack_end(vbox, expand=False)

        self.window.add(hbox)

        # Drag and drop
        wp_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
            [('text/plain', 0, 0)],
            gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)
        wp_view.connect('drag-data-get', self.drag_data_get)

        task_view.enable_model_drag_source(gtk.gdk.BUTTON1_MASK,
            [('MY_TREE_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0),
             ('text/plain', 0, 0)],
            gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_MOVE)
        task_view.enable_model_drag_dest(
            [('MY_TREE_MODEL_ROW', gtk.TARGET_SAME_WIDGET, 0),
             ('text/plain', 0, 0)],
            gtk.gdk.ACTION_DEFAULT)
        task_view.connect('drag-data-get', self.drag_data_get)
        task_view.connect('drag-data-received', self.drag_data_received)

        self.update_distance()
        self.window.show_all()

    def drag_data_get(self, view, context, selection, info, etime):
        wpsel = view.get_selection()
        model, iter = wpsel.get_selected()
        id = model.get_value(iter, 0)
        selection.set('text/plain', 8, id)

    def drag_data_received(self,
                           task_view, context, x, y, selection, info, etime):
        model = task_view.get_model()
        wp = selection.data
        drop_info = task_view.get_dest_row_at_pos(x, y)
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

        if context.action == gtk.gdk.ACTION_MOVE:
            context.finish(True, True, etime)

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

            n = model.iter_n_children(None)
            if n > 0:
                if n == path[0]:
                    selection.select_path(n-1)
                else:
                    selection.select_path(path)

        self.update_distance()
        self.task_saved = False

    def save_task(self, button):
        task = [wp[0] for wp in self.task_store]
        if task:
            self.task_db.set_task(task)
            self.task_saved = True
        else:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_OK,
               message_format='The task must contain at least one waypoint',
               type=gtk.MESSAGE_ERROR)
            dialog.run()
            dialog.destroy()

    def update_distance(self):
        task = [wp[0] for wp in self.task_store]
        dist = self.calc_distance(task)
        self.dist_label.set_text('%.1fkm' % (dist/1000))

    def calc_distance(self, task):
        if len(task) <= 1:
            return 0
        else:
            name, x1, y1 = self.task_db.get_waypoint(task[0])
            name, x2, y2 = self.task_db.get_waypoint(task[1])
            dist = self.lambert.dist(x1, y1, x2, y2) + \
                self.calc_distance(task[1:])
            return dist

    def quit(self, widget, event, data=None):
        if not self.task_saved:
            dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO,
                message_format='Task updated, are you sure you want to quit?',
                type=gtk.MESSAGE_QUESTION)
            ret = dialog.run()
            dialog.destroy()
            return (ret == gtk.RESPONSE_NO)

    def main(self):
        gtk.main()

def main():
    task_app = TaskApp()
    task_app.main()

if __name__ == '__main__':
    main()
