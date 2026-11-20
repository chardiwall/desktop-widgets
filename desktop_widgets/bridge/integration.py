"""Install the shared desktop bridge against the user's existing AzClock 16.1."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory

from gi.repository import GLib

from .gnome import AzClockHost, EXTENSION, HostError
from ..settings import theme_art_paths

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "desktop-widget-settings/desktop_widgets"
RELEASES = "desktop-widget-settings/releases"
BRIDGE_FILES = ("attachments.js", "ayah.js", "clock.js", "indicator.js", "azclock-avatar.js", "listening.js", "track.js")
AVATAR_MODULES = ("motion.js", "placement.js")
AVATAR_FRAMES = ("rest.rgba", "walk.rgba", "listening.rgba", "walk-data.js")
MARKER = "import {displayedWidgets}"
AYAH_MARKER = "import {decorateAyah}"
AYAH_IMPORT = f"{AYAH_MARKER} from './{BUNDLE}/bridge/ayah.js';"
LEGACY_ATTACHMENT_MARKER = "import {WidgetAttachments, displayedWidgets}"
PANEL_MARKER = "import {WidgetIndicator}"
HOOKS = (
    ("import {UpdateNotification}",
     f"{MARKER} from './{BUNDLE}/bridge/attachments.js';\n\n" "import {UpdateNotification}"),
    ("        const widgetIds = [];",
     "        let widgetIds = [];"),
    ("        const deletedWidgets = this._oldWidgetIds.filter",
     "        widgetIds = displayedWidgets(widgetIds);\n        const deletedWidgets = this._oldWidgetIds.filter"),
)
LEGACY_AYAH_IMPORT = f"{AYAH_MARKER} from './{BUNDLE}/bridge/attachments.js';"
LEGACY_AYAH_ATTACH = (
    "                if (this._settingsId === 'ayah' && elementId === 'verse' && element.clutter_text)\n"
    "                    decorateAyah(element);\n"
)
AYAH_ATTACH = (
    "                if (this._settingsId === 'ayah' && elementId === 'verse' && element.clutter_text)\n"
    "                    element._ayahCard = decorateAyah(this, element, elementSettings);\n"
)
AYAH_HOOKS = (
    ("import {UpdateNotification}",
     AYAH_IMPORT + "\n\nimport {UpdateNotification}"),
    ("                this._elements.set(elementId, element);",
     AYAH_ATTACH + "                this._elements.set(elementId, element);"),
)
CLOCK_IMPORT = f"import {{decorateClock}} from './{BUNDLE}/bridge/clock.js';"
LEGACY_CLOCK_ATTACH = (
    "                if (this._settingsId === 'clock' && elementId === 'card' && element.clutter_text)\n"
    "                    decorateClock(element, elementSettings);\n"
)
CLOCK_ATTACH = (
    "                if (this._settingsId === 'clock' && elementId === 'card' && element.clutter_text)\n"
    "                    element._clockCard = decorateClock(this, element, elementSettings);\n"
)
CLOCK_HOOKS = (
    ("import {UpdateNotification}", CLOCK_IMPORT + "\n\nimport {UpdateNotification}"),
    ("                this._elements.set(elementId, element);",
     CLOCK_ATTACH + "                this._elements.set(elementId, element);"),
)
AYAH_FRAME = (
    ("            this.add_child(element);", "            this.add_child(element._ayahCard?.actor ?? element);"),
    ("        const {x, y} = this._getPosition();\n        box.set_origin(x, y);",
     "        const {x, y} = this._elements?.get('verse')?._ayahCard?.position(box) ?? this._getPosition();\n"
     "        box.set_origin(x, y);"),
    ("    setStyle() {\n", "    setStyle() {\n"
     "        if (this._elements.get('verse')?._ayahCard) {\n"
     "            this.style = '';\n"
     "            this.queue_relayout();\n"
     "            return;\n"
     "        }\n"),
)
CARD_FRAME = (
    (AYAH_FRAME[0][1], "            this.add_child(element._ayahCard?.actor ?? element._clockCard?.actor ?? element);"),
    (AYAH_FRAME[1][1], "        const card = this._elements?.get('verse')?._ayahCard ?? this._elements?.get('card')?._clockCard;\n"
     "        const {x, y} = card?.position(box) ?? this._getPosition();\n        box.set_origin(x, y);"),
    (AYAH_FRAME[2][1], "    setStyle() {\n"
     "        if (this._elements.get('verse')?._ayahCard || this._elements.get('card')?._clockCard) {\n"
     "            this.style = '';\n            this.queue_relayout();\n            return;\n        }\n"),
)
PANEL_HOOKS = (
    ("import {UpdateNotification}",
     f"{PANEL_MARKER} from './{BUNDLE}/bridge/indicator.js';\n\n" "import {UpdateNotification}"),
    ("        this._oldWidgetIds = [];",
     "        this._widgetIndicator = new WidgetIndicator(this);\n        this._oldWidgetIds = [];"),
    ("    disable() {\n",
     "    disable() {\n"
     "        this._widgetIndicator?.destroy();\n        this._widgetIndicator = null;\n"),
    ("        widgetIds = displayedWidgets(widgetIds);",
     "        widgetIds = displayedWidgets(this._widgetIndicator?.displayedWidgets(widgetIds) ?? widgetIds);"),
    ("        this._syncClockTimerToNearestSecond();",
     "        if (widgetIds.length)\n            this._syncClockTimerToNearestSecond();\n"
     "        this._widgetIndicator?.refresh();"),
)


LEGACY_AVATAR_MARKER = "import {AvatarPilot}"
AVATAR_MARKER = "this._avatarPilotLoad = load;"
AVATAR_REFRESH = "        this._oldWidgetIds = widgetIds;\n        this._avatarPilot?.refresh();"
AVATAR_STOP = "        this._avatarPilot?.destroy();\n        this._avatarPilot = null;\n"
AVATAR_CANCEL = "        this._avatarPilotLoad = null;\n"
AVATAR_LOAD = (
    f"{AVATAR_REFRESH}\n"
    "        if (this.widgets.has('avatar') && !this._avatarPilotLoad) {\n"
    f"            const load = import('./{BUNDLE}/bridge/azclock-avatar.js');\n"
    f"            {AVATAR_MARKER}\n"
    "            load.then(({AvatarPilot}) => {\n"
    "                if (this._avatarPilotLoad === load)\n"
    "                    this._avatarPilot = new AvatarPilot(this);\n"
    "            }).catch(error => {\n"
    "                if (this._avatarPilotLoad === load)\n"
    "                    console.warn(`Desktop Widgets: Avatar renderer could not start: ${error.message}`);\n"
    "            });\n"
    "        }"
)
AVATAR_HOOKS = (
    ("        this._oldElementIds = elementIds;\n        this.queue_relayout();",
     "        this._oldElementIds = elementIds;\n        this.queue_relayout();\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("        this._isDragging = true;", "        this._isDragging = true;\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("        this._isDragging = false;", "        this._isDragging = false;\n"
     "        EXTENSION?._avatarPilot?.refresh();"),
    ("    disable() {\n", "    disable() {\n" + AVATAR_CANCEL + AVATAR_STOP),
    ("        this._oldWidgetIds = widgetIds;", AVATAR_LOAD),
)
LEGACY_AVATAR_HOOKS = (
    (f"{LEGACY_AVATAR_MARKER} from './{BUNDLE}/bridge/azclock-avatar.js';\n\n", ""),
    ("        this._avatarPilot = new AvatarPilot(this);\n", ""),
    (AVATAR_STOP, AVATAR_CANCEL + AVATAR_STOP),
    (AVATAR_REFRESH, AVATAR_LOAD),
)
WIDGET_START = "\n                widget = this._createWidget(widgetId);"
WIDGET_START_GUARD = (
    "\n                try {"
    "\n                    widget = this._createWidget(widgetId);"
    "\n                } catch (error) {"
    "\n                    console.warn(`Desktop Widgets: ${widgetId} could not start: ${error.message}`);"
    "\n                    continue;"
    "\n                }"
)


def _replace_hooks(source, hooks):
    for match, replacement in hooks:
        if source.count(match) != 1:
            raise HostError(f"AzClock source does not match the integration hook: {match.strip()}")
        source = source.replace(match, replacement, 1)
    return source


def _apply_hooks(source, marker, hooks):
    return source if marker in source else _replace_hooks(source, hooks)


def patch_extension(source):
    source = re.sub(rf"(from |import\()'\./{RELEASES}/[0-9a-f]{{64}}/desktop_widgets(?=/bridge/)",
                    rf"\1'./{BUNDLE}", source)
    # Strip the local desk-light patch from both original and previously integrated installs.
    source = re.sub(
        r"        // Local patch \(desk-light\):[^\n]*\n(?:[^\n]*\n)*?"
        r"        this\.reactive = this\._isDeskLightKnob \|\| !this\._settings\.get_boolean\('lock-widget'\);",
        "        this.reactive = !this._settings.get_boolean('lock-widget');",
        source,
    )
    source = re.sub(r"        if \(this\._isDeskLightKnob\) // desk-light:[^\n]*\n"
                    r"            return Clutter\.EVENT_STOP;\n", "", source)
    source = re.sub(r"        if \(this\._isDeskLightKnob\) \{ // desk-light:[^\n]*\n"
                    r"(?:[^\n]*\n)*?        \}\n", "", source)
    source = source.replace(
        "this.style = style + (EXTENSION?._widgetAttachments?.lightStyle(this) ?? '');",
        "this.style = style;",
    )
    if LEGACY_ATTACHMENT_MARKER in source:
        source = source.replace(LEGACY_ATTACHMENT_MARKER, MARKER)
        source = source.replace(
            "EXTENSION?._widgetAttachments?.onTopFor(this) ??\n            ", "")
        source = source.replace(
            "        const attached = EXTENSION?._widgetAttachments?.positionFor(this);\n"
            "        if (attached)\n            return attached;\n", "")
        source = re.sub(r"^ +(?:EXTENSION\?\._widgetAttachments\?\.allocated\(this, box\);|"
                        r"this\._widgetAttachments(?: = new WidgetAttachments\(this\)| = null|"
                        r"\?\.(?:destroy|refresh)\(\));)\n", "", source, flags=re.MULTILINE)
        if "_widgetAttachments" in source or "WidgetAttachments" in source:
            raise HostError("AzClock source has an unrecognized Avatar attachment hook.")

    for name in ("attachments.js", "indicator.js"):
        source = source.replace(f"{BUNDLE}/{name}", f"{BUNDLE}/bridge/{name}")
    source = source.replace("from './avatar/azclock.js'", f"from './{BUNDLE}/bridge/azclock-avatar.js'")
    source = _apply_hooks(source, MARKER, HOOKS)
    if LEGACY_AYAH_IMPORT in source:
        source = _replace_hooks(source, ((LEGACY_AYAH_IMPORT, AYAH_IMPORT), (LEGACY_AYAH_ATTACH, AYAH_ATTACH)))
    source = _apply_hooks(source, AYAH_IMPORT, AYAH_HOOKS)
    if CARD_FRAME[0][1] not in source:
        source = _apply_hooks(source, AYAH_FRAME[0][1], AYAH_FRAME)
        source = _replace_hooks(source, CARD_FRAME)
    source = _apply_hooks(source, CLOCK_IMPORT, CLOCK_HOOKS)
    if LEGACY_CLOCK_ATTACH in source:
        source = _replace_hooks(source, ((LEGACY_CLOCK_ATTACH, CLOCK_ATTACH),))
    source = _apply_hooks(source, PANEL_MARKER, PANEL_HOOKS)
    if LEGACY_AVATAR_MARKER in source:
        source = _replace_hooks(source, LEGACY_AVATAR_HOOKS)
    else:
        source = _apply_hooks(source, AVATAR_MARKER, AVATAR_HOOKS)
    source = _apply_hooks(source, WIDGET_START_GUARD, ((WIDGET_START, WIDGET_START_GUARD),))
    for hook, count in (
        (f"{MARKER} from './{BUNDLE}/bridge/attachments.js';", 1),
        (AYAH_IMPORT, 1),
        (AYAH_ATTACH, 1),
        (CLOCK_IMPORT, 1),
        (CLOCK_ATTACH, 1),
        *((replacement, 1) for _, replacement in CARD_FRAME),
        (f"{PANEL_MARKER} from './{BUNDLE}/bridge/indicator.js';", 1),
        (AVATAR_LOAD, 1),
        (AVATAR_CANCEL + AVATAR_STOP, 1),
        (WIDGET_START_GUARD, 1),
        ("let widgetIds = [];", 1),
        ("new WidgetIndicator(this);", 1),
        ("this._widgetIndicator?.destroy();", 1),
        ("this._widgetIndicator?.refresh();", 1),
        ("widgetIds = displayedWidgets(this._widgetIndicator?.displayedWidgets(widgetIds) ?? widgetIds);", 1),
        ("new AvatarPilot(this);", 1),
        ("this._avatarPilot?.destroy();", 1),
        ("EXTENSION?._avatarPilot?.refresh();", 3),
        ("this._avatarPilot?.refresh();", 1),
    ):
        if source.count(hook) != count:
            raise HostError(f"AzClock source does not match the integration hook: {hook}")
    return source


def prepare_extension(directory):
    try:
        metadata = json.loads((directory / "metadata.json").read_text())
    except ValueError as exc:
        raise HostError("AzClock metadata must be a valid JSON object.") from exc
    if not isinstance(metadata, dict):
        raise HostError("AzClock metadata must be a valid JSON object.")
    if metadata.get("uuid") != EXTENSION or metadata.get("version-name") != "16.1":
        raise HostError("This integration requires the local AzClock 16.1 setup.")
    entry = directory / "extension.js"
    if entry.is_symlink():
        raise HostError("Use a local AzClock source file before adding the integration.")
    original = entry.read_bytes()
    return original, patch_extension(original.decode()).encode()


def bundle_assets(frames, audio):
    avatar = ROOT / "widgets/avatar"
    ayah = ROOT / "widgets/ayah"
    clock = ROOT / "widgets/clock"
    paths = {
        **{f"bridge/{name}": ROOT / "bridge" / name for name in BRIDGE_FILES},
        **{f"widgets/clock/{name}": clock / name for name in ("face.js", "themes.json")},
        **{f"widgets/ayah/{name}": ayah / name for name in ("card.js", "themes.json")},
        **{path.as_posix(): ROOT / path for path in theme_art_paths()},
        **{f"widgets/avatar/{name}": avatar / name for name in AVATAR_MODULES},
        **{f"widgets/avatar/{name}": frames / name for name in AVATAR_FRAMES},
        "widgets/avatar/avatar-audio": audio,
    }
    return {path: source.read_bytes() for path, source in paths.items()}


def _replace_file(destination, content, mode):
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        staging = Path(temporary.name)
        try:
            temporary.write(content)
            temporary.flush()
            staging.chmod(mode)
            staging.replace(destination)
        finally:
            staging.unlink(missing_ok=True)


def prepare_release(directory, entry, assets):
    digest = hashlib.sha256()
    for name, content in sorted(assets.items()):
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
    bundle = f"{RELEASES}/{digest.hexdigest()}/desktop_widgets"
    destination = directory / bundle
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        with TemporaryDirectory(dir=destination.parent, prefix=".stage-") as temporary:
            staged = Path(temporary) / "desktop_widgets"
            for name, content in assets.items():
                file = staged / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(content)
                file.chmod(0o755 if file.name == "avatar-audio" else 0o644)
            try:
                staged.rename(destination)
            except OSError:
                if not destination.is_dir():
                    raise
    for name, content in assets.items():
        if (destination / name).read_bytes() != content:
            raise HostError(f"The staged AzClock release differs from the package at {name}.")
    return entry.replace(f"'./{BUNDLE}/bridge/".encode(), f"'./{bundle}/bridge/".encode())


def install_bridge():
    directory = Path(GLib.get_user_data_dir()) / "gnome-shell/extensions" / EXTENSION
    entry = directory / "extension.js"
    original, updated = prepare_extension(directory)
    avatar = ROOT / "widgets/avatar"
    assets = bundle_assets(avatar, avatar / "avatar-audio")
    backup = entry.with_name("extension.js.before-desktop-widget-settings")
    if (backup.exists() and MARKER.encode() not in original and LEGACY_ATTACHMENT_MARKER.encode() not in original
            and backup.read_bytes() != original):
        raise HostError("The AzClock source differs from the existing backup. Review both before continuing.")

    updated = prepare_release(directory, updated, assets)

    # The legacy watcher resets the card widths and borders on startup.
    config = Path.home() / ".config"
    units = config / "systemd/user"
    for unit in ("desk-light.service", "desk-avatar.service"):
        if (units / unit).is_file():
            subprocess.run(["systemctl", "--user", "disable", "--now", unit], check=True)
    state = config / "desk-light/state"
    if not state.is_symlink() and state.is_file() and state.read_bytes().strip() == b"on":
        _replace_file(state, b"off\n", state.stat().st_mode & 0o777)
    host = AzClockHost.discover()
    host.retire_pull_cord()
    if host.has_custom_ayah and "ayah" in host.visibility():
        card = host.card("ayah")
        if card.theme in AYAH_PRESETS:
            host.apply_card("ayah", card, {})
    if original != updated:
        if not backup.exists():
            _replace_file(backup, original, entry.stat().st_mode & 0o777)
        _replace_file(entry, updated, entry.stat().st_mode & 0o777)
    print(f"Desktop bridge and avatar installed. Log out and back in to load them. Backup: {backup}")
