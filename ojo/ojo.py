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


import cairo
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import os
import sys

class Easylog:
    def __init__(self, level):
        self.level = level

    def log(x):
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
        print logging.exception(x)

logging = Easylog(1)

class Ojo(Gtk.Window):
    def __init__(self):
        super(Ojo, self).__init__()
        self.screen = self.get_screen()

        self.full = '-f' in sys.argv or '--fullscreen' in sys.argv
        self.mousedown_zoomed = False
        self.mousedown_panning = False

        self.set_decorated('-d' in sys.argv or '--decorated' in sys.argv)
        if '-m' in sys.argv or '--maximize' in sys.argv:
            self.maximize()

        self.update_size()

        self.visual = self.screen.get_rgba_visual()
        if self.visual and self.screen.is_composited():
            self.set_visual(self.visual)
        self.set_app_paintable(True)
        self.connect("draw", self.area_draw)

        self.box = Gtk.VBox()
        self.box.set_visible(True)

        self.scroll_window = Gtk.ScrolledWindow()
        self.image = Gtk.Image()
        self.image.set_visible(True)
        self.box.add(self.scroll_window)
        self.scroll_window.add_with_viewport(self.image)
        self.make_transparent(self.scroll_window)
        self.make_transparent(self.scroll_window.get_child())
        self.scroll_window.set_visible(True)
        self.add(self.box)

        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK)

        if self.full:
            self.set_margins(0)
            self.fullscreen()
        else:
            self.set_margins(30)
            self.set_position(Gtk.WindowPosition.CENTER)
        self.set_zoom(False, 0.5, 0.5)

    def main(self):
        path = os.path.realpath(sys.argv[-1])
        logging.info("Started with: " + path)
        self.meta_cache = {}
        self.pix_cache = {}
        self.current_preparing = None
        if os.path.isfile(path):
            self.mode = 'image'
            self.show(path, quick=True)
            self.update_size(True)

            GObject.idle_add(self.after_quick_start)
        else:
            self.mode = 'folder'
            self.current = os.path.join(path, 'none')
            self.after_quick_start()
            self.set_mode('folder')
            self.show(self.images[0], quick=True)

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
        if hasattr(self, "web_view_loaded"):
            GObject.idle_add(lambda: self.web_view.execute_script(command))
        else:
            GObject.timeout_add(100, lambda: self.js(command))

    def update_browser(self, file):
        self.js("select('%s')" % file)

    def save_zoom_scrolling(self):
        if self.zoom:
            ha = self.scroll_window.get_hadjustment()
            posh = ha.get_upper() - ha.get_page_size() - ha.get_lower()
            if posh > 0:
                self.zoom_x_percent = ha.get_value() / posh
            va = self.scroll_window.get_vadjustment()
            posv = va.get_upper() - va.get_page_size() - va.get_lower()
            if posv > 0:
                self.zoom_x_percent = va.get_value() / posv

    def update_zoom_scrolling(self):
        if self.zoom:
            def _f():
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
            GObject.idle_add(_f)

    def show(self, filename=None, orient=False, quick=False):
        if filename:
            logging.info("Showing " + filename)

        filename = filename or self.current
        self.current = filename
        self.selected = self.current
        self.set_title(self.current)
        self.pixbuf, oriented = self.get_pixbuf(self.current, orient)

#        self.save_zoom_scrolling()
        self.image.set_from_pixbuf(self.pixbuf)
        self.update_zoom_scrolling()

        if not orient and not oriented:
            def _check_orientation():
                meta = self.get_meta(filename)
                if self.current == filename and self.needs_orientation(meta):
                    self.show(self.current, True)
            GObject.idle_add(_check_orientation)

        if not quick:
            import time
            self.last_action_time = time.time()
            self.update_browser(self.current)
            self.cache_around()
        else:
            self.last_action_time = 0

    def after_quick_start(self):
        self.folder = os.path.dirname(self.current)
        self.images = filter(os.path.isfile, map(lambda f: os.path.join(self.folder, f), sorted(os.listdir(self.folder))))
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

#        def _ha(ha):
#            self.zoom_x_percent = ha.get_value() / (ha.get_upper() - ha.get_page_size() - ha.get_lower())
#        self.scroll_window.get_hadjustment().connect("value-changed", _ha)
#        def _va(va):
#            self.zoom_x_percent = va.get_value() / (va.get_upper() - va.get_page_size() - va.get_lower())
#        self.scroll_window.get_vadjustment().connect("value-changed", _va)
#
        GObject.idle_add(self.render_browser)

        self.start_cache_thread()
        if self.mode == "image":
            self.cache_around()
        self.start_thumbnail_thread()

    def make_transparent(self, widget):
        rgba = Gdk.RGBA()
        rgba.parse('rgba(0, 0, 0, 0)')
        widget.override_background_color(Gtk.StateFlags.NORMAL, rgba)

    def render_browser(self):
        from gi.repository import WebKit

        with open(os.path.join(os.path.dirname(os.path.normpath(__file__)), 'browse.html')) as f:
            html = f.read()

        self.web_view = WebKit.WebView()
        self.web_view.set_transparent(True)

        def nav(wv, wf, title):
            import time
            import json

            index = title.index(':')
            action = title[:index]
            argument = title[index + 1:]

            if action in ('ojo', 'ojo-select'):
                self.selected = argument
                if action == 'ojo':
                    def _do():
                        self.show(self.selected)
                        self.from_browser_time = time.time()
                        self.set_mode("image")
                    GObject.idle_add(_do)
            elif action == 'ojo-priority':
                files = json.loads(argument)
                self.priority_thumbs(map(lambda f: f.encode('utf-8'), files))
        self.web_view.connect("title-changed", nav)

        self.web_view.connect('document-load-finished', lambda wf, data: self.on_web_view_loaded()) # Load page

        self.web_view.load_string(html, "text/html", "UTF-8", "file://" + os.path.dirname(__file__) + "/")
        self.web_view.set_visible(True)
        self.make_transparent(self.web_view)
        self.browser.add(self.web_view)

    def on_web_view_loaded(self):
        self.web_view_loaded = True

        import threading
        def _thread():
            for img in self.images:
                self.js("add_image_div('%s', %s)" % (img, 'true' if img==self.current else 'false'))
                if img == self.current:
                    self.update_browser(img)
            pos = self.images.index(self.current)
            self.priority_thumbs([x[1] for x in sorted(enumerate(self.images), key=lambda (i,f): abs(i - pos))])

        prepare_thread = threading.Thread(target=_thread)
        prepare_thread.daemon = True
        prepare_thread.start()

    def cache_around(self):
        if not hasattr(self, "images"):
            return
        pos = self.images.index(self.current)
        for i in [1, -1]:
            if pos + i < 0 or pos + i >= len(self.images):
                continue
            f = self.images[pos + i]
            if not f in self.pix_cache:
                logging.debug("Caching around: " + f)
                self.cache_queue.append(f)
                self.cache_queue_event.set()

    def start_cache_thread(self):
        import threading
        self.cache_queue = []
        self.cache_queue_event = threading.Event()
        self.preparing_event = threading.Event()

        def _queue_thread():
            logging.info("Starting cache thread")
            while True:
                self.cache_queue_event.wait()
                if len(self.pix_cache) > 20:
                    self.pix_cache = {}

                while self.cache_queue:
                    file = self.cache_queue[0]
                    self.cache_queue.remove(file)
                    if not file in self.pix_cache:
                        logging.debug("Cache thread loads file " + file)
                        self.current_preparing = file
                        try:
                            self.get_meta(file)
                            self.get_pixbuf(file, orient=True, force=True)
                        except Exception:
                            logging.exception("Could not cache file " + file)
                        finally:
                            self.current_preparing = None
                            self.preparing_event.set()
                self.cache_queue_event.clear()
        cache_thread = threading.Thread(target=_queue_thread)
        cache_thread.daemon = True
        cache_thread.start()

    def start_thumbnail_thread(self):
        import threading
        import time
        self.prepared_thumbs = set()
        self.thumbs_queue = []
        self.thumbs_queue_event = threading.Event()

        def _thumbs_thread():
            # delay the start to give the caching thread some time to prepare next images
            start_time = time.time()
            while self.mode == "image" and time.time() - start_time < 2:
                time.sleep(0.1)

            logging.info("Starting thumbs thread")
            while True:
                self.thumbs_queue_event.wait()
                while self.thumbs_queue:
                    while time.time() - self.last_action_time < 2:
                        time.sleep(0.2)
                    img = self.thumbs_queue[0]
                    self.thumbs_queue.remove(img)
                    if not img in self.prepared_thumbs:
                        self.prepared_thumbs.add(img)
                        logging.debug("Thumbs thread loads file " + img)
                        self.add_thumb(img)
                self.thumbs_queue_event.clear()
        thumbs_thread = threading.Thread(target=_thumbs_thread)
        thumbs_thread.daemon = True
        thumbs_thread.start()

    def add_thumb(self, img):
        try:
            b64 = self.b64(img, 500, 120)
            self.js("add_image('%s', '%s')" % (img, b64))
            if img == self.current:
                self.update_browser(img)
        except Exception, e:
            self.js("remove_image_div('%s')" % img)
            logging.warning("Could not add thumb for " + img)

    def priority_thumbs(self, files):
        logging.debug("Priority thumbs: " + str(files))
        new_thumbs_queue = [self.current] + [f for f in files if not f in self.prepared_thumbs] + \
                           [f for f in self.thumbs_queue if not f in files and not f in self.prepared_thumbs]
        self.thumbs_queue = new_thumbs_queue
        self.thumbs_queue_event.set()

    def get_meta(self, filename):
        from pyexiv2 import ImageMetadata
        meta = ImageMetadata(filename)
        meta.read()
        self.meta_cache[filename] = self.needs_orientation(meta), meta.dimensions[0], meta.dimensions[1]
        self.js("set_dimensions('%s', '%d x %d')" % (filename, meta.dimensions[0], meta.dimensions[1]))
        return meta

    def set_margins(self, margin):
        self.margin = margin
        def _f():
            self.box.set_margin_right(margin)
            self.box.set_margin_left(margin)
            self.box.set_margin_bottom(margin)
            self.box.set_margin_top(margin)
        GObject.idle_add(_f)

    def update_size(self, from_image=False):
        if self.full:
            self.real_width = self.screen.get_width()
            self.real_height = self.screen.get_height()
        else:
            if from_image:
                self.real_width = self.pixbuf.get_width() + 2 * self.margin
                self.real_height = self.pixbuf.get_height() + 2 * self.margin
            else:
                self.real_width = self.screen.get_width() - 90
                self.real_height = self.screen.get_height() - 90
                if self.real_width > 1.5 * self.real_height:
                    self.real_width = int(1.5 * self.real_height)
                else:
                    self.real_height = int(self.real_width / 1.5)

        if not self.full:
            self.resize(self.real_width, self.real_height)
            self.move((self.screen.get_width() - self.real_width) // 2,
                (self.screen.get_height() - self.real_height) // 2)

    def get_max_image_width(self):
        return self.real_width - 2 * self.margin if not self.full else self.screen.get_width()

    def get_max_image_height(self):
        return self.real_height - 2 * self.margin if not self.full else self.screen.get_height()

    def go(self, direction, start_position=None):
        filename = None
        try:
            position = start_position - direction if not start_position is None else self.images.index(self.current)
            position = (position + direction + len(self.images)) % len(self.images)
            filename = self.images[position]
            self.show(filename)
            return
        except Exception, ex:
            logging.exception("go: Could not show " + filename)
            GObject.idle_add(lambda: self.go(direction))

    def toggle_fullscreen(self, full=None):
        if full is None:
            full = not self.full
        self.full = full

        self.pix_cache = {}

        if self.full:
            self.fullscreen()
            self.set_margins(0)
        else:
            self.unfullscreen()
            self.set_margins(30)

        self.update_size()
        self.update_cursor()
        self.show()

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
        if self.mode == "image" and self.selected != self.current:
            self.show(self.selected)
        else:
            self.last_action_time = 0
        self.update_cursor()
        self.scroll_window.set_visible(self.mode == 'image')
        self.image.set_visible(self.mode == 'image')
        self.browser.set_visible(self.mode == 'folder')

    def process_key(self, widget, event):
        key = Gdk.keyval_name(event.keyval)
        logging.debug("Pressed key " + key)
        if key == 'Escape':
            Gtk.main_quit()
        elif key in ("f", "F", "F11"):
            self.toggle_fullscreen()
            self.show()
        elif key == 'Return':
            modes = ["image", "folder"]
            self.set_mode(modes[(modes.index(self.mode) + 1) % len(modes)])
        elif self.mode == 'folder':
            self.js("on_key('%s')" % key)
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
            self.update_size()
            self.show()
        elif key in ("1", "0"):
            self.set_zoom(True)
            self.update_size()
            self.show()
        elif key in ("slash", "asterisk"):
            self.set_zoom(False)
            self.update_size()
            self.show()

    def set_zoom(self, zoom, x_percent=None, y_percent=None):
        self.zoom = zoom
        x_percent = x_percent or self.zoom_x_percent
        y_percent = y_percent or self.zoom_y_percent
        self.zoom_x_percent = x_percent
        self.zoom_y_percent = y_percent
        self.pix_cache = {}

    def mouse_motion(self, widget, event):
        if not self.mousedown_zoomed and not self.mousedown_panning:
            self.set_cursor(Gdk.CursorType.ARROW)
            return

        self.register_action()
        if self.mousedown_zoomed:
            self.set_zoom(True,
                min(1, max(0, event.x - 100) / max(1, self.real_width - 200)),
                min(1, max(0, event.y - 100) / max(1, self.real_height - 200)))
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
            import time
            mousedown_time = time.time()
            x = event.x
            y = event.y
            def act():
                if mousedown_time > self.last_mouseup_time:
                    self.mousedown_zoomed = True
                    self.register_action()
                    self.set_zoom(True,
                        min(1, max(0, x - 100) / max(1, self.real_width - 200)),
                        min(1, max(0, y - 100) / max(1, self.real_height - 200)))
                    self.show()
                    self.update_cursor()
            GObject.timeout_add(250, act)

    def register_action(self):
        import time
        self.last_action_time = time.time()

    def mouseup(self, widget, event):
        import time
        self.last_mouseup_time = time.time()
        if self.mode != "image" or event.button != 1:
            return
        if self.last_mouseup_time - self.from_browser_time < 0.2:
            return
        if self.mousedown_zoomed:
            self.set_zoom(False)
            self.show()
        elif self.mousedown_panning and (event.x != self.mousedown_x or event.y != self.mousedown_y):
            self.scroll_h = self.scroll_window.get_hadjustment().get_value()
            self.scroll_v = self.scroll_window.get_vadjustment().get_value()
        else:
            self.go(-1 if event.x < 0.5 * self.real_width else 1)
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

    def b64(self, filename, width, height):
        return self.pil_to_base64(self.get_pil(filename, width, height))

    def get_pixbuf(self, filename, orient, width=None, height=None, force=False):
        use_cache = width is None
        width = width or self.get_max_image_width()
        height = height or self.get_max_image_height()

        while not force and use_cache and self.current_preparing == filename:
            logging.info("Waiting on cache")
            self.preparing_event.wait()
            self.preparing_event.clear()
        if use_cache and filename in self.pix_cache:
            cached = self.pix_cache[filename]
            if cached[2] == width and (not orient or cached[1]):
                logging.debug("Cache hit: " + filename)
                return cached[0], cached[1]

        oriented = filename in self.meta_cache and not self.meta_cache[filename][0]
        if oriented or (not orient and not filename in self.meta_cache):
            try:
                if not self.zoom:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(filename, width, height, True)
                else:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(filename)
                if use_cache:
                    self.pix_cache[filename] = pixbuf, oriented, width
                logging.debug("Loaded directly")
                return pixbuf, oriented
            except GObject.GError, e:
                pass # below we'll use another method

            try:
                preview = self.get_meta(filename).previews[-1].data
                pixbuf = self.pixbuf_from_data(preview, width, height)
                if use_cache:
                    self.pix_cache[filename] = pixbuf, oriented, width
                logging.debug("Loaded from preview")
                return pixbuf, oriented
            except Exception, e:
                pass # below we'll use another method

        pixbuf = self.pil_to_pixbuf(self.get_pil(filename, width, height, self.zoom))
        if use_cache:
            self.pix_cache[filename] = pixbuf, True, width
        logging.debug("Loaded with PIL")
        return pixbuf, True

    def get_pil(self, filename, width, height, zoomed_in=False):
        from PIL import Image
        import cStringIO
        meta = self.get_meta(filename)
        try:
            pil_image = Image.open(filename)
        except IOError:
            pil_image = Image.open(cStringIO.StringIO(meta.previews[-1].data))
        pil_image = self.auto_rotate(meta, pil_image)
        if not zoomed_in:
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

#        import array
#        if pil_image.mode != 'RGB':
#            pil_image = pil_image.convert('RGB')
#        arr = array.array('B', pil_image.tostring())
#        height, width = pil_image.size
#        return GdkPixbuf.Pixbuf.new_from_data(
#            arr, GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4, None, None)

    def needs_orientation(self, meta):
        if 'Exif.Image.Orientation' in meta.keys():
            return meta['Exif.Image.Orientation'].value != 1
        else:
            return False

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
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    Ojo().main()
