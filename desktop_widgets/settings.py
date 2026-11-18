"""Portable card preferences and their draft/commit semantics."""

from dataclasses import asdict, dataclass, replace
import re

WIDGETS = {"ayah": "Ayah reminder", "clock": "Clock", "avatar": "Avatar"}
STYLES = ("Glass", "Solid", "Minimal")
COLORS = ("text", "accent", "background")
THEME_FIELDS = ("style", *COLORS, "font")
THEMES = {
    "ayah": {
        "Lantern": ("Solid", "#fff0d7", "#ffbc72", "#191a24", "DejaVu Serif"),
        "Blueprint": ("Glass", "#e5f0ff", "#88d9fa", "#1c2a34", "Ubuntu Sans"),
        "Oasis": ("Glass", "#edf8e6", "#9dd8b3", "#263628", "DejaVu Serif"),
        "Warm Earth": ("Solid", "#322119", "#b25e3d", "#f3e5d6", "Liberation Serif"),
        "Graphite": ("Minimal", "#f5f1ed", "#ad98ce", "#25232b", "Ubuntu Sans"),
    },
    "clock": {
        "Lantern": ("Solid", "#fff0d7", "#d7b45d", "#161c29", "DejaVu Serif"),
        "Blueprint": ("Glass", "#e5f0ff", "#88d9fa", "#1c2a34", "DejaVu Sans Mono"),
        "Oasis": ("Glass", "#edf8e6", "#9dd8b3", "#263628", "Ubuntu Sans"),
        "Warm Earth": ("Solid", "#322119", "#b25e3d", "#f3e5d6", "Liberation Serif"),
        "Afterglow": ("Minimal", "#ffeada", "#ff996d", "#482c44", "Ubuntu Sans"),
    },
}


def theme_preview(widget, name, card):
    return replace(card, **dict(zip(THEME_FIELDS, THEMES[widget][name], strict=True)))


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


def validate_card(card):
    for field in COLORS:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", getattr(card, field)):
            raise ValueError("Use a six-digit hexadecimal colour.")
    if type(card.transparency) is not int or not 0 <= card.transparency <= 100:
        raise ValueError("Choose transparency from 0 to 100 percent.")
    if card.style not in STYLES:
        raise ValueError("Choose a supported card style.")
    if not re.fullmatch(r"[\w .+()-]{0,100}", card.font):
        raise ValueError("Choose a font family with a supported name.")
    if not 8 <= card.size <= 48 or not 360 <= card.width <= 1000:
        raise ValueError("Choose a text size of 8–48 pt and a card width of 360–1000 px.")


class CardEditor:
    def __init__(self, widget, saved):
        self.widget = widget
        self.custom = saved
        self.theme = "Custom"
        self.mark_saved(saved)

    def select_theme(self, name):
        if name == "Custom":
            self.draft = replace(self.draft, **{
                field: getattr(self.custom, field) for field in THEME_FIELDS
            })
        else:
            self.draft = theme_preview(self.widget, name, self.draft)
        self.theme = name

    def edit(self, **values):
        draft = replace(self.draft, **values)
        validate_card(draft)
        self.draft = draft
        if values.keys() & set(THEME_FIELDS):
            self.theme = "Custom"
            self.custom = draft

    @property
    def dirty(self):
        return self.draft != self.saved

    def changes(self):
        return {key: value for key, value in asdict(self.draft).items() if value != getattr(self.saved, key)}

    def mark_saved(self, card):
        self.saved = self.draft = card
        self.saved_theme = self.theme
        self.saved_custom = self.custom

    def cancel(self, current=None):
        if current is not None and current != self.saved:
            self.custom = current
            self.theme = "Custom"
            self.mark_saved(current)
        else:
            self.draft = self.saved
            self.custom = self.saved_custom
            self.theme = self.saved_theme
