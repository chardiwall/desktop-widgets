"""Start and stop the managed widget session without replacing widget preferences."""

from pathlib import Path
import subprocess

from gi.repository import Gio, GLib

from .gnome import EXTENSION, HostError
from .integration import AVATAR_MARKER, LEGACY_AVATAR_MARKER

APP_ID = "io.github.desktopwidgets.Settings"
MODE = "session-mode"
RESTORE_AVATAR = "resume-legacy-avatar"


def _legacy_avatar(operation):
    directory = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions" / EXTENSION
    entry = directory / "extension.js"
    if entry.is_file():
        source = entry.read_text()
        if AVATAR_MARKER in source or LEGACY_AVATAR_MARKER in source:
            return False
    result = subprocess.run(
        ["systemctl", "--user", operation, "desk-avatar.service"],
        text=True, capture_output=True, timeout=8,
    )
    if operation == "is-active" and result.returncode in (3, 4):
        return False
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise HostError(f"Could not {operation} the legacy avatar service. {detail}".strip())
    return True


class Session:
    def __init__(self, settings, service=_legacy_avatar):
        self.settings = settings
        self.service = service

    @classmethod
    def discover(cls):
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup(APP_ID, True) if source else None
        return cls(Gio.Settings.new_full(schema, None, None)) if schema else None

    def watch_stopped(self, listener):
        def changed(settings, _):
            if settings.get_string(MODE) == "stopped":
                listener()

        self.settings.connect("changed::" + MODE, changed)

    def _set_state(self, mode, restore_avatar):
        self.settings.delay()
        if not (
            self.settings.set_boolean(RESTORE_AVATAR, restore_avatar)
            and self.settings.set_string(MODE, mode)
        ):
            self.settings.revert()
            raise HostError("Could not save widget session state.")
        self.settings.apply()
        Gio.Settings.sync()

    def quit(self):
        if self.settings.get_string(MODE) == "stopped":
            return
        if not all(self.settings.is_writable(key) for key in (MODE, RESTORE_AVATAR)):
            raise HostError("The widget session setting is read-only.")
        active = self.service("is-active")
        if active:
            self.service("stop")
        try:
            self._set_state("stopped", active)
        except HostError:
            if active:
                self.service("start")
            raise

    def reopen(self):
        if self.settings.get_string(MODE) != "stopped":
            return
        if not all(self.settings.is_writable(key) for key in (MODE, RESTORE_AVATAR)):
            raise HostError("The widget session setting is read-only.")
        started = (self.settings.get_boolean(RESTORE_AVATAR) and not self.service("is-active")
                   and self.service("start"))
        try:
            self._set_state("running", False)
        except HostError as exc:
            if started:
                try:
                    self.service("stop")
                except (HostError, OSError, subprocess.SubprocessError) as rollback:
                    raise HostError(f"{exc} The legacy Avatar could not be stopped: {rollback}") from rollback
            raise
