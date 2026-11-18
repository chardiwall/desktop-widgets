"""Install the shared desktop bridge against the user's existing AzClock 16.1."""

import json
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile

from gi.repository import GLib

from .gnome import EXTENSION, HostError

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "desktop-widget-settings/desktop_widgets"
BRIDGE_FILES = ("attachments.js", "indicator.js", "azclock-avatar.js", "listening.js", "track.js")
AVATAR_FILES = ("motion.js", "avatar-audio", "rest.rgba", "walk.rgba", "listening.rgba", "walk-data.js")
MARKER = "import {WidgetAttachments, displayedWidgets}"
PANEL_MARKER = "import {WidgetIndicator}"
HOOKS = (
    ("import {UpdateNotification}",
     MARKER + " from './desktop-widget-settings/desktop_widgets/bridge/attachments.js';\n\nimport {UpdateNotification}"),
    ("        const alwaysOnTop = this._settings.get_boolean('always-on-top');\n        if (alwaysOnTop)",
     "        const alwaysOnTop = EXTENSION?._widgetAttachments?.onTopFor(this) ??\n"
     "            this._settings.get_boolean('always-on-top');\n        if (alwaysOnTop)"),
    ("            super.vfunc_allocate(box);\n            return;",
     "            super.vfunc_allocate(box);\n            EXTENSION?._widgetAttachments?.allocated(this, box);\n            return;"),
    ("        super.vfunc_allocate(box);\n    }",
     "        super.vfunc_allocate(box);\n        EXTENSION?._widgetAttachments?.allocated(this, box);\n    }"),
    ("    _getPosition() {\n        const locationData",
     "    _getPosition() {\n"
     "        const attached = EXTENSION?._widgetAttachments?.positionFor(this);\n"
     "        if (attached)\n            return attached;\n        const locationData"),
    ("`${GLib.get_home_dir()}/.local/bin/desk-light`, 'toggle'",
     "'/usr/bin/desktop-widget-settings', '--toggle-pull-cord'"),
    ("        this.style = style;\n\n        this.queue_relayout();",
     "        this.style = style + (EXTENSION?._widgetAttachments?.lightStyle(this) ?? '');\n\n        this.queue_relayout();"),
    ("        this.widgets = new Map();\n        this._oldWidgetIds = [];",
     "        this.widgets = new Map();\n        this._widgetAttachments = new WidgetAttachments(this);\n"
     "        this._oldWidgetIds = [];"),
    ("    disable() {\n", "    disable() {\n        this._widgetAttachments?.destroy();\n"
     "        this._widgetAttachments = null;\n"),
    ("        const widgetIds = [];",
     "        let widgetIds = [];"),
    ("        const deletedWidgets = this._oldWidgetIds.filter",
     "        widgetIds = displayedWidgets(widgetIds);\n        const deletedWidgets = this._oldWidgetIds.filter"),
    ("        this._oldWidgetIds = widgetIds;\n", "        this._oldWidgetIds = widgetIds;\n"
     "        this._widgetAttachments?.refresh();\n"),
)
PANEL_HOOKS = (
    ("import {UpdateNotification}", PANEL_MARKER +
     " from './desktop-widget-settings/desktop_widgets/bridge/indicator.js';\n\nimport {UpdateNotification}"),
    ("        this._widgetAttachments = new WidgetAttachments(this);",
     "        this._widgetAttachments = new WidgetAttachments(this);\n"
     "        this._widgetIndicator = new WidgetIndicator(this);"),
    ("        this._widgetAttachments?.destroy();",
     "        this._widgetIndicator?.destroy();\n        this._widgetIndicator = null;\n"
     "        this._widgetAttachments?.destroy();"),
    ("        widgetIds = displayedWidgets(widgetIds);",
     "        widgetIds = displayedWidgets(this._widgetIndicator?.displayedWidgets(widgetIds) ?? widgetIds);"),
    ("        this._syncClockTimerToNearestSecond();",
     "        if (widgetIds.length)\n            this._syncClockTimerToNearestSecond();\n"
     "        this._widgetIndicator?.refresh();"),
)


AVATAR_MARKER = "import {AvatarPilot}"
AVATAR_HOOKS = (
    ("import {UpdateNotification}", AVATAR_MARKER +
     " from './desktop-widget-settings/desktop_widgets/bridge/azclock-avatar.js';\n\nimport {UpdateNotification}"),
    ("        this._oldElementIds = elementIds;\n        this.queue_relayout();",
     "        this._oldElementIds = elementIds;\n        this.queue_relayout();\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("        this._isDragging = true;", "        this._isDragging = true;\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("        this._isDragging = false;", "        this._isDragging = false;\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("        SETTINGS.connectObject('changed::widgets', () => this._createWidgets(), this);",
     "        SETTINGS.connectObject('changed::widgets', () => this._createWidgets(), this);\n"
     "        this._avatarPilot = new AvatarPilot(this);"),
    ("    disable() {\n", "    disable() {\n        this._avatarPilot?.destroy();\n"
     "        this._avatarPilot = null;\n"),
    ("        this._oldWidgetIds = widgetIds;", "        this._oldWidgetIds = widgetIds;\n"
     "        this._avatarPilot?.refresh();"),
)


def _apply_hooks(source, marker, hooks):
    if marker not in source:
        for match, replacement in hooks:
            if source.count(match) != 1:
                raise HostError(f"AzClock source does not match the integration hook: {match.strip()}")
            source = source.replace(match, replacement, 1)
    return source


def patch_avatar(source):
    for name in ("attachments.js", "indicator.js"):
        source = source.replace(f"{BUNDLE}/{name}", f"{BUNDLE}/bridge/{name}")
    source = source.replace("from './avatar/azclock.js'", f"from './{BUNDLE}/bridge/azclock-avatar.js'")
    return _apply_hooks(source, AVATAR_MARKER, AVATAR_HOOKS)


def patch_extension(source):
    source = _apply_hooks(source, MARKER, HOOKS)
    source = _apply_hooks(source, PANEL_MARKER, PANEL_HOOKS)
    return patch_avatar(source)


def _replace_file(destination, content, mode=0o644):
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        staging = Path(temporary.name)
        try:
            temporary.write(content)
            temporary.flush()
            staging.chmod(mode)
            staging.replace(destination)
        finally:
            staging.unlink(missing_ok=True)


def install_bridge():
    directory = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions" / EXTENSION
    entry = directory / "extension.js"
    metadata = json.loads((directory / "metadata.json").read_text())
    if metadata.get("uuid") != EXTENSION or metadata.get("version-name") != "16.1":
        raise HostError("This integration requires the local AzClock 16.1 setup.")
    if entry.is_symlink():
        raise HostError("Install AzClock in the local extensions directory before adding the integration.")
    original = entry.read_bytes()
    updated = patch_extension(original.decode()).encode()
    assets = {**{f"bridge/{name}": (ROOT / "bridge" / name).read_bytes() for name in BRIDGE_FILES},
              **{f"widgets/avatar/{name}": (ROOT / "widgets/avatar" / name).read_bytes()
                 for name in AVATAR_FILES}}
    backup = entry.with_name("extension.js.before-desktop-widget-settings")
    if original != updated:
        if backup.exists():
            if MARKER not in original.decode() and backup.read_bytes() != original:
                raise HostError("The AzClock source differs from the existing backup. Review both before continuing.")
        else:
            shutil.copy2(entry, backup)

    for asset, content in assets.items():
        destination = directory / BUNDLE / asset
        destination.parent.mkdir(parents=True, exist_ok=True)
        _replace_file(destination, content, 0o755 if destination.name == "avatar-audio" else 0o644)

    # The legacy watcher resets the card widths and borders on startup.
    legacy = Path.home() / ".config/systemd/user/desk-light.service"
    if legacy.is_file():
        subprocess.run(["systemctl", "--user", "disable", "--now", "desk-light.service"], check=True)
    legacy_avatar = Path.home() / ".config/systemd/user/desk-avatar.service"
    if legacy_avatar.is_file():
        subprocess.run(["systemctl", "--user", "disable", "--now", "desk-avatar.service"], check=True)
    if original != updated:
        _replace_file(entry, updated, entry.stat().st_mode & 0o777)
    print(f"Desktop bridge and avatar installed. Log out and back in to load them. Backup: {backup}")
