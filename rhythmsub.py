"""
Rhythmsub: Subsonic support in Rhythmbox

Inspired by the excellent Ampache plugin. Probably buggy.

Copyright (c) 2013 Luke Carrier
Released under the terms of the GPLv3
"""

from collections import deque
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk, Peas, PeasGtk, RB
import json
import rb
import re
import time

from subsonic import Server as SubsonicServer

"""
Rhythmsub Rhythbox plugin.

This is the main plugin class which Rhythmbox seeks upon loading the plugin. It
contains the activation and deactivation functions which register and unregister
the Subsonic source.
"""
class Rhythmsub(GObject.Object, Peas.Activatable):
    # GObject type name
    __gtype_name = "RhythmsubPlugin"

    # Rhythmbox shell object
    object = GObject.property(type=GObject.Object)

    # RhythmsubDBEntryType instance
    __entry_type = None

    # RhythmsubSource instance
    __source = None

    """
    Initialiser.

    Calls parent initialisers.
    """
    def __init__(self):
        super(Rhythmsub, self).__init__()

    """
    Activate the plugin.

    Intantiates our entry type and source and registers them with the Rhythmbox
    database and shell so they become user accessible.
    """
    def do_activate(self):
        shell, db = self.object, self.object.props.db
        group     = RB.DisplayPageGroup.get_by_id("shared")

        theme = Gtk.IconTheme.get_default()
        what, width, height = Gtk.icon_size_lookup(Gtk.IconSize.LARGE_TOOLBAR)
        icon_file           = rb.find_plugin_file(self, "subsonic.png")
        icon                = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_file,
                                                                     width,
                                                                     height)

        self.__entry_type = RhythmsubDBEntryType()
        self.__source = GObject.new(
            RhythmsubSource,
            shell=shell,
            icon=icon,
            plugin=self,
            entry_type=self.__entry_type,
            name="Subsonic"
        )

        db.register_entry_type(self.__entry_type)
        shell.append_display_page(self.__source, group)
        shell.register_entry_type_for_source(self.__source, self.__entry_type)


    """
    Deactivate the plugin.

    Remove our source and entry type.
    """
    def do_deactivate(self):
        self.__source.delete_thyself()
        self.__source = None

        self.__entry_type = None

    """
    Get settings from GIO.

    Get the plugin's settings object from GIO.
    """
    def get_settings():
        return Gio.Settings("org.gnome.rhythmbox.plugins.rhythmsub")

"""
Rhythmsub cache queue.
"""
class RhythmsubCacheQueue:
    # RhythmsubCache instance
    __cache = None

    # State indicators
    __is_refreshing = None # Awaiting an append
    __is_processing = None # process_one() is running

    # The name of the queue (used in log output)
    __name = None

    # The contents of the queue
    __queue = None

    # Subsonic server instance
    _server = None

    """
    Initialiser.
    """
    def __init__(self, name, cache, server):
        self.__name  = name
        self._cache  = cache
        self._server = server

        self.__log("initialising")

        self.__is_refreshing = False
        self.__is_processing = False
        self.__queue         = deque()

    """
    Log a message.
    """
    def __log(self, msg):
        print("%s: %s" %(self.__name, msg))

    """
    Schedule item updates.
    """
    def extend(self, items):
        self.__log("adding %d items" %len(items))
        self.__queue.extend(items)

        self.refreshed()

    """
    Get the name of the queue.
    """
    def get_name(self):
        return self.__name

    """
    """
    def is_processing(self):
        return self.__is_processing

    """
    """
    def is_refreshing(self):
        return self.__is_refreshing

    """
    Process a limited number of queue items.
    """
    def process(self, num_items=1):
        self.__log("processing %d entries" %num_items)

        try:
            complete = False
            item = self.__queue.popleft()
            self.__log("processing %s" %item)

            self.__is_processing = True
            self.process_one(item)
            self.__is_processing = False

        except IndexError:
            complete = True
            self.__log("no items to process")

        return complete

    """
    Trigger the idle handler to ensure processing.
    """
    def refreshed(self):
        self.__log("refreshed; ensuring idle handler is active")
        self.__is_refreshing = False
        self._cache.ensure_idle_handler_active()

    """
    Indicate that the queue is refreshing.

    When queried by the idle handler, the queue reports that new items are being
    added. This can sometimes prevent the idle handler from exiting prematurely.

    You should call refreshed() when you're done, else the idle handler will
    poll for all eternity.
    """
    def refreshing(self):
        self.__is_refreshing = True


class RhythmsubCacheArtistQueue(RhythmsubCacheQueue):
    # Album queue
    __album_queue = None

    """
    Initialiser.
    """
    def __init__(self, name, cache, server, album_queue):
        super(self.__class__, self).__init__(name, cache, server)

        self.__album_queue = album_queue
 
    """
    Fetch all of the artists in the library and pass them to the album queue.
    """
    def process_one(self, artist):
        album_queue = self.__album_queue

        def complete_cb(resp):
            try:
                album_queue.extend(resp.children)
            except TypeError:
                pass # there are no children
            finally:
                album_queue.refreshed()

        self._server.get_music_directory_async(complete_cb, artist["id"])


class RhythmsubCacheAlbumQueue(RhythmsubCacheQueue):
    # Song queue
    __song_queue = None

    """
    Initialiser.
    """
    def __init__(self, name, cache, server, song_queue):
        super(self.__class__, self).__init__(name, cache, server)

        self.__song_queue = song_queue
 
    def process_one(self, album):
        song_queue = self.__song_queue

        def complete_cb(resp):
            song_queue.extend(resp.children)
            song_queue.refreshed()

        self._server.get_music_directory_async(complete_cb, album["id"])


class RhythmsubCacheSongQueue(RhythmsubCacheQueue):
    # RhythmDB instance
    __db = None

    # RhythmsubDBEntryType
    __entry_type = None

    """
    Initialiser.
    """
    def __init__(self, name, cache, server, db, entry_type):
        super(self.__class__, self).__init__(name, cache, server)

        self.__db         = db
        self.__entry_type = entry_type
 
    """
    Add/update one song.
    """
    def process_one(self, song):
        url = "rhythmsub://%s/%d" %(self._server.get_address(), song["id"])

        entry = self.__db.entry_lookup_by_location(url)
        if entry is None:
            entry = RB.RhythmDBEntry.new(self.__db, self.__entry_type, url)

        try:
            self.__db.entry_set(entry,  RB.RhythmDBPropType.ALBUM,        song["album"])
            self.__db.entry_set(entry,  RB.RhythmDBPropType.ARTIST,       song["artist"])
            self.__db.entry_set(entry,  RB.RhythmDBPropType.TITLE,        song["title"])
            self.__db.entry_set(entry,  RB.RhythmDBPropType.DATE,         song["year"])
        except KeyError:
            return False

        try: self.__db.entry_set(entry, RB.RhythmDBPropType.DURATION,     song["duration"])
        except KeyError: pass

        try: self.__db.entry_set(entry, RB.RhythmDBPropType.FILE_SIZE,    song["size"])
        except KeyError: pass

        try: self.__db.entry_set(entry, RB.RhythmDBPropType.GENRE,        song["genre"])
        except KeyError: pass

        try: self.__db.entry_set(entry, RB.RhythmDBPropType.TRACK_NUMBER, song["track"])
        except KeyError: pass

        self.__db.commit()


"""
Rhythmsub local content cache.

This class is responsible for maintaining the local RhythmDB cache of content
in the remote Subsonic server.
"""
class RhythmsubCache:
    # RhythmDB instance
    __db = None

    # The queues
    __queues = None

    # The Subsonic server instance
    __server = None

    """
    Initialiser.

    Prepare queues.
    """
    def __init__(self, db, entry_type, server):
        self.__db         = db
        self.__entry_type = entry_type
        self.__server     = server

        self.__queues = {
            "song": RhythmsubCacheSongQueue  ("song", self, self.__server, self.__db, self.__entry_type),
        }
        self.__queues["album"]  = RhythmsubCacheAlbumQueue ("album",  self, self.__server, self.__queues["song"])
        self.__queues["artist"] = RhythmsubCacheArtistQueue("artist", self, self.__server, self.__queues["album"])

        self.__idle_handler_active = False

    """
    Cache idle callback.

    Registered as an idle callback with Gdk; checks for and performs DB updates
    in the background until all queues are empty.
    """
    def __idle_handler(self, data):
        print("queue processing: run started at %d" %time.time())
        incomplete = []

        for name, queue in self.__queues.items():
            print("queue processing: %s" %name)

            if queue.is_processing():
                print("already processing")
                incomplete.append(name)
            else:
                queue.process()

            if queue.is_refreshing():
                print("refreshing")
                incomplete.append(name)

        if len(incomplete) == 0:
            self.__idle_handler_active = False
            return False

        print("queue processing: run completed with %s queues incomplete at %d"
                %(", ".join(set(incomplete)), time.time()))
        return True


    """
    Ensure the idle handler is running.

    This should be called whenever a queue is extended in order to ensure its
    contents gets processed.
    """
    def ensure_idle_handler_active(self):
        if self.__idle_handler_active == False:
            Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE, self.__idle_handler, {})
            self.__idle_handler_active = True

    """
    Update the local cache of Subsonic content.
    """
    def update(self):
        print("called")

        artist_queue = self.__queues["artist"]

        def complete_cb(resp):
            artist_queue.extend(resp.index)
            artist_queue.refreshed()

        self.__server.get_indexes_async(complete_cb)

        self.ensure_idle_handler_active()


"""
Rhythmsub configuration dialogue.
"""
class RhythmsubConfigDialog(GObject.Object, PeasGtk.Configurable):
    # GObject type name
    __gtype_name = 'RhythmsubConfigDialog'

    # Rhythmbox shell object
    object = GObject.property(type=GObject.Object)

    # Configuration dialogue's root widget
    __config_dialog = None

    # Settings from GIO
    __settings = None

    # GTK UI builder
    __ui = None

    """
    Create the configuration widget for display in plugin preferences.
    """
    def do_create_configure_widget(self):
        self.__settings = Rhythmsub.get_settings()

        self.__ui = Gtk.Builder()
        self.__ui.add_from_file(rb.find_plugin_file(self, "preferences.ui"))
        self.__config_dialog = self.__ui.get_object("rhythmsub-preferences")

        for input in ["address", "username", "password"]:
            input_object = self.__ui.get_object("server-" + input + "-entry")
            input_object.set_text(self.__settings[input])
            input_object.connect("changed", self.handle_change)

        return self.__config_dialog

    """
    Handle a value change event within the plugin's preferences.

    Given a widget object, alter the corresponding value in GIO.
    """
    def handle_change(self, widget):
        widget_name = Gtk.Buildable.get_name(widget)
        prop_name   = re.match("^server-(.+?)-entry$", widget_name).group(1)

        value = widget.get_text()

        self.__settings[prop_name] = value


"""
"""
class RhythmsubDBEntryType(RB.RhythmDBEntryType):
    def __init__(self):
        RB.RhythmDBEntryType.__init__(self, name="rhythmsub-entry-type")


"""
Rhythmsub database source.
"""
class RhythmsubSource(RB.BrowserSource):
    # Rhythmsub content cache
    __cache = None

    # RhythmDB instance
    __db = None

    # RhythmsubDBEntryType instance
    __entry_type = None

    # Settings from GIO
    __settings = None

    # Subsonic instance
    __server = None

    """
    Initialiser.

    Get settings and prepare a Subsonic client instance ready for requests. We
    should probably ping the server somewhere around here to report connection
    status, too.
    """
    def __init__(self, **kwargs):
        super(RhythmsubSource, self).__init__(self, **kwargs)

        self.__settings = Rhythmsub.get_settings()
        self.__server   = SubsonicServer(self.__settings["address"],
                                         self.__settings["username"],
                                         self.__settings["password"],
                                         "Rhythmsub",
                                         async_fetcher=RhythmboxLoaderAsyncFetcher)

    """
    Page tree double click handler.

    We use this as a cue to update the local song cache.
    """
    def do_activate(self):
        self.__shell      = self.props.shell
        self.__db         = self.__shell.props.db
        self.__entry_type = self.props.entry_type

        if not self.__cache:
            self.__cache = RhythmsubCache(self.__db, self.__entry_type, self.__server)
        self.__cache.update()

    """
    Page tree single click handler.

    One day we'll probably treat the first single click on our entry type as a
    cue to update the local cache.
    """
    def do_selected(self):
        pass

    """
    Set status bar progress/status text.
    """
    def __set_status(self, progress, progress_text=None, text=None):
        self.__progress = progress

        if progress_text is not None:
            self.__progress_text = progress_text

        if text is not None:
            self.__text = text

        self.notify_status_changed()


"""
Rhythmbox asynchronous fetcher class.

Make asynchronous HTTP requests using Rhythmbox's loader class.

XXX no attempt is made here to rate limit requests. Making a request higher than
the maximum number of file descriptors that can be held by a process will
probably crash gvfsd-http.

XXX make it possible to retry requests, maybe with an additional on_failure
callback. Somehow we'd need to track the number of attempts and pass it to the
failure callback for more intelligent error handling.
"""
class RhythmboxLoaderAsyncFetcher:
    def get(url, complete_cb):
        def real_complete_cb(resp, loader):
            data = json.loads(resp.decode("utf-8"))
            loader.rhythmsub_result = complete_cb(data)

        loader = rb.Loader()
        loader.get_url(url, real_complete_cb, loader)


# Not sure why this is necessary for only this object?
GObject.type_register(RhythmsubSource)
