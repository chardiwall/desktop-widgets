"""Start and stop the managed widget session without replacing widget preferences."""

import subprocess

from gi.repository import Gio

from .gnome import HostError

APP_ID = "io.github.desktopwidgets.Settings"
MODE = "session-mode"
RESTORE_AVATAR = "resume-legacy-avatar"


def _legacy_avatar(operation):
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
        if self.settings.get_boolean(RESTORE_AVATAR):
            self.service("start")
        self._set_state("running", False)
