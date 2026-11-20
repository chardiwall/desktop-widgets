"""Portable card preferences and their draft/commit semantics."""

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import re

from .widgets.ayah.themes import SIZING as AYAH_SIZING
from .widgets.ayah.themes import PRESETS as AYAH_PRESETS
from .widgets.clock.themes import DESIGNS

WIDGETS = {"ayah": "Ayah reminder", "clock": "Clock", "avatar": "Avatar"}
CARD_STYLES = {"Glass": (18, 1), "Solid": (8, 1), "Minimal": (2, 0)}
STYLES = tuple(CARD_STYLES)
COLORS = ("text", "accent", "background")
THEME_FIELDS = ("style", *COLORS, "font")
AYAH_EXTRAS = ("arabic_font", "arabic_size", "art_theme", "text_opacity")
AYAH_OPTIONS = ("size", "width", "transparency")
AYAH_APPEARANCE = (*THEME_FIELDS, *AYAH_OPTIONS, *AYAH_EXTRAS)
THEMES = {"ayah": AYAH_PRESETS, "clock": DESIGNS}
THEME_FAMILIES = {
    name: {
        "ayah": (f"{name} A", f"{name} B"),
        "clock": (name, f"{name} B"),
    }
    for name in DESIGNS if not name.endswith(" B")
}
CLOCK_FACES = {"en": "English", "ar": "Arabic (العربية)"}
CLOCK_APPEARANCE = (*THEME_FIELDS, *AYAH_OPTIONS, "clock_design", "arabic_font", "text_opacity")


def theme_art_paths():
    """Return the manifest artwork paths relative to the desktop_widgets package."""
    return sorted({
        Path("widgets") / widget / "art" / layer["file"]
        for widget, themes in THEMES.items()
        for theme in themes.values()
        for layer in theme["art"]
    })


def custom_theme_name(name, existing):
    name = name.strip()
    reserved = {*DESIGNS, *AYAH_PRESETS, *existing, "Custom"}
    if not name or len(name) > 48 or not name.isprintable():
        raise ValueError("Enter a theme name of 1–48 characters.")
    if name.casefold() in {item.casefold() for item in reserved}:
        raise ValueError("Choose a new theme name.")
    return name


def custom_snapshot(widget, card):
    fields = AYAH_APPEARANCE if widget == "ayah" else CLOCK_APPEARANCE
    return {"widget": widget, **{field: getattr(card, field) for field in fields}}


def custom_preview(widget, snapshot, card):
    source = snapshot["widget"]
    fields = {key: value for key, value in snapshot.items() if key != "widget"}
    if source != widget:
        design = fields["clock_design" if source == "clock" else "art_theme"]
        for variants in THEME_FAMILIES.values():
            if design in variants[source]:
                card = theme_preview(widget, variants[widget][variants[source].index(design)], card)
                break
        fields = {key: fields[key] for key in ("style", *COLORS)}
        fields.update(transparency=snapshot["transparency"], text_opacity=snapshot.get("text_opacity", 100))
    return fit_card_dimensions(replace(card, theme="Custom", background_readable=True, **fields))


def theme_preview(widget, name, card):
    preset = THEMES[widget][name]
    fields = {key: preset[key] for key in (*THEME_FIELDS, "arabic_font")}
    if widget == "ayah":
        fields.update(art_theme=name, text_opacity=100)
    else:
        fields["clock_design"] = name
    return replace(card, theme=name, custom_name="", background_readable=True, **fields)


@dataclass(frozen=True)
class Card:
    style: str = "Glass"
    text: str = "#fff4e8"
    accent: str = "#e6b866"
    background: str = "#39333e"
    font: str = ""
    size: int = 14
    width: int = AYAH_SIZING["default_width"]
    transparency: int = 45
    background_readable: bool = True
    theme: str = "Custom"
    arabic_font: str = ""
    arabic_size: int = 21
    art_theme: str = ""
    text_opacity: int = 100
    face: str = "en"
    clock_design: str = "Lantern"
    custom_name: str = ""

    @property
    def opacity(self):
        return (100 - self.transparency) / 100

    @property
    def foreground_opacity(self):
        return self.text_opacity / 100


def fit_card_dimensions(card):
    size = max(AYAH_SIZING["min_size"], min(card.size, 48))
    width = max(AYAH_SIZING["min_width"], min(card.width, AYAH_SIZING["max_width"]))
    arabic_size = max(AYAH_SIZING["min_size"], min(card.arabic_size, AYAH_SIZING["max_arabic_size"]))
    return replace(card, size=size, width=width, arabic_size=arabic_size)


def validate_card(card):
    if card.face not in CLOCK_FACES or card.clock_design not in DESIGNS:
        raise ValueError("Choose an available clock face and design.")
    for field in COLORS:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(card, field)):
            raise ValueError("Use a six-digit hexadecimal colour.")
    if any(type(value) is not int or not 0 <= value <= 100 for value in (card.transparency, card.text_opacity)):
        raise ValueError("Choose percentages from 0 to 100.")
    if card.style not in STYLES:
        raise ValueError("Choose a supported card style.")
    if any(font and not font.isprintable() for font in (card.font, card.arabic_font)):
        raise ValueError("Choose a font family with a supported name.")
    if not AYAH_SIZING["min_size"] <= card.size <= 48 or not AYAH_SIZING["min_width"] <= card.width <= AYAH_SIZING["max_width"]:
        raise ValueError("Choose a text size of 8–48 pt and a card width of 360–1000 px.")
    if type(card.arabic_size) is not int or not AYAH_SIZING["min_size"] <= card.arabic_size <= AYAH_SIZING["max_arabic_size"]:
        raise ValueError("Choose an Arabic text size of 8–55 pt.")


class CardEditor:
    def __init__(self, widget, saved, custom=None, preset_options=None):
        self.widget = widget
        self.custom = custom or saved
        self.appearance_fields = AYAH_APPEARANCE if widget == "ayah" else CLOCK_APPEARANCE
        self.preset_options = preset_options or {
            **{field: getattr(saved, field) for field in AYAH_OPTIONS},
            "arabic_size": saved.size + AYAH_SIZING["arabic_extra"],
        }
        self.theme = saved.theme
        self.mark_saved(saved)

    def select_theme(self, name):
        if name == "Custom":
            self.draft = replace(self.draft, theme="Custom", custom_name=self.custom.custom_name, background_readable=self.custom.background_readable, **{
                field: getattr(self.custom, field) for field in self.appearance_fields
            })
        else:
            self.draft = theme_preview(self.widget, name, self.draft)
            if self.widget == "ayah":
                self.draft = replace(self.draft, **self.preset_options)
            self.draft = fit_card_dimensions(self.draft)
        self.theme = name

    def select_custom(self, name, snapshot):
        draft = replace(custom_preview(self.widget, snapshot, self.draft), custom_name=name)
        validate_card(draft)
        self.theme = "Custom"
        self.draft = self.custom = draft

    def edit(self, **values):
        if "background" in values:
            values["background_readable"] = True
        draft = replace(self.draft, **values)
        validate_card(draft)
        self.draft = draft
        if values.keys() & set(self.appearance_fields):
            self.theme = "Custom"
            self.draft = self.custom = replace(draft, theme="Custom", custom_name="")

    @property
    def dirty(self):
        return self.draft != self.saved

    def changes(self):
        values = asdict(self.draft)
        values.pop("background_readable")
        changes = {key: value for key, value in values.items() if value != getattr(self.saved, key)}
        if self.draft.background_readable and not self.saved.background_readable:
            changes["background"] = self.draft.background
        return changes

    def mark_saved(self, card, custom=None):
        self.saved = self.draft = card
        self.theme = card.theme
        self.custom = card if card.theme == "Custom" else custom or self.custom
        self.saved_theme = self.theme
        self.saved_custom = self.custom

    def cancel(self, current=None, custom=None, preset_options=None):
        if preset_options is not None:
            self.preset_options = preset_options
        if current is not None and (current != self.saved or custom is not None):
            self.custom = custom or current
            self.theme = current.theme
            self.mark_saved(current)
        else:
            self.draft = self.saved
            self.custom = self.saved_custom
            self.theme = self.saved_theme
