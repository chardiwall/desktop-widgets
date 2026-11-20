import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from desktop_widgets.bridge import integration
from desktop_widgets.bridge.gnome import EXTENSION, HostError
from desktop_widgets.bridge.integration import MARKER, PANEL_MARKER, prepare_extension, patch_extension


# The hook locations from a clean AzClock entry, in their original order.
SOURCE = """import {UpdateNotification} from './updateNotification.js';

class DesktopWidget {
    vfunc_allocate(box) {
        const {x, y} = this._getPosition();
        box.set_origin(x, y);
    }

    createElements() {
        if (element)
                this._elements.set(elementId, element);
            this.add_child(element);
        this._oldElementIds = elementIds;
        this.queue_relayout();
    }

    setStyle() {
        this.style = style;
    }

    _onDragBegin() {
        this._isDragging = true;
    }

    _onDragEnd() {
        this._isDragging = false;
    }
}

class AzClock {
    enable() {
        this.widgets = new Map();
        this._oldWidgetIds = [];
    }

    _enable() {
        SETTINGS.connectObject('changed::widgets', () => this._createWidgets(), this);
    }

    disable() {
        this._destroyWidgets();
    }

    _createWidgets() {
        const widgetIds = [];
        const deletedWidgets = this._oldWidgetIds.filter(x => !widgetIds.includes(x));
        for (const widgetId of widgetIds) {
            let widget = this.widgets.get(widgetId);
            if (!widget) {
                widget = this._createWidget(widgetId);
                this.widgets.set(widgetId, widget);
            }
        }
        this._oldWidgetIds = widgetIds;
        this._syncClockTimerToNearestSecond();
    }
}
"""


class IntegrationPatchTest(unittest.TestCase):
    def test_integration_applies_once(self):
        patched = patch_extension(SOURCE)
        self.assertEqual(patch_extension(patched), patched)
        self.assertIn(MARKER, patched)
        self.assertIn(PANEL_MARKER, patched)
        self.assertIn("element._ayahCard = decorateAyah(this, element, elementSettings);", patched)
        self.assertIn("this._widgetIndicator?.displayedWidgets(widgetIds)", patched)
        self.assertNotIn(integration.LEGACY_AVATAR_MARKER, patched)
        self.assertIn("this.widgets.has('avatar')", patched)
        self.assertIn("const load = import(", patched)
        self.assertIn("this._avatarPilot = new AvatarPilot(this);", patched)
        self.assertIn("this._avatarPilotLoad = null;\n        this._avatarPilot?.destroy();", patched)
        self.assertIn(integration.WIDGET_START_GUARD, patched)

    def test_upgrades_static_avatar_in_a_versioned_bundle(self):
        patched = patch_extension(SOURCE)
        legacy = patched.replace(integration.AVATAR_CANCEL, "").replace(
            integration.AVATAR_LOAD, integration.AVATAR_REFRESH
        ).replace(integration.WIDGET_START_GUARD, integration.WIDGET_START)
        legacy = legacy.replace(
            "import {UpdateNotification}",
            f"{integration.LEGACY_AVATAR_MARKER} from './{integration.BUNDLE}/bridge/azclock-avatar.js';\n\n"
            "import {UpdateNotification}",
        ).replace(
            "SETTINGS.connectObject('changed::widgets', () => this._createWidgets(), this);",
            "SETTINGS.connectObject('changed::widgets', () => this._createWidgets(), this);\n"
            "        this._avatarPilot = new AvatarPilot(this);",
        )
        versioned = f"{integration.RELEASES}/{'a' * 64}/desktop_widgets"
        self.assertEqual(patch_extension(legacy.replace(integration.BUNDLE, versioned)), patched)

    def test_upgrades_the_old_ayah_ornament_hook(self):
        patched = patch_extension(SOURCE)
        legacy = patched.replace(integration.AYAH_IMPORT, integration.LEGACY_AYAH_IMPORT).replace(
            integration.AYAH_ATTACH, integration.LEGACY_AYAH_ATTACH
        )
        for match, replacement in integration.AYAH_FRAME:
            legacy = legacy.replace(replacement, match)
        self.assertEqual(patch_extension(legacy), patched)

    def test_preparation_refuses_ambiguous_hooks_without_writing(self):
        with TemporaryDirectory() as temp:
            extension = Path(temp)
            (extension / "metadata.json").write_text(json.dumps({"uuid": EXTENSION, "version-name": "16.1"}))
            source = extension / "extension.js"
            patched = patch_extension(SOURCE)
            for label, ambiguous in (("fresh", SOURCE + "\nimport {UpdateNotification}"),
                                     ("integrated", patched + "\nthis._widgetIndicator?.refresh();")):
                with self.subTest(source=label):
                    source.write_text(ambiguous)
                    with self.assertRaisesRegex(HostError, "integration hook"):
                        prepare_extension(extension)
                    self.assertEqual(source.read_text(), ambiguous)
                    self.assertEqual(sorted(p.name for p in extension.iterdir()), ["extension.js", "metadata.json"])

    def test_upgrade_removes_legacy_pull_cord_and_attachment_hooks(self):
        patched = patch_extension(SOURCE)
        source = patched.replace(MARKER, "import {WidgetAttachments, displayedWidgets}")
        source = source.replace("/bridge/attachments.js", "/attachments.js")
        source += """
        this._widgetAttachments = new WidgetAttachments(this);
        this._widgetAttachments?.refresh();
        // Local patch (desk-light): locked widgets ignore the mouse entirely
        this._isDeskLightKnob = true;
        this.reactive = this._isDeskLightKnob || !this._settings.get_boolean('lock-widget');
        this.style = style + (EXTENSION?._widgetAttachments?.lightStyle(this) ?? '');
        if (this._isDeskLightKnob) // desk-light: suppress the menu
            return Clutter.EVENT_STOP;
        if (this._isDeskLightKnob) { // desk-light: toggle on click
            if (clicked) {
                togglePullCord();
            }
            return Clutter.EVENT_STOP;
        }
        this._removeMenuTimeout();
"""
        updated = patch_extension(source)
        self.assertTrue(updated.startswith(patched))
        for retired in ("WidgetAttachments", "_widgetAttachments", "DeskLightKnob", "togglePullCord", "lightStyle"):
            self.assertNotIn(retired, updated)
        self.assertIn("this.reactive = !this._settings.get_boolean('lock-widget');", updated)
        self.assertIn("this.style = style;\n        this._removeMenuTimeout();", updated)
        self.assertEqual(patch_extension(updated), updated)


class InstallationFailureTest(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(TemporaryDirectory())
        home = Path(temporary)
        data = home / "data"
        self.directory = data / "gnome-shell/extensions" / EXTENSION
        self.directory.mkdir(parents=True)
        self.metadata = self.directory / "metadata.json"
        self.metadata.write_text(json.dumps({"uuid": EXTENSION, "version-name": "16.1"}))
        self.entry = self.directory / "extension.js"
        self.previous = patch_extension(SOURCE).replace(MARKER, integration.LEGACY_ATTACHMENT_MARKER).encode()
        self.entry.write_bytes(self.previous)
        self.old_asset = self.directory / integration.BUNDLE / "bridge/attachments.js"
        self.old_asset.parent.mkdir(parents=True)
        self.old_asset.write_bytes(b"export class WidgetAttachments {}")
        self.assets = {"bridge/attachments.js": b"new attachment module", "widgets/avatar/placement.js": b"new placement"}
        self.enterContext(patch.object(integration.GLib, "get_user_data_dir", return_value=str(data)))
        self.enterContext(patch.object(Path, "home", return_value=home))
        self.enterContext(patch.object(integration, "bundle_assets", return_value=self.assets))
        self.enterContext(patch.object(integration.AzClockHost, "discover"))
        self.enterContext(patch("builtins.print"))

    def assert_previous_bundle(self):
        self.assertEqual(self.entry.read_bytes(), self.previous)
        self.assertEqual(self.old_asset.read_bytes(), b"export class WidgetAttachments {}")

    def test_invalid_metadata_reports_a_host_error_before_installing(self):
        for invalid in ("[]", "{", '"AzClock"'):
            with self.subTest(metadata=invalid):
                self.metadata.write_text(invalid)
                with self.assertRaisesRegex(HostError, "metadata.*JSON object"):
                    integration.install_bridge()
                self.assert_previous_bundle()
                self.assertFalse((self.directory / integration.RELEASES).exists())

    def test_failed_asset_write_preserves_previous_bundle_and_can_retry(self):
        write_bytes = Path.write_bytes

        def fail_last_file(path, contents):
            if path.name == "placement.js":
                raise OSError("write failed")
            return write_bytes(path, contents)

        with patch.object(Path, "write_bytes", fail_last_file):
            with self.assertRaisesRegex(OSError, "write failed"):
                integration.install_bridge()
        self.assert_previous_bundle()
        self.assertFalse(list((self.directory / integration.RELEASES).glob("*/desktop_widgets")))

        integration.install_bridge()
        installed = self.entry.read_bytes()
        attachments = next((self.directory / integration.RELEASES).glob("*/desktop_widgets/bridge/attachments.js"))
        self.assertIn(attachments.relative_to(self.directory).as_posix().encode(), installed)
        self.assertIn(b"import('./" + attachments.parent.relative_to(self.directory).as_posix().encode()
                      + b"/azclock-avatar.js')", installed)
        self.assertEqual(attachments.read_bytes(), self.assets["bridge/attachments.js"])
        self.assertEqual(self.old_asset.read_bytes(), b"export class WidgetAttachments {}")
        with patch.object(integration, "_replace_file", side_effect=AssertionError("unexpected rewrite")):
            integration.install_bridge()
        self.assertEqual(self.entry.read_bytes(), installed)

    def test_failed_legacy_shutdown_preserves_active_entry_and_assets(self):
        legacy = Path.home() / ".config/systemd/user/desk-light.service"
        legacy.parent.mkdir(parents=True)
        legacy.touch()
        with patch.object(integration.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "systemctl")):
            with self.assertRaises(subprocess.CalledProcessError):
                integration.install_bridge()
        self.assert_previous_bundle()

    def test_failed_activation_preserves_active_entry_and_assets(self):
        replace_file = integration._replace_file

        def fail_entry(path, contents, mode):
            if path == self.entry:
                raise OSError("activation failed")
            replace_file(path, contents, mode)

        with patch.object(integration, "_replace_file", side_effect=fail_entry):
            with self.assertRaisesRegex(OSError, "activation failed"):
                integration.install_bridge()
        self.assert_previous_bundle()
