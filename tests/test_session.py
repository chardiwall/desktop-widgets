import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gi.repository import Gio

from desktop_widgets.bridge.gnome import EXTENSION, HostError
from desktop_widgets.bridge.integration import AVATAR_MARKER, LEGACY_AVATAR_MARKER
from desktop_widgets.bridge.session import Session, _legacy_avatar

SCHEMA = Path(__file__).resolve().parents[1] / "packaging/io.github.desktopwidgets.Settings.gschema.xml"


class SessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        subprocess.run(["glib-compile-schemas", "--strict", "--targetdir", directory.name, SCHEMA.parent], check=True)
        cls.schema = Gio.SettingsSchemaSource.new_from_directory(directory.name, None, False).lookup(
            "io.github.desktopwidgets.Settings", False
        )

    def setUp(self):
        self.settings = Gio.Settings.new_full(self.schema, Gio.memory_settings_backend_new(), None)
        self.operations = []
        self.active = True
        self.session = Session(self.settings, self.service)

    def service(self, operation):
        self.operations.append(operation)
        if operation == "is-active":
            return self.active
        self.active = operation == "start"
        return True

    def test_quit_stops_avatar_and_reopen_restores_that_service_once(self):
        self.session.quit()
        self.assertEqual(self.settings.get_string("session-mode"), "stopped")
        self.assertFalse(self.active)
        self.session.quit()
        self.session.reopen()
        self.session.reopen()
        self.assertEqual(self.settings.get_string("session-mode"), "running")
        self.assertEqual(self.operations.count("stop"), 1)
        self.assertEqual(self.operations.count("start"), 1)

    def test_quit_does_not_enable_an_inactive_legacy_service(self):
        self.active = False
        self.session.quit()
        self.session.reopen()
        self.assertEqual(self.operations, ["is-active"])

    def test_failed_stop_leaves_running_state_and_reports_failure(self):
        def fail(operation):
            if operation == "stop":
                raise HostError("Could not stop avatar")
            return self.service(operation)
        with self.assertRaisesRegex(HostError, "Could not stop"):
            Session(self.settings, fail).quit()
        self.assertEqual(self.settings.get_string("session-mode"), "running")

    def test_failed_reopen_stops_the_avatar_it_started_and_allows_retry(self):
        self.session.quit()
        with patch.object(self.settings, "set_string", return_value=False):
            with self.assertRaisesRegex(HostError, "Could not save"):
                self.session.reopen()
        self.assertFalse(self.active)
        self.assertEqual(self.operations[-2:], ["start", "stop"])
        self.assertEqual(self.settings.get_string("session-mode"), "stopped")
        self.assertTrue(self.settings.get_boolean("resume-legacy-avatar"))
        self.session.reopen()
        self.assertTrue(self.active)
        self.assertEqual(self.settings.get_string("session-mode"), "running")

    def test_both_bridge_startup_hooks_keep_the_legacy_avatar_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            entry = Path(directory) / "gnome-shell/extensions" / EXTENSION / "extension.js"
            entry.parent.mkdir(parents=True)
            with patch("desktop_widgets.bridge.session.GLib.get_user_data_dir", return_value=directory), \
                    patch("desktop_widgets.bridge.session.subprocess.run") as run:
                for marker in (AVATAR_MARKER, LEGACY_AVATAR_MARKER):
                    entry.write_text(marker)
                    self.assertFalse(_legacy_avatar("start"))
                run.assert_not_called()
