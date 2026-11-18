"""Music and Qur'an player launched by the desktop avatar."""

import sys
from pathlib import Path
from threading import Thread

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gio, GLib, Gst, Gtk


APP_ID = "io.github.desktopwidgets.Media"
RECITATION = "https://cdn.mp3quran.net/download/audio/muhammad-minshawi/r2/"
FORMATS = {".mp3", ".ogg", ".oga", ".opus", ".flac", ".wav", ".aac", ".m4a", ".aiff", ".wma"}
SURAHS = (
    "الفاتحة|البقرة|آل عمران|النساء|المائدة|الأنعام|الأعراف|الأنفال|التوبة|يونس|هود|يوسف|"
    "الرعد|إبراهيم|الحجر|النحل|الإسراء|الكهف|مريم|طه|الأنبياء|الحج|المؤمنون|النور|"
    "الفرقان|الشعراء|النمل|القصص|العنكبوت|الروم|لقمان|السجدة|الأحزاب|سبأ|فاطر|يس|"
    "الصافات|ص|الزمر|غافر|فصلت|الشورى|الزخرف|الدخان|الجاثية|الأحقاف|محمد|الفتح|"
    "الحجرات|ق|الذاريات|الطور|النجم|القمر|الرحمن|الواقعة|الحديد|المجادلة|الحشر|الممتحنة|"
    "الصف|الجمعة|المنافقون|التغابن|الطلاق|التحريم|الملك|القلم|الحاقة|المعارج|نوح|الجن|"
    "المزمل|المدثر|القيامة|الإنسان|المرسلات|النبأ|النازعات|عبس|التكوير|الانفطار|المطففين|"
    "الانشقاق|البروج|الطارق|الأعلى|الغاشية|الفجر|البلد|الشمس|الليل|الضحى|الشرح|التين|"
    "العلق|القدر|البينة|الزلزلة|العاديات|القارعة|التكاثر|العصر|الهمزة|الفيل|قريش|الماعون|"
    "الكوثر|الكافرون|النصر|المسد|الإخلاص|الفلق|الناس"
).split("|")


def music_files(folder):
    return sorted(
        (path for path in folder.iterdir() if path.suffix.lower() in FORMATS and path.is_file()),
        key=lambda path: (path.name.casefold(), path.name),
    )


def surah_uri(index):
    if not 0 <= index < len(SURAHS):
        raise IndexError("Invalid surah")
    return f"{RECITATION}{index + 1:03d}.mp3"


def audio_choices(label, model=None):
    search = Gtk.PropertyExpression.new(Gtk.StringObject, None, "string")
    dropdown = Gtk.DropDown.new(model, search)
    dropdown.set_enable_search(True)
    dropdown.update_property([Gtk.AccessibleProperty.LABEL], [label])
    return dropdown


class Player(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.current = None
        self.playing = False
        self.want_play = False
        self.progress_id = 0
        self.folder_revision = 0
        self.files = []

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gst.init(None)
        self.pipeline = Gst.ElementFactory.make("playbin")
        if self.pipeline:
            self.pipeline.props.flags = 0x02  # GST_PLAY_FLAG_AUDIO
            self.bus = self.pipeline.get_bus()
            self.bus.add_signal_watch()
            self.bus.connect("message", self.on_message)
        self.state = Gio.SimpleAction.new_stateful("now-playing", None, GLib.Variant("s", "none"))
        self.state.connect("change-state", lambda *_: None)
        self.add_action(self.state)
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("io.github.desktopwidgets.Settings", True) if source else None
        if schema:
            self.widget_session = Gio.Settings.new_full(schema, None, None)
            self.widget_session.connect("changed::session-mode", self.on_widget_session)
            self.widget_session.get_string("session-mode")

    def on_widget_session(self, settings, _):
        if settings.get_string("session-mode") == "stopped":
            self.quit()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args and args != ["music"] and args != ["quran"]:
            return 2
        if self.window is None:
            self.build_window()
        if args:
            self.tabs.set_visible_child_name(args[0])
        self.window.present()
        self.update_info()
        return 0

    def build_window(self):
        self.window = Gtk.ApplicationWindow(application=self, title="Avatar audio", default_width=460)
        self.window.connect("close-request", self.close_window)
        self.window.connect("notify::visible", lambda *_: self.update_timer())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        self.window.set_child(box)
        self.tabs = Gtk.Stack()
        switcher = Gtk.StackSwitcher(stack=self.tabs, halign=Gtk.Align.CENTER)
        box.append(switcher)
        box.append(self.tabs)

        music = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        folder = Gtk.Button(label="Choose music folder…", halign=Gtk.Align.START)
        folder.connect("clicked", self.choose_folder)
        music.append(folder)
        self.folder_label = Gtk.Label(label="Choose a folder to list its audio files.", xalign=0, wrap=True)
        music.append(self.folder_label)
        self.tracks = audio_choices("Music file")
        music.append(self.tracks)
        self.tabs.add_titled(music, "music", "Music")

        quran = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        heading = Gtk.Label(label="محمد صديق المنشاوي · المصحف المجوّد", xalign=1)
        heading.set_direction(Gtk.TextDirection.RTL)
        quran.append(heading)
        self.surahs = audio_choices("السورة", Gtk.StringList.new(
            [f"{i}. {name}" for i, name in enumerate(SURAHS, 1)]))
        self.surahs.set_direction(Gtk.TextDirection.RTL)
        quran.append(self.surahs)
        quran.append(Gtk.LinkButton.new_with_label(
            "https://www.mp3quran.net/eng/minsh_mjwd/", "Recording source · MP3Quran"))
        self.tabs.add_titled(quran, "quran", "القرآن")

        self.status = Gtk.Label(xalign=0, wrap=True)
        box.append(self.status)
        self.updating_progress = False
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.seek.set_draw_value(False)
        self.seek.update_property([Gtk.AccessibleProperty.LABEL], ["Playback position"])
        self.seek.connect("change-value", self.seek_to)
        box.append(self.seek)

        buttons = Gtk.Box(spacing=6)
        box.append(buttons)
        self.controls = {}
        for name, action in (("Previous", lambda: self.step(-1)), ("Play", self.play_or_pause),
                             ("Next", lambda: self.step(1)), ("Stop", self.stop)):
            button = Gtk.Button(label=name)
            button.connect("clicked", lambda _button, run=action: run())
            self.controls[name] = button
            buttons.append(button)
        volume = Gtk.VolumeButton()
        volume.set_value(1)
        volume.connect("value-changed", lambda _button, value: self.set_volume(value))
        buttons.append(volume)
        quit_button = Gtk.Button(label="Quit")
        quit_button.connect("clicked", lambda *_: self.quit())
        buttons.append(quit_button)

        self.tabs.connect("notify::visible-child-name", lambda *_: self.refresh_controls())
        self.tracks.connect("notify::selected", lambda *_: self.refresh_controls())
        self.surahs.connect("notify::selected", lambda *_: self.refresh_controls())
        self.refresh_controls()

    def selected(self):
        mode = self.tabs.get_visible_child_name()
        selection = self.tracks.get_selected() if mode == "music" else self.surahs.get_selected()
        if selection >= (len(self.files) if mode == "music" else len(SURAHS)):
            return None
        return (mode, selection)

    def choose_folder(self, _button):
        dialog = Gtk.FileDialog(title="Choose music folder")
        dialog.select_folder(self.window, None, self.folder_chosen)

    def folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result).get_path()
        except GLib.Error:
            return
        if folder is None:
            self.folder_label.set_text("Choose a folder stored on this device.")
            return
        self.folder_revision += 1
        revision = self.folder_revision
        self.folder_label.set_text("Reading folder…")

        def scan():
            try:
                files = music_files(Path(folder))
                message = f"{Path(folder).name} · {len(files)} audio files"
            except OSError as error:
                files = []
                message = f"Cannot read folder: {error.strerror}"
            GLib.idle_add(self.show_folder, revision, files, message)

        Thread(target=scan, daemon=True).start()

    def show_folder(self, revision, files, message):
        if revision == self.folder_revision and self.window is not None:
            if self.current and self.current[0] == "music":
                self.stop()
            self.files = files
            self.tracks.set_model(Gtk.StringList.new([path.name for path in files]))
            self.folder_label.set_text(message)
            self.refresh_controls()
        return GLib.SOURCE_REMOVE

    def playback(self, selection):
        if self.pipeline is None or selection is None:
            return
        if selection != self.current:
            self.pipeline.set_state(Gst.State.NULL)
            self.publish(False)
            mode, index = selection
            uri = self.files[index].as_uri() if mode == "music" else surah_uri(index)
            self.pipeline.props.uri = uri
            self.current = selection
        self.want_play = True
        self.status.set_text("Loading audio…")
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self.stop("Audio could not start.")
        self.refresh_controls()

    def play_or_pause(self):
        selection = self.selected()
        if self.pipeline and self.current == selection and self.want_play:
            self.want_play = False
            self.pipeline.set_state(Gst.State.PAUSED)
            self.publish(False)
            self.update_info()
        else:
            self.playback(selection)

    def step(self, direction):
        selection = self.selected()
        if selection is None:
            return
        mode, index = selection
        last = len(self.files if mode == "music" else SURAHS) - 1
        index = min(last, max(0, index + direction))
        (self.tracks if mode == "music" else self.surahs).set_selected(index)
        self.playback((mode, index))

    def set_volume(self, value):
        if self.pipeline:
            self.pipeline.props.volume = value

    def seek_to(self, _scale, _scroll, seconds):
        if self.current and not self.updating_progress:
            self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                                      int(seconds * Gst.SECOND))
        return False

    def update_progress(self):
        available = False
        if self.current:
            duration_ok, duration = self.pipeline.query_duration(Gst.Format.TIME)
            position_ok, position = self.pipeline.query_position(Gst.Format.TIME)
            available = duration_ok and position_ok and duration > 0
            if available:
                self.updating_progress = True
                self.seek.set_range(0, duration / Gst.SECOND)
                self.seek.set_value(position / Gst.SECOND)
                self.updating_progress = False
        self.seek.set_sensitive(available)
        return GLib.SOURCE_CONTINUE

    def update_timer(self):
        needs_timer = self.window and self.window.get_visible() and self.playing
        if needs_timer and not self.progress_id:
            self.progress_id = GLib.timeout_add(300, self.update_progress)
        elif not needs_timer and self.progress_id:
            GLib.source_remove(self.progress_id)
            self.progress_id = 0

    def publish(self, playing):
        self.playing = playing and self.current is not None
        value = self.current[0] if self.playing else "none"
        if self.state.get_state().get_string() != value:
            self.state.set_state(GLib.Variant("s", value))
        self.update_timer()

    def on_message(self, _bus, message):
        if message.type == Gst.MessageType.ERROR and self.current:
            error, _ = message.parse_error()
            self.stop(f"Audio unavailable: {error.message}")
        elif message.type == Gst.MessageType.EOS and self.current:
            mode, index = self.current
            last = len(self.files if mode == "music" else SURAHS) - 1
            if index < last:
                (self.tracks if mode == "music" else self.surahs).set_selected(index + 1)
                self.playback((mode, index + 1))
            else:
                self.stop()
        elif message.type == Gst.MessageType.STATE_CHANGED and message.src == self.pipeline:
            _, state, _ = message.parse_state_changed()
            self.publish(state == Gst.State.PLAYING and self.want_play)
            self.update_info()

    def refresh_controls(self):
        selection = self.selected()
        self.controls["Play"].set_label("Pause" if self.want_play and self.current == selection else "Play")
        for name in ("Play", "Previous", "Next"):
            self.controls[name].set_sensitive(selection is not None and self.pipeline is not None)
        self.controls["Stop"].set_sensitive(self.current is not None)

    def update_info(self):
        if self.current:
            mode, index = self.current
            title = self.files[index].name if mode == "music" else f"سورة {SURAHS[index]}"
            status = "Playing" if self.playing else "Loading" if self.want_play else "Paused"
            self.status.set_text(f"{status} · {title}")
        else:
            self.status.set_text("Select audio to play." if self.pipeline else "GStreamer playback is unavailable.")
        self.refresh_controls()
        self.update_progress()

    def stop(self, message=None):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        self.current = None
        self.want_play = False
        self.publish(False)
        self.update_info()
        if message:
            self.status.set_text(message)

    def close_window(self, window):
        if self.want_play:
            window.hide()
            return True
        return False

    def do_shutdown(self):
        if self.progress_id:
            GLib.source_remove(self.progress_id)
        if self.pipeline:
            self.bus.remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
        self.window = None
        Gtk.Application.do_shutdown(self)


if __name__ == "__main__":
    sys.exit(Player().run(sys.argv))
