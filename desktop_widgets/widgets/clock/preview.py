"""GTK preview of the themed clock using its live Pango renderer."""

from functools import lru_cache
import json
from pathlib import Path
import subprocess

from gi.repository import Gtk

from ...settings import CARD_STYLES
from ..ayah.preview import _css, _panel_widget, paint_panel
from ..ayah.themes import SIZING
from .themes import DESIGNS

SCRIPT = Path(__file__).with_suffix(".js")
ART = SCRIPT.with_name("art")
CELL_MARKUP = '<span font_family="DejaVu Sans Mono" size="{}pt">━━━━━━━━━━</span>'


@lru_cache(maxsize=128)
def _markup(card, cells, scale):
    return subprocess.check_output(
        ["gjs", "-m", str(SCRIPT), card, str(cells), str(scale)], text=True,
    ).strip()


class ClockPreview:
    def __init__(self, width=0):
        self.width = width
        self.widget = _panel_widget()
        self.widget.set_halign(Gtk.Align.CENTER)
        self.label = Gtk.Label(justify=Gtk.Justification.LEFT, xalign=0, valign=Gtk.Align.CENTER)
        self.widget.add_overlay(self.label)
        self.text_css = _css(self.label)

    def render(self, card):
        design = DESIGNS.get(card.clock_design, DESIGNS["Lantern"])
        radius, border = CARD_STYLES[card.style]
        width = self.width or min(SIZING["default_width"], card.width)
        scale = min(1, width / SIZING["width"])
        padding = max(8, round(18 * scale))
        radius = max(5, round((max(12, radius) if border else 8) * scale))
        self.widget.set_size_request(width, round(220 * scale))
        paint_panel(self.widget, card, {**design, "radius": radius, "border": border, "frame_opacity": 0.86},
                    width, round(220 * scale), art_dir=ART, mirror=card.face == "ar")
        self.text_css.load_from_string(f"label {{ color: {card.text}; }}")
        self.label.set_opacity(card.foreground_opacity)
        self.label.set_margin_start(padding)
        self.label.set_margin_end(padding)
        self.label.set_direction(Gtk.TextDirection.RTL if card.face == "ar" else Gtk.TextDirection.LTR)
        layout = self.label.create_pango_layout("")
        layout.set_markup(CELL_MARKUP.format(max(5, round(9 * scale))))
        ten_cells, _ = layout.get_pixel_size()
        content_width = width - 2 * padding
        cells = max(8, (content_width - 2) * 10 // max(1, ten_cells))
        values = {key: getattr(card, key) for key in ("face", "font", "arabic_font", "clock_design", "size", "accent")}
        values.update(width=card.width, headerWidth=content_width - max(36, round(100 * scale)),
                      height=round(192 * scale))
        self.label.set_markup(_markup(json.dumps(values), cells, scale))
