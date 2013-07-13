#!/usr/bin/python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2012, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE


# We import here only the things necessary to start and show an image. The rest are imported lazily so they do not slow startup
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import cairo
import os
import sys
import time

killed = False

def kill(*args):
    global killed
    killed = True

class Easylog:
    def __init__(self, level):
        self.level = level

    def log(self, x):
        print x

    def info(self, x):
        if self.level >= 0:
            print x

    def debug(self, x):
        if self.level >= 1:
            print x

    def warning(self, x):
        print x

    def exception(self, x):
        import logging
        logging.exception(x)

logging = Easylog(1 if "-v" in sys.argv or "--verbose" in sys.argv else 0)

class Ojo(Gtk.Window):
    def __init__(self):
        super(Ojo, self).__init__()

        path = os.path.realpath(sys.argv[-1]) if len(sys.argv) > 1 and os.path.exists(sys.argv[-1]) \
            else os.path.expanduser('~/Pictures') # TODO get XDG dir
        logging.info("Started with: " + path)

        self.set_position(Gtk.WindowPosition.CENTER)

        self.visual = self.get_screen().get_rgba_visual()
        if self.visual and self.get_screen().is_composited():
            self.set_visual(self.visual)
        self.set_app_paintable(True)
        self.connect("draw", self.area_draw)

        self.scroll_window = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.image.set_visible(True)
        self.scroll_window.add_with_viewport(self.image)
        self.make_transparent(self.scroll_window)
        self.make_transparent(self.scroll_window.get_child())
        self.scroll_window.set_visible(True)

        self.box = Gtk.VBox()
        self.box.set_visible(True)
        self.box.add(self.scroll_window)
        self.add(self.box)

        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK)

        self.mousedown_zoomed = False
        self.mousedown_panning = False

        self.set_decorated('-d' in sys.argv or '--decorated' in sys.argv)
        if '-m' in sys.argv or '--maximize' in sys.argv:
            self.maximize()
        self.full = '-f' in sys.argv or '--fullscreen' in sys.argv
        self.fit_only_large = '--fit-only-large' in sys.argv

        self.meta_cache = {}
        self.pix_cache = {False: {}, True: {}} # keyed by "zoomed" property
        self.current_preparing = None
        self.manually_resized = False

        self.set_zoom(False, 0.5, 0.5)
        self.toggle_fullscreen(self.full, first_run=True)

        if os.path.isfile(path):
            self.mode = 'image'
            self.last_automatic_resize = time.time()
            self.show(path, quick=True)
            GObject.idle_add(self.after_quick_start)
        else:
            if not path.endswith('/'):
                path += '/'
            self.mode = 'folder'
            self.selected = path
            self.shown = None
            self.after_quick_start()
            self.set_mode('folder')
            self.selected = self.images[0] if self.images else path
            self.last_automatic_resize = time.time()
            self.resize(*self.get_recommended_size())

        self.set_visible(True)

        GObject.threads_init()
        Gdk.threads_init()
        Gdk.threads_enter()
        Gtk.main()
        Gdk.threads_leave()

    def area_draw(self, widget, cr):
        if self.full:
            if self.mode == 'folder':
                cr.set_source_rgba(77.0/255, 75.0/255, 69.0/255, 1)
            else:
                cr.set_source_rgba(0, 0, 0, 1.0)
        else:
            cr.set_source_rgba(77.0/255, 75.0/255, 69.0/255, 0.9)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

    def js(self, command):
        logging.debug('js(%s)' % command)
        if hasattr(self, "web_view_loaded"):
            GObject.idle_add(lambda: self.web_view.execute_script(command))
        else:
            GObject.timeout_add(100, lambda: self.js(command))

    def select_in_browser(self, file):
        self.js("select('%s')" % file)

    def update_zoom_scrolling(self):
        if self.zoom:
            if not self.zoom_x_percent is None:
                ha = self.scroll_window.get_hadjustment()
                ha.set_value(self.zoom_x_percent * (ha.get_upper() - ha.get_page_size() - ha.get_lower()))
                self.zoom_x_percent = None
            if not self.zoom_y_percent is None:
                va = self.scroll_window.get_vadjustment()
                va.set_value(self.zoom_y_percent * (va.get_upper() - va.get_page_size() - va.get_lower()))
                self.zoom_y_percent = None
            self.scroll_h = self.scroll_window.get_hadjustment().get_value()
            self.scroll_v = self.scroll_window.get_vadjustment().get_value()

    def show(self, filename=None, quick=False):
        filename = filename or self.selected
        logging.info("Showing " + filename)

        if os.path.isdir(filename):
            self.change_to_folder(filename)
            return

        self.shown = filename
        self.selected = self.shown
        self.set_title(self.shown)

        self.pixbuf = self.get_pixbuf(self.shown)
        self.increase_size()

        if os.path.splitext(filename)[1].lower() in ('.gif', '.mng', '.png'):
            anim = GdkPixbuf.PixbufAnimation.new_from_file(filename)
            if anim.is_static_image():
                self.image.set_from_pixbuf(self.pixbuf)
            else:
                self.image.set_from_animation(anim)
        else:
            self.image.set_from_pixbuf(self.pixbuf)

        if not quick:
            self.update_cursor()
            self.last_action_time = time.time()
            self.select_in_browser(self.shown)
            self.cache_around()
        else:
            self.last_action_time = 0

    def get_supported_image_extensions(self):
        if not hasattr(self, "image_formats"):
            # supported by PIL, as per http://infohost.nmt.edu/tcc/help/pubs/pil/formats.html:
            self.image_formats = {"bmp", "dib", "dcx", "eps", "ps", "gif", "im", "jpg", "jpe", "jpeg", "pcd",
                                  "pcx", "png", "pbm", "pgm", "ppm", "psd", "tif", "tiff", "xbm", "xpm"}

            # RAW formats, as per https://en.wikipedia.org/wiki/Raw_image_format#Annotated_list_of_file_extensions, we rely on pyexiv2 previews for these:
            self.image_formats = self.image_formats.union(
                    {"3fr", "ari", "arw", "srf", "sr2", "bay", "crw", "cr2", "cap", "iiq",
                     "eip", "dcs", "dcr", "drf", "k25", "kdc", "dng", "erf", "fff", "mef", "mos", "mrw",
                     "nef", "nrw", "orf", "pef", "ptx", "pxn", "r3d", "raf", "raw", "rw2", "raw", "rwl",
                     "dng", "rwz", "srw", "x3f"})

            # supported by GdkPixbuf:
            for l in [f.get_extensions() for f in GdkPixbuf.Pixbuf.get_formats()]:
                self.image_formats = self.image_formats.union(map(lambda e: e.lower(), l))

        return self.image_formats

    def is_image(self, filename):
        """Decide if something might be a supported image based on extension"""
        try:
            return os.path.isfile(filename) and os.path.splitext(filename)[1].lower()[1:] in self.get_supported_image_extensions()
        except Exception:
            return False

    def get_image_list(self):
        return filter(self.is_image, map(lambda f: os.path.join(self.folder, f), sorted(os.listdir(self.folder))))

    def set_folder(self, path):
        path = os.path.realpath(path)
        logging.info("Setting folder %s" % path)
        if hasattr(self, "folder") and not path in self.folder_history:
            self.folder_history = self.folder_history[self.folder_history.index(self.folder):]
        self.folder = path
        if not path in self.folder_history:
            self.folder_history.insert(0, self.folder)
        self.images = self.get_image_list()

    def get_back_folder(self):
        i = self.folder_history.index(self.folder)
        if i < len(self.folder_history) - 1:
            return self.folder_history[i + 1]

    def folder_history_back(self):
        if self.get_back_folder():
            self.change_to_folder(self.get_back_folder())

    def get_forward_folder(self):
        i = self.folder_history.index(self.folder)
        if i > 0:
            return self.folder_history[i - 1]

    def folder_history_forward(self):
        if self.get_forward_folder():
            self.change_to_folder(self.get_forward_folder())

    def change_to_folder(self, path):
        with self.thumbs_queue_lock:
            self.thumbs_queue = []
            self.prepared_thumbs = set()
        self.set_folder(path)
        self.selected = self.images[0] if self.images else os.path.realpath(os.path.join(path, '..'))
        self.set_mode("folder")
        self.render_folder_view()

    def check_kill(self):
        global killed
        if killed:
            logging.info('Killed, quitting...')
            GObject.idle_add(Gtk.main_quit)
        else:
            GObject.timeout_add(500, self.check_kill)

    def resized(self, widget, event):
        last_width = getattr(self, "last_width", 0)
        last_height = getattr(self, "last_height", 0)
        last_x = getattr(self, "last_x", 0)
        last_y = getattr(self, "last_y", 0)

        if time.time() - self.last_automatic_resize > 0.5 and \
           (event.width, event.height, event.x, event.y) != (last_width, last_height, last_x, last_y):
            logging.info("Manually resized, stop automatic resizing")
            self.manually_resized = True
            GObject.idle_add(self.show)

        self.last_width = event.width
        self.last_height = event.height
        self.last_x = event.x
        self.last_y = event.y

    def after_quick_start(self):
        import signal
        signal.signal(signal.SIGINT, kill)
        signal.signal(signal.SIGTERM, kill)
        signal.signal(signal.SIGQUIT, kill)

        self.check_kill()
        self.folder_history = []
        self.set_folder(os.path.dirname(self.selected))

        self.update_cursor()
        self.from_browser_time = 0

        self.browser = Gtk.ScrolledWindow()
        self.browser.set_visible(False)
        self.make_transparent(self.browser)
        self.box.add(self.browser)

        self.connect("delete-event", Gtk.main_quit)
        self.connect("key-press-event", self.process_key)
        if "--quit-on-focus-out" in sys.argv:
            self.connect("focus-out-event", Gtk.main_quit)
        self.connect("button-press-event", self.mousedown)
        self.last_mouseup_time = 0
        self.connect("button-release-event", self.mouseup)
        self.connect("scroll-event", self.scrolled)
        self.connect('motion-notify-event', self.mouse_motion)

        self.connect('configure-event', self.resized)

        GObject.idle_add(self.render_browser)

        self.start_cache_thread()
        if self.mode == "image":
            self.cache_around()
        self.start_thumbnail_thread()

    def make_transparent(self, widget):
        rgba = Gdk.RGBA()
        rgba.parse('rgba(0, 0, 0, 0)')
        widget.override_background_color(Gtk.StateFlags.NORMAL, rgba)

    def on_js_action(self, action, argument):
        import json

        if action in ('ojo', 'ojo-select'):
            self.selected = argument
            if action == 'ojo':
                def _do():
                    filename = self.selected
                    if os.path.isfile(filename):
                        self.show(filename)
                        self.from_browser_time = time.time()
                        self.set_mode("image")
                    else:
                        self.change_to_folder(filename)

                GObject.idle_add(_do)
        elif action == 'ojo-priority':
            files = json.loads(argument)
            self.priority_thumbs(map(lambda f: f.encode('utf-8'), files))
        elif action == 'ojo-handle-key':
            self.process_key(key=argument, skip_browser=True)

    def render_browser(self):
        from gi.repository import WebKit

        with open(os.path.join(os.path.dirname(os.path.normpath(__file__)), 'browse.html')) as f:
            html = f.read()

        self.web_view = WebKit.WebView()
        self.web_view.set_transparent(True)
        self.web_view.set_can_focus(True)

        def nav(wv, wf, title):
            title = title[title.index('|') + 1:]
            index = title.index(':')
            action = title[:index]
            argument = title[index + 1:]
            self.on_js_action(action, argument)
        self.web_view.connect("title-changed", nav)

        self.web_view.connect('document-load-finished', lambda wf, data: self.render_folder_view()) # Load page

        self.web_view.load_string(html, "text/html", "UTF-8", "file://" + os.path.dirname(__file__) + "/")
        self.make_transparent(self.web_view)
        self.web_view.set_visible(True)
        self.browser.add(self.web_view)
        self.web_view.grab_focus()

    def add_folder(self, category, path):
        import util
        self.js("add_folder('%s', '%s', '%s', '%s')" % (
            category,
            os.path.basename(path) or path,
            path,
            util.get_folder_icon(path, 24)))

    def render_folder_view(self):
        self.web_view_loaded = True
        folder = self.folder
        self.js("change_folder('%s')" % self.folder)

        import threading
        def _thread():
            self.js("set_title('%s')" % self.folder)
            if self.folder != '/':
                parent_path = os.path.realpath(os.path.join(self.folder, '..'))
                self.js("add_folder_category('Up', 'up')")
                self.add_folder('up', parent_path)

                siblings = [os.path.join(parent_path, f) for f in sorted(os.listdir(parent_path))
                            if os.path.isdir(os.path.join(parent_path, f))]
                pos = siblings.index(self.folder)
                if pos - 1 >= 0:
                    self.js("add_folder_category('Previous', 'prev_sibling')")
                    self.add_folder('prev_sibling', siblings[pos - 1])
                if pos + 1 < len(siblings):
                    self.js("add_folder_category('Next', 'next_sibling')")
                    self.add_folder('next_sibling', siblings[pos + 1])

            subfolders = [os.path.join(self.folder, f) for f in sorted(os.listdir(self.folder))
                          if os.path.isdir(os.path.join(self.folder, f))]
            if subfolders:
                self.js("add_folder_category('Subfolders', 'sub')")
                for sub in subfolders:
                    if folder != self.folder:
                        return
                    self.add_folder('sub', sub)

            self.select_in_browser(self.selected)

            pos = self.images.index(self.selected) if self.selected in self.images else 0
            self.priority_thumbs([x[1] for x in sorted(enumerate(self.images), key=lambda (i,f): abs(i - pos))])

            for img in self.images:
                if folder != self.folder:
                    return
                self.js("add_image_div('%s', %s, %d)" % (img, 'true' if img==self.selected else 'false', 180))
                cached = self.get_cached_thumbnail_path(img)
                if os.path.exists(cached):
                    self.add_thumb(img, use_cached=cached)
                else:
                    try:
                        meta = self.get_meta(img)
                        w, h = meta.dimensions
                        thumb_width = int(h * 120 / w) if self.needs_rotation(meta) else int(w * 120 / h)
                        if w and h:
                            self.js("set_dimensions('%s', '%d x %d', %d)" % (img, w, h, thumb_width))
                    except Exception:
                        pass

            self.select_in_browser(self.selected)

        prepare_thread = threading.Thread(target=_thread)
        prepare_thread.daemon = True
        prepare_thread.start()

    def cache_around(self):
        if not hasattr(self, "images") or not self.images:
            return
        pos = self.images.index(self.selected) if self.selected in self.images else 0
        for i in [1, -1]:
            if pos + i < 0 or pos + i >= len(self.images):
                continue
            f = self.images[pos + i]
            if not f in self.pix_cache[self.zoom]:
                logging.info("Caching around: file %s, zoomed %s" % (f, self.zoom))
                self.cache_queue.put((f, self.zoom))

    def start_cache_thread(self):
        import threading
        import Queue
        self.cache_queue = Queue.Queue()
        self.preparing_event = threading.Event()

        def _queue_thread():
            logging.info("Starting cache thread")
            while True:
                if len(self.pix_cache[False]) > 20:   #TODO: Do we want a proper LRU policy, or this is good enough?
                    self.pix_cache[False] = {}
                if len(self.pix_cache[True]) > 20:
                    self.pix_cache[True] = {}

                file, zoom = self.cache_queue.get()

                try:
                    if not file in self.pix_cache[zoom]:
                        logging.debug("Cache thread loads file %s, zoomed %s" % (file, zoom))
                        self.current_preparing = file, zoom
                        try:
                            self.get_meta(file)
                            self.get_pixbuf(file, force=True, zoom=zoom)
                        except Exception:
                            logging.exception("Could not cache file " + file)
                        finally:
                            self.current_preparing = None
                            self.preparing_event.set()
                except Exception:
                    logging.exception("Exception in cache thread:")
        cache_thread = threading.Thread(target=_queue_thread)
        cache_thread.daemon = True
        cache_thread.start()

    def get_thumbs_cache_dir(self, height):
        return os.path.expanduser('~/.config/ojo/cache/%d' % height)

    def start_thumbnail_thread(self):
        import threading
        self.prepared_thumbs = set()
        self.thumbs_queue = []
        self.thumbs_queue_event = threading.Event()
        self.thumbs_queue_lock = threading.Lock()

        def _thumbs_thread():
            # delay the start to give the caching thread some time to prepare next images
            start_time = time.time()
            while self.mode == "image" and time.time() - start_time < 2:
                time.sleep(0.1)

            try:
                cache_dir = self.get_thumbs_cache_dir(120)
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)
            except Exception:
                logging.exception("Could not create cache dir %s" % cache_dir)

            logging.info("Starting thumbs thread")
            while True:
                self.thumbs_queue_event.wait()
                while self.thumbs_queue:
                    # pause thumbnailing while the user is actively cycling images:
                    while time.time() - self.last_action_time < 2:
                        time.sleep(0.2)
                    time.sleep(0.03)
                    try:
                        with self.thumbs_queue_lock:
                            if not self.thumbs_queue:
                                continue
                            img = self.thumbs_queue[0]
                            self.thumbs_queue.remove(img)
                        if not img in self.prepared_thumbs:
                            logging.debug("Thumbs thread loads file " + img)
                            self.add_thumb(img)
                    except Exception:
                        logging.exception("Exception in thumbs thread:")
                self.thumbs_queue_event.clear()
        thumbs_thread = threading.Thread(target=_thumbs_thread)
        thumbs_thread.daemon = True
        thumbs_thread.start()

    def add_thumb(self, img, use_cached=None):
        try:
            thumb_path = use_cached or self.prepare_thumbnail(img, 360, 120)
            self.js("add_image('%s', '%s')" % (img, thumb_path))
            if img == self.selected:
                self.select_in_browser(img)
            self.prepared_thumbs.add(img)
        except Exception, e:
            self.js("remove_image_div('%s')" % img)
            logging.warning("Could not add thumb for " + img)

    def priority_thumbs(self, files):
        logging.debug("Priority thumbs: " + str(files))
        new_thumbs_queue = [self.selected] + [f for f in files if not f in self.prepared_thumbs] + \
                           [f for f in self.thumbs_queue if not f in files and not f in self.prepared_thumbs]
        new_thumbs_queue = filter(self.is_image, new_thumbs_queue)
        with self.thumbs_queue_lock:
            self.thumbs_queue = new_thumbs_queue
            self.thumbs_queue_event.set()

    def get_meta(self, filename):
        try:
            from pyexiv2 import ImageMetadata
            meta = ImageMetadata(filename)
            meta.read()
            self.meta_cache[filename] = self.needs_orientation(meta), meta.dimensions[0], meta.dimensions[1]
            self.js("set_dimensions('%s', '%d x %d')" % (filename, meta.dimensions[0], meta.dimensions[1]))
            return meta
        except Exception:
            logging.exception("Could not parse meta-info for %s" % filename)
            return None

    def set_margins(self, margin):
        if margin == getattr(self, "margin", -1):
            return

        self.margin = margin
        def _f():
            self.box.set_margin_right(margin)
            self.box.set_margin_left(margin)
            self.box.set_margin_bottom(margin)
            self.box.set_margin_top(margin)
        GObject.idle_add(_f)

    def get_recommended_size(self):
        screen = self.get_screen()
        width = screen.get_width() - 150
        height = screen.get_height() - 150
        if width > 1.5 * height:
            width = int(1.5 * height)
        else:
            height = int(width / 1.5)
        return min(width, screen.get_width() - 150), min(height, screen.get_height() - 150)

    def get_max_image_width(self):
        if self.full:
            return self.get_screen().get_width()
        elif self.manually_resized:
            return self.get_window().get_width() - 2*self.margin
        else:
            return self.get_recommended_size()[0] - 2*self.margin

    def get_max_image_height(self):
        if self.full:
            return self.get_screen().get_height()
        elif self.manually_resized:
            return self.get_window().get_height() - 2*self.margin
        else:
            return self.get_recommended_size()[1] - 2*self.margin

    def increase_size(self):
        if self.manually_resized or self.zoom or self.full:
            return

        new_width = max(self.pixbuf.get_width() + 2 * self.margin, self.get_width())
        new_height = max(self.pixbuf.get_height() + 2 * self.margin, self.get_height())
        if new_width > self.get_width() or new_height > self.get_height():
            self.last_automatic_resize = time.time()
            self.resize(new_width, new_height)
            self.move((self.get_screen().get_width() - new_width) // 2, (self.get_screen().get_height() - new_height) // 2)

    def go(self, direction, start_position=None):
        filename = None
        try:
            position = start_position - direction if not start_position is None else self.images.index(self.selected)
            position = (position + direction + len(self.images)) % len(self.images)
            filename = self.images[position]
            self.show(filename)
            return
        except Exception:
            logging.exception("go: Could not show %s" % filename)
            GObject.idle_add(lambda: self.go(direction))

    def toggle_fullscreen(self, full=None, first_run=False):
        if full is None:
            full = not self.full
        self.full = full

        self.pix_cache[False] = {}

        self.update_margins()
        if self.full:
            self.fullscreen()
        elif not first_run:
            self.unfullscreen()
        self.last_automatic_resize = time.time()

        if not first_run and not self.full:
            self.update_cursor()
            GObject.idle_add(self.show)

    def update_margins(self):
        if self.full:
            self.set_margins(0)
        else:
            self.set_margins(30)

    def update_cursor(self):
        if self.mousedown_zoomed:
            self.set_cursor(Gdk.CursorType.HAND1)
        elif self.mousedown_panning:
            self.set_cursor(Gdk.CursorType.HAND1)
        elif self.full and self.mode == 'image':
            self.set_cursor(Gdk.CursorType.BLANK_CURSOR)
        else:
            self.set_cursor(Gdk.CursorType.ARROW)

    def set_cursor(self, cursor):
        if self.get_window() and (
            not self.get_window().get_cursor() or cursor != self.get_window().get_cursor().get_cursor_type()):
            self.get_window().set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(), cursor))

    def set_mode(self, mode):
        self.mode = mode
        if self.mode == "image" and self.selected != self.shown:
            self.show(self.selected)
        elif self.mode == "folder":
            self.set_title(self.folder)
            self.last_action_time = 0

        self.update_cursor()
        self.scroll_window.set_visible(self.mode == 'image')
        self.image.set_visible(self.mode == 'image')
        self.browser.set_visible(self.mode == 'folder')
        self.update_margins()

    def process_key(self, widget=None, event=None, key=None, skip_browser=False):
        key = key or Gdk.keyval_name(event.keyval)
        if key == 'Escape' and (self.mode == 'image' or skip_browser):
            Gtk.main_quit()
        elif key in ("F11",) or (self.mode == 'image' and key in ('f', 'F')):
            self.toggle_fullscreen()
            self.show()
        elif key == 'Return':
            modes = ["image", "folder"]
            self.set_mode(modes[(modes.index(self.mode) + 1) % len(modes)])
        elif self.mode == 'folder':
            if hasattr(self, 'web_view'):
                self.web_view.grab_focus()
            if key == 'Left' and event and (event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)):
                self.folder_history_back()
            elif key == 'Right' and event and (event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)):
                self.folder_history_forward()
            elif not skip_browser:
                self.js("on_key('%s')" % key)
            else:
                if key == 'BackSpace':
                    self.change_to_folder(os.path.join(self.folder, '..'))
        elif key == 'F5':
            self.show()
        elif key in ("Right", "Down", "Page_Down", "space"):
            GObject.idle_add(lambda: self.go(1))
        elif key in ("Left", "Up", "Page_Up", "BackSpace"):
            GObject.idle_add(lambda: self.go(-1))
        elif key == "Home":
            GObject.idle_add(lambda: self.go(1, 0))
        elif key == "End":
            GObject.idle_add(lambda: self.go(-1, len(self.images) - 1))
        elif key in ("z", "Z"):
            self.set_zoom(not self.zoom)
            self.show()
            self.update_zoomed_views()
        elif key in ("1", "0"):
            self.set_zoom(True)
            self.show()
            self.update_zoomed_views()
        elif key in ("slash", "asterisk"):
            self.set_zoom(False)
            self.show()
            self.update_zoomed_views()

    def set_zoom(self, zoom, x_percent=None, y_percent=None):
        self.zoom = zoom
        if x_percent is None:
            x_percent = self.zoom_x_percent
        if y_percent is None:
            y_percent = self.zoom_y_percent
        self.zoom_x_percent = x_percent
        self.zoom_y_percent = y_percent

    def update_zoomed_views(self):
        rect = Gdk.Rectangle()
        rect.width = self.get_max_image_width()
        rect.height = self.get_max_image_height()
        self.scroll_window.size_allocate(rect)
        self.update_zoom_scrolling()

    def get_width(self):
        return self.get_window().get_width() if self.get_window() else 1

    def get_height(self):
        return self.get_window().get_height() if self.get_window() else 1

    def mouse_motion(self, widget, event):
        if not self.mousedown_zoomed and not self.mousedown_panning:
            self.set_cursor(Gdk.CursorType.ARROW)
            return

        self.register_action()
        if self.mousedown_zoomed:
            self.set_zoom(True,
                min(1, max(0, event.x - 100) / max(1, self.get_width() - 200)),
                min(1, max(0, event.y - 100) / max(1, self.get_height() - 200)))
            self.update_zoom_scrolling()
        elif self.mousedown_panning:
            ha = self.scroll_window.get_hadjustment()
            ha.set_value(self.scroll_h - (event.x - self.mousedown_x))
            va = self.scroll_window.get_vadjustment()
            va.set_value(self.scroll_v - (event.y - self.mousedown_y))

    def mousedown(self, widget, event):
        if self.mode != "image" or event.button != 1:
            return

        self.mousedown_x = event.x
        self.mousedown_y = event.y

        if self.zoom:
            self.mousedown_panning = True
            self.update_cursor()
            self.register_action()
        else:
            mousedown_time = time.time()
            x = event.x
            y = event.y
            def act():
                if mousedown_time > self.last_mouseup_time:
                    self.mousedown_zoomed = True
                    self.register_action()
                    self.set_zoom(True,
                        min(1, max(0, x - 100) / max(1, self.get_width() - 200)),
                        min(1, max(0, y - 100) / max(1, self.get_height() - 200)))
                    self.show()
                    self.update_zoomed_views()
                    self.update_cursor()
            GObject.timeout_add(250, act)

    def register_action(self):
        self.last_action_time = time.time()

    def mouseup(self, widget, event):
        self.last_mouseup_time = time.time()
        if self.mode != "image" or event.button != 1:
            return
        if self.last_mouseup_time - self.from_browser_time < 0.2:
            return
        if self.mousedown_zoomed:
            self.set_zoom(False)
            self.show()
            self.update_zoomed_views()
        elif self.mousedown_panning and (event.x != self.mousedown_x or event.y != self.mousedown_y):
            self.scroll_h = self.scroll_window.get_hadjustment().get_value()
            self.scroll_v = self.scroll_window.get_vadjustment().get_value()
        else:
            self.go(-1 if event.x < 0.5 * self.get_width() else 1)
        self.mousedown_zoomed = False
        self.mousedown_panning = False
        self.update_cursor()

    def scrolled(self, widget, event):
        if self.mode != "image" or self.zoom:
            return
        if event.direction not in (
            Gdk.ScrollDirection.UP, Gdk.ScrollDirection.LEFT, Gdk.ScrollDirection.DOWN, Gdk.ScrollDirection.RIGHT):
            return

        if getattr(self, "wheel_timer", None):
            GObject.source_remove(self.wheel_timer)

        direction = -1 if event.direction in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.LEFT) else 1
        self.wheel_timer = GObject.timeout_add(100, lambda: self.go(direction))

    def pixbuf_from_data(self, data, width, height):
        from gi.repository import Gio
        input_str = Gio.MemoryInputStream.new_from_data(data, None)
        if not self.zoom:
            return GdkPixbuf.Pixbuf.new_from_stream_at_scale(input_str, width, height, True, None)
        else:
            return GdkPixbuf.Pixbuf.new_from_stream(input_str, None)

    def pixbuf_to_b64(self, pixbuf):
        return pixbuf.save_to_bufferv('png', [], [])[1].encode("base64").replace('\n', '')

    def get_cached_thumbnail_path(self, filename):
        # Use "smaller" types of images directly - webkit will handle transparency, animated gifs, etc.
        if os.path.splitext(filename)[1].lower() in (('.gif', '.svg')):
            return filename

        import hashlib
        import re
        # we append modification time to ensure we're not using outdated cached images
        mtime = os.path.getmtime(filename)
        hash = hashlib.md5(filename + str(mtime)).hexdigest()
        return os.path.join(self.get_thumbs_cache_dir(120), re.sub('[\W_]+', '_', filename) + '_' + hash + ".jpg")

    def prepare_thumbnail(self, filename, width, height):
        cached = self.get_cached_thumbnail_path(filename)
        if not os.path.exists(cached):
            try:
                pil = self.get_pil(filename, width, height)
                ext = os.path.splitext(filename)[1].lower()
                format = {".gif": "GIF", ".png" : "PNG"}.get(ext, 'JPEG')
                for format in (format, 'JPEG', 'GIF', 'PNG'):
                    try:
                        pil.save(cached, format)
                        if os.path.getsize(cached):
                            break
                    except Exception:
                        pass
            except Exception:
                pixbuf = self.get_pixbuf(filename, True, False, 360, 120)
                pixbuf.savev(cached, 'jpeg', [], [])
        if not os.path.isfile(cached) or not os.path.getsize(cached):
            raise IOError('Could not create thumbnail')
        return cached

    def get_pixbuf(self, filename, force=False, zoom=None, width=None, height=None):
        if zoom is None:
            zoom = self.zoom

        width = width or self.get_max_image_width()
        height = height or self.get_max_image_height()

        while not force and self.current_preparing == (filename, zoom):
            logging.info("Waiting on cache")
            self.preparing_event.wait()
            self.preparing_event.clear()
        if filename in self.pix_cache[zoom]:
            cached = self.pix_cache[zoom][filename]
            if cached[1] == width:
                logging.info("Cache hit: " + filename)
                return cached[0]

        full_meta = None
        if not filename in self.meta_cache:
            full_meta = self.get_meta(filename)
        if filename in self.meta_cache:
            meta = self.meta_cache[filename]
            oriented = not meta[0]
            image_width, image_height = meta[1], meta[2]
        else:
            oriented = True
            image_width = image_height = None

        if oriented:
            try:
                if not image_width and self.fit_only_large:
                    format, image_width, image_height = GdkPixbuf.Pixbuf.get_file_info(filename)
                if not zoom:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        filename,
                        min(width, image_width if self.fit_only_large else width),
                        min(height, image_height if self.fit_only_large else height),
                        True)
                else:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
                self.pix_cache[zoom][filename] = pixbuf, width
                logging.debug("Loaded directly")
                return pixbuf
            except GObject.GError, e:
                pass # below we'll use another method

            try:
                if not full_meta:
                    full_meta = self.get_meta(filename)
                preview = full_meta.previews[-1].data
                pixbuf = self.pixbuf_from_data(
                    preview,
                    min(width, image_width if self.fit_only_large else width),
                    min(height, image_height if self.fit_only_large else height))
                self.pix_cache[zoom][filename] = pixbuf, width
                logging.debug("Loaded from preview")
                return pixbuf
            except Exception, e:
                pass # below we'll use another method

        pixbuf = self.pil_to_pixbuf(self.get_pil(filename, width, height, zoom))
        self.pix_cache[zoom][filename] = pixbuf, width
        logging.debug("Loaded with PIL")
        return pixbuf

    def get_pil(self, filename, width, height, zoomed_in=False):
        from PIL import Image
        import cStringIO
        meta = self.get_meta(filename)
        try:
            pil_image = Image.open(filename)
        except IOError:
            pil_image = Image.open(cStringIO.StringIO(meta.previews[-1].data))
        if not zoomed_in:
            pil_image.thumbnail((width, height), Image.ANTIALIAS)
        try:
            pil_image = self.auto_rotate(meta, pil_image)
        except Exception:
            logging.exception('Auto-rotation failed for %s' % filename)
        if not zoomed_in and (pil_image.size[0] > width or pil_image.size[1] > height):
            pil_image.thumbnail((width, height), Image.ANTIALIAS)
        return pil_image

    def pil_to_base64(self, pil_image):
        import cStringIO
        output = cStringIO.StringIO()
        pil_image.save(output, "PNG")
        contents = output.getvalue().encode("base64")
        output.close()
        return contents.replace('\n', '')

    def pil_to_pixbuf(self, pil_image):
        import cStringIO
        if pil_image.mode != 'RGB':          # Fix IOError: cannot write mode P as PPM
            pil_image = pil_image.convert('RGB')
        buff = cStringIO.StringIO()
        pil_image.save(buff, 'ppm')
        contents = buff.getvalue()
        buff.close()
        loader = GdkPixbuf.PixbufLoader()
        loader.write(contents)
        pixbuf = loader.get_pixbuf()
        loader.close()
        return pixbuf

    def needs_orientation(self, meta):
        return 'Exif.Image.Orientation' in meta.keys() and meta['Exif.Image.Orientation'].value != 1

    def needs_rotation(self, meta):
        return 'Exif.Image.Orientation' in meta.keys() and meta['Exif.Image.Orientation'].value in (5, 6, 7, 8)

    def auto_rotate(self, meta, im):
        from PIL import Image
        # We rotate regarding to the EXIF orientation information
        if 'Exif.Image.Orientation' in meta.keys():
            orientation = meta['Exif.Image.Orientation'].value
            if orientation == 1:
                # Nothing
                result = im
            elif orientation == 2:
                # Vertical Mirror
                result = im.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                # Rotation 180°
                result = im.transpose(Image.ROTATE_180)
            elif orientation == 4:
                # Horizontal Mirror
                result = im.transpose(Image.FLIP_TOP_BOTTOM)
            elif orientation == 5:
                # Horizontal Mirror + Rotation 270°
                result = im.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.ROTATE_270)
            elif orientation == 6:
                # Rotation 270°
                result = im.transpose(Image.ROTATE_270)
            elif orientation == 7:
                # Vertical Mirror + Rotation 270°
                result = im.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.ROTATE_270)
            elif orientation == 8:
                # Rotation 90°
                result = im.transpose(Image.ROTATE_90)
            else:
                result = im
        else:
            # No EXIF information, the user has to do it
            result = im

        return result

if __name__ == "__main__":
    Ojo()
