"""Portable card preferences and their draft/commit semantics."""

from dataclasses import asdict, dataclass, replace
import re

from .widgets.ayah.themes import THEMES as AYAH_THEMES
from .widgets.ayah.themes import SIZING as AYAH_SIZING
from .widgets.ayah.themes import PRESETS as AYAH_PRESETS
from .widgets.clock.themes import THEMES as CLOCK_THEMES

WIDGETS = {"ayah": "Ayah reminder", "clock": "Clock", "avatar": "Avatar"}
CARD_STYLES = {"Glass": (18, 1), "Solid": (8, 1), "Minimal": (2, 0)}
STYLES = tuple(CARD_STYLES)
COLORS = ("text", "accent", "background")
THEME_FIELDS = ("style", *COLORS, "font")
AYAH_EXTRAS = ("arabic_font", "arabic_size", "art_theme", "text_opacity")
AYAH_OPTIONS = ("size", "width", "transparency")
AYAH_APPEARANCE = (*THEME_FIELDS, *AYAH_OPTIONS, *AYAH_EXTRAS)
THEMES = {"ayah": AYAH_THEMES, "clock": CLOCK_THEMES}


def theme_preview(widget, name, card):
    fields = dict(zip(THEME_FIELDS, THEMES[widget][name], strict=True))
    if widget == "ayah":
        fields.update(theme=name, art_theme=name, arabic_font=AYAH_PRESETS[name]["arabic_font"], text_opacity=100)
    return replace(card, background_readable=True, **fields)


@dataclass(frozen=True)
class Card:
    style: str = "Glass"
    text: str = "#fff4e8"
    accent: str = "#e6b866"
    background: str = "#39333e"
    font: str = ""
    size: int = 14
    width: int = 600
    transparency: int = 45
    background_readable: bool = True
    theme: str = "Custom"
    arabic_font: str = ""
    arabic_size: int = 21
    art_theme: str = ""
    text_opacity: int = 100

    @property
    def opacity(self):
        return (100 - self.transparency) / 100

    @property
    def foreground_opacity(self):
        return self.text_opacity / 100


def validate_card(card):
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
        self.appearance_fields = AYAH_APPEARANCE if widget == "ayah" else THEME_FIELDS
        self.preset_options = preset_options or {
            **{field: getattr(saved, field) for field in AYAH_OPTIONS},
            "arabic_size": saved.size + AYAH_SIZING["arabic_extra"],
        }
        self.theme = saved.theme
        self.mark_saved(saved)

    def select_theme(self, name):
        if name == "Custom":
            self.draft = replace(self.draft, theme="Custom", background_readable=self.custom.background_readable, **{
                field: getattr(self.custom, field) for field in self.appearance_fields
            })
        else:
            self.draft = theme_preview(self.widget, name, self.draft)
            if self.widget == "ayah":
                self.draft = replace(self.draft, **self.preset_options)
        self.theme = name

    def edit(self, **values):
        if "background" in values:
            values["background_readable"] = True
        draft = replace(self.draft, **values)
        validate_card(draft)
        self.draft = draft
        if values.keys() & set(self.appearance_fields):
            self.theme = "Custom"
            self.draft = self.custom = replace(draft, theme="Custom")

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
        if self.widget == "ayah":
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
