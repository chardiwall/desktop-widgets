"""The desktop host for AzClock on GNOME."""

from dataclasses import replace
import json
from pathlib import Path
import re

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib

from ..settings import CARD_STYLES, Card, validate_card

SCHEMA = "org.gnome.shell.extensions.azclock"
PATH = "/org/gnome/shell/extensions/azclock/"
EXTENSION = "azclock@azclock.gitlab.com"
ELEMENTS = {"ayah": "verse", "clock": "card", "avatar": "body"}
DICTIONARY = GLib.VariantType.new("a{sv}")
CARD_WIDTH = re.compile(r"((?:^|;)\s*width:\s*)(\d+)px\b")
LEGACY_GLOW = re.compile(r"^rgba\([^)]*\); box-shadow: inset 0 0 26px 2px rgba\([^)]*\)(?=;)")
ANCHORS = {
    "Top left": ("Top_Left", 0.04, 0.06),
    "Top centre": ("Center_Top", 0.5, 0.06),
    "Top right": ("Top_Right", 0.96, 0.06),
    "Middle left": ("Center_Left", 0.04, 0.5),
    "Centre": ("Center", 0.5, 0.5),
    "Middle right": ("Center_Right", 0.96, 0.5),
    "Bottom left": ("Bottom_Left", 0.04, 0.94),
    "Bottom centre": ("Center_Bottom", 0.5, 0.94),
    "Bottom right": ("Bottom_Right", 0.96, 0.94),
}


class HostError(Exception):
    """The desktop host cannot complete the requested change."""


def _entries(value):
    return [value.get_child_value(index) for index in range(value.n_children())]


def _location(frame):
    try:
        location = json.loads(frame.get_string("location-data"))
    except ValueError:
        return {}
    return location if isinstance(location, dict) else {}


def _parse_colour(value):
    colour = Gdk.RGBA()
    value = value.partition(";")[0].strip()
    if value.lower() == "transparent":
        value = "rgba(0,0,0,0)"
    return colour if colour.parse(value) else None


def _channels(colour):
    return (colour.red * 255, colour.green * 255, colour.blue * 255)


def _hex_colour(colour, fallback):
    if colour is None:
        return fallback
    return "#" + "".join(f"{int(channel + 0.5):02x}" for channel in _channels(colour))


def _write(*changes):
    updates = [(settings, values) for settings, values in changes if values]
    for settings, values in updates:
        for key in values:
            if not settings.is_writable(key):
                raise HostError(f"The desktop setting {key} is read-only.")
    for settings, values in updates:
        settings.delay()
        for key, value in values.items():
            if not settings.set_value(key, value):
                for pending, _ in updates:
                    pending.revert()
                raise HostError(f"The desktop setting {key} could not be staged.")
    for settings, _ in updates:
        settings.apply()
    Gio.Settings.sync()


def _shell_call(name, path, method, parameters=None):
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return connection.call_sync(name, path, name, method, parameters, None,
                                Gio.DBusCallFlags.NONE, 900, None).unpack()


class AzClockHost:
    def __init__(self, source, backend=None):
        self.source = source
        self.backend = backend
        self.root = self._settings(SCHEMA)

    @classmethod
    def discover(cls):
        data_dirs = [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]
        for directory in data_dirs:
            schemas = Path(directory) / "gnome-shell/extensions" / EXTENSION / "schemas"
            if (schemas / "gschemas.compiled").is_file():
                source = Gio.SettingsSchemaSource.new_from_directory(str(schemas), None, False)
                return cls(source)
        raise HostError("Install the Desktop Widgets extension for GNOME, then reopen this app.")

    def watch_visibility(self, listener):
        handler = self.root.connect("changed::widgets", lambda *_: listener())
        return lambda: self.root.disconnect(handler)

    def _settings(self, schema_id, path=None):
        schema = self.source.lookup(schema_id, False)
        if schema is None:
            raise HostError("This version of Desktop Widgets has an incompatible settings schema.")
        return Gio.Settings.new_full(schema, self.backend, path)

    def widget(self, name):
        return self._settings(SCHEMA + ".widget-data", f"{PATH}widget-data/{name}/")

    def visibility(self):
        entries = _entries(self.root.get_value("widgets"))
        result = {}
        for name, element in ELEMENTS.items():
            properties = next((value for entry in entries
                               if (value := entry.lookup_value(name, DICTIONARY)) is not None), None)
            if properties is not None and any(
                element in entry for entry in self.widget(name).get_value("elements").unpack()
            ):
                result[name] = properties.unpack().get("enabled") is True
        return result

    def set_visible(self, name, visible):
        if name not in self.visibility():
            raise HostError("This widget is not configured in Desktop Widgets.")
        value = self.root.get_value("widgets")
        entries = _entries(value)
        widget_index = clock_index = None
        raise_avatar = name == "avatar" and visible
        for index, entry in enumerate(entries):
            if raise_avatar and entry.lookup_value("clock", DICTIONARY) is not None:
                clock_index = index
            properties = entry.lookup_value(name, DICTIONARY)
            if properties is None:
                continue
            widget_index = index
            if properties.unpack().get("enabled") is not visible:
                updated = GLib.VariantDict.new(properties)
                updated.insert_value("enabled", GLib.Variant("b", visible))
                outer = GLib.VariantDict.new(entry)
                outer.insert_value(name, updated.end())
                entries[index] = outer.end()
        if widget_index is None:
            raise HostError("A requested widget was removed.")
        if clock_index is not None and widget_index > clock_index:
            entries.insert(clock_index, entries.pop(widget_index))
        updated = GLib.Variant.new_array(DICTIONARY, entries)
        if updated != value:
            if not self.root.set_value("widgets", updated):
                raise HostError("The widget visibility setting could not be saved.")
            Gio.Settings.sync()

    def status(self):
        bus = "org.gnome.Shell.Extensions"
        try:
            info, = _shell_call(bus, "/org/gnome/Shell/Extensions", "GetExtensionInfo",
                                GLib.Variant("(s)", (EXTENSION,)))
        except GLib.Error:
            return "The GNOME session could not be reached. Reopen this app from your desktop session."
        state = info.get("state")
        if state == 1:
            return "Connected to GNOME Desktop Widgets."
        if state == 4:
            return "Desktop Widgets needs an update for this GNOME Shell version."
        if state == 3:
            return "Desktop Widgets reported a GNOME Shell error. Check it in the Extensions app."
        return "Enable Desktop Widgets in the GNOME Extensions app to show your widgets."

    def element(self, name):
        return self._settings(SCHEMA + ".element-data",
                              f"{PATH}widget-data/{name}/element-data/{ELEMENTS[name]}/")

    def card(self, name):
        if name not in self.visibility() or name == "avatar":
            raise HostError("This card is not configured in Desktop Widgets.")
        frame, label = self.widget(name), self.element(name)
        defaults = Card()
        background = _parse_colour(frame.get_string("background-color"))
        width = CARD_WIDTH.search(label.get_string("background-color"))
        override, font = label.get_value("font-family-override").unpack()
        if not frame.get_boolean("show-border"):
            style = "Minimal"
        elif frame.get_int("border-radius") > CARD_STYLES["Solid"][0]:
            style = "Glass"
        else:
            style = "Solid"
        transparency = round(100 * (1 - background.alpha)) if background is not None else 0
        if not frame.get_boolean("show-background"):
            transparency = 100
        return Card(
            transparency=transparency, style=style, background=_hex_colour(background, defaults.background),
            background_readable=background is not None,
            text=_hex_colour(_parse_colour(label.get_string("foreground-color")), defaults.text),
            accent=_hex_colour(_parse_colour(label.get_string("border-color")), defaults.accent),
            font=font if override else "", size=label.get_int("font-size"),
            width=int(width[2]) if width else defaults.width,
        )

    def apply_card(self, name, saved, changes):
        current = self.card(name)
        frame, label = self.widget(name), self.element(name)
        checked = changes.keys() | ({"background_readable"} if "background" in changes else set())
        if any(getattr(current, key) != getattr(saved, key) for key in checked):
            raise HostError("This card changed in GNOME. Cancel to reload its current settings.")
        card = replace(current, **changes)
        validate_card(card)
        frame_values = {}
        label_values = {}
        if {"background", "transparency"} & changes.keys():
            original = frame.get_string("background-color")
            _, separator, declarations = original.partition(";")
            colour = card.background
            if "background" not in changes or card.transparency:
                saved_colour = _parse_colour(card.background if "background" in changes else original)
                if saved_colour is None:
                    raise HostError("The saved background colour could not be read. Choose a colour before applying transparency.")
                rgb = ",".join(f"{channel:.6g}" for channel in _channels(saved_colour))
                colour = f"rgba({rgb},{card.opacity:.2f})"
            frame_values["background-color"] = GLib.Variant("s", colour + separator + declarations)
            if "transparency" in changes:
                frame_values["show-background"] = GLib.Variant("b", True)
        if "style" in changes:
            radius, border = CARD_STYLES[card.style]
            frame_values["show-border"] = GLib.Variant("b", bool(border))
            frame_values["border-radius"] = GLib.Variant("i", radius)
        if "text" in changes:
            label_values["foreground-color"] = GLib.Variant("s", card.text)
        if "accent" in changes:
            label_values["border-color"] = GLib.Variant("s", card.accent)
        if "font" in changes:
            # AzClock inserts the family into a double-quoted CSS string.
            if '"' in card.font or "\\" in card.font:
                raise HostError("AzClock cannot use this font family name.")
            label_values["font-family-override"] = GLib.Variant("(bs)", (bool(card.font), card.font))
        if "size" in changes:
            label_values["font-size"] = GLib.Variant("i", card.size)
        if "transparency" in changes:
            background = label.get_string("background-color")
            cleaned = LEGACY_GLOW.sub("rgba(0,0,0,0)", background)
            if cleaned != background:
                label_values["background-color"] = GLib.Variant("s", cleaned)
        if "width" in changes:
            # shortcut: AzClock's cards use inline width, replace when the host exposes a width key.
            background = label.get_string("background-color") if label.get_boolean("show-background") else "rgba(0,0,0,0)"
            if "background-color" in label_values:
                background = label_values["background-color"].get_string()
            background, replaced = CARD_WIDTH.subn(lambda match: f"{match[1]}{card.width}px", background)
            if not replaced:
                background = background.rstrip("; ") + f"; width: {card.width}px"
            label_values["show-background"] = GLib.Variant("b", True)
            label_values["background-color"] = GLib.Variant("s", background)
        _write((frame, frame_values), (label, label_values))
        return self.card(name)

    def displays(self):
        name = "org.gnome.Mutter.DisplayConfig"
        try:
            _, monitors, logical, _ = _shell_call(name, "/org/gnome/Mutter/DisplayConfig", "GetCurrentState")
        except GLib.Error as exc:
            raise HostError("GNOME could not provide the current displays.") from exc
        labels = {tuple(spec): properties.get("display-name", spec[2]) for spec, _, properties in monitors}
        displays = []
        for index, (_, _, _, _, primary, members, _) in enumerate(logical):
            if not members:
                continue
            key = " + ".join(sorted(member[0] for member in members))
            titles = " + ".join(labels.get(tuple(member), "") or member[0] for member in members)
            label = f"{titles} ({key})" + (" · Primary" if primary else "")
            displays.append((key, label, index))
        return displays

    def position(self, name, displays):
        frame = self.widget(name)
        index = _location(frame).get("monitorIndex")
        key = next((key for key, _, native in displays if native == index), None)
        anchor = frame.get_string("anchor-point")
        position = next((position for position, values in ANCHORS.items() if values[0] == anchor), "Top left")
        return key, position

    def place(self, name, display, position):
        if name not in self.visibility():
            raise HostError("Placement is available for configured widgets.")
        if position not in ANCHORS:
            raise HostError("Choose a supported anchor position.")
        index = next((index for key, _, index in self.displays() if key == display), None)
        if index is None:
            raise HostError("The selected display disconnected. Choose a connected display.")
        anchor, x, y = ANCHORS[position]
        frame = self.widget(name)
        loc = _location(frame)
        # shortcut: the pilot applies display margins, upgrade to measured work areas before release.
        if frame.get_string("anchor-point") != anchor or not all(
            type(loc.get(key)) in (float, int) and 0 <= loc[key] <= 1 for key in ("relativeX", "relativeY")
        ):
            loc.update(relativeX=x, relativeY=y)
        loc["monitorIndex"] = index
        _write((frame, {
            "anchor-point": GLib.Variant("s", anchor),
            "location-data": GLib.Variant("s", json.dumps(loc)),
            "convert-old-location-done": GLib.Variant("b", True),
            "lock-widget": GLib.Variant("b", True),
        }))
