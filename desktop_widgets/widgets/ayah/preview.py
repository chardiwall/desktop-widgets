"""Native GTK preview of the Ayah reminder."""

from math import ceil

from gi.repository import Gio, GLib, Gtk, Pango

from ...settings import CARD_STYLES
from .card import fit_verse, verse_from_markup
from .themes import ART, PRESETS, SIZING, SPEC


def _preset(card):
    if card.theme in PRESETS:
        return PRESETS[card.theme]
    base = PRESETS.get(card.art_theme, SPEC["custom"])
    radius, border = (base["radius"], base["border"]) if base.get("style") == card.style else CARD_STYLES[card.style]
    return {**base, "radius": radius, "border": border, "accent": card.accent,
            "font": card.font or SPEC["custom"]["font"], "arabic_font": card.arabic_font or SPEC["custom"]["arabic_font"]}


def _label(index):
    label = Gtk.Label(wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, xalign=1 if index == 0 else 0)
    label.set_direction(Gtk.TextDirection.RTL if index == 0 else Gtk.TextDirection.LTR)
    return label


def _panel(overlay, card, theme, width, height, miniature=False):
    opacity = 1 if miniature else card.opacity
    radius = 8 if miniature else theme["radius"]
    border = theme["border"]
    overlay.clip_css.load_from_string(f"overlay {{ border-radius: {radius}px; }}")
    paint = f"background-color: alpha({card.background}, {opacity}); border-radius: {radius}px;"
    overlay.fill_css.load_from_string(f"box {{ {paint} }}")
    overlay.frame_css.load_from_string(
        f"box {{ border: {border}px solid {card.accent}; border-radius: {radius}px; }}"
    )
    overlay.art.set_opacity(opacity)
    overlay.frame.set_opacity(opacity)
    art_key = (card.art_theme, width, height)
    if art_key == overlay.art_key:
        return
    overlay.art_key = art_key
    for layer in overlay.layers:
        overlay.art.remove_overlay(layer)
    overlay.layers.clear()
    for art in theme.get("art", ()):
        vertical, horizontal = art["anchor"].split("-")
        corner_scale = min(1, width / SIZING["width"])
        scale = min(height / SIZING["height"], SIZING["scenery_scale_max"]) if art.get("scenery") else corner_scale
        layer_width = round(art["width"] * scale)
        picture = Gtk.Box(can_target=False)
        x, y = (round(value * corner_scale) for value in art.get("inset", (0, 0)))
        picture.set_margin_start(x if horizontal == "left" else 0)
        picture.set_margin_end(x if horizontal == "right" else 0)
        picture.set_margin_top(y if vertical == "top" else 0)
        picture.set_margin_bottom(y if vertical == "bottom" else 0)
        _css(picture).load_from_string(
            f'box {{ background-image: url("{(ART / art["file"]).as_uri()}"); '
            f'background-size: {layer_width}px auto; background-repeat: no-repeat; '
            f'background-position: {horizontal} {vertical}; }}'
        )
        picture.set_opacity(art["opacity"])
        overlay.art.add_overlay(picture)
        overlay.layers.append(picture)


def _css(widget):
    provider = Gtk.CssProvider()
    widget.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return provider


def _panel_widget():
    overlay = Gtk.Overlay(overflow=Gtk.Overflow.HIDDEN, valign=Gtk.Align.START)
    overlay.set_direction(Gtk.TextDirection.LTR)
    overlay.clip_css = _css(overlay)
    fill = Gtk.Box()
    overlay.set_child(fill)
    overlay.fill_css = _css(fill)
    overlay.art = Gtk.Overlay(can_target=False)
    overlay.add_overlay(overlay.art)
    overlay.frame = Gtk.Box(can_target=False)
    overlay.add_overlay(overlay.frame)
    overlay.frame_css = _css(overlay.frame)
    overlay.layers = []
    overlay.art_key = None
    return overlay


def thumbnail(card, *, overlay=None):
    if overlay is None:
        overlay = _panel_widget()
        overlay.set_size_request(100, 60)
    _panel(overlay, card, _preset(card), 132, 60, miniature=True)
    return overlay


class AyahPreview:
    def __init__(self, settings):
        self.settings = settings
        self.card = None
        self.verse = ("", "Loading today’s ayah…", "")
        self.command = None
        self.poll = 0
        self.widget = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC, vscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True,
        )
        self.panel = _panel_widget()
        self.panel.set_halign(Gtk.Align.CENTER)
        self.widget.set_child(self.panel)
        self.widget.connect("map", self._mapped)
        self.widget.connect("unmap", self._unmapped)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SIZING["gap"])
        self.scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER, vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        )
        self.scroll.set_child(self.content)
        self.panel.add_overlay(self.scroll)
        self.labels = [_label(i) for i in range(3)]
        self.text_css = [_css(label) for label in self.labels]
        self.rule = Gtk.Box(halign=Gtk.Align.START)
        self.rule.set_size_request(SIZING["rule_width"], SIZING["rule_height"])
        self.rule_css = _css(self.rule)
        self.footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=SIZING["gap"], vexpand=True)
        self.footer_css = _css(self.footer)
        for child in self.labels[1:]:
            self.footer.append(child)
        for child in (self.labels[0], self.rule, self.footer):
            self.content.append(child)

    def _mapped(self, _):
        self.style_watch = self.widget.get_settings().connect("notify::gtk-xft-dpi", lambda *_: self.render())
        self.command_watch = [self.settings.connect(f"changed::{key}", self._source_changed) for key in
                              ("command", "polling-enabled", "polling-interval")]
        self._schedule()
        self.render()

    def _unmapped(self, _):
        self.widget.get_settings().disconnect(self.style_watch)
        for handler in self.command_watch:
            self.settings.disconnect(handler)
        if self.poll:
            GLib.source_remove(self.poll)
            self.poll = 0
        if self.command:
            self.command.force_exit()
            self.command = None

    def _source_changed(self, _settings, key):
        if key == "command" and self.command:
            self.command.force_exit()
            self.command = None
        self._schedule()

    def _schedule(self):
        if self.poll:
            GLib.source_remove(self.poll)
            self.poll = 0
        self._load_verse()
        if self.settings.get_boolean("polling-enabled"):
            self.poll = GLib.timeout_add(max(250, self.settings.get_int("polling-interval")), self._load_verse)

    def _load_verse(self):
        if self.command:
            return GLib.SOURCE_CONTINUE
        command = self.settings.get_string("command")
        if not command:
            self.verse = ("", "No Ayah source is configured.", "")
            self.render()
            return GLib.SOURCE_CONTINUE
        try:
            self.command = Gio.Subprocess.new(
                ["bash", "-c", command], Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            )
            self.command.communicate_utf8_async(None, None, self._loaded)
        except GLib.Error:
            self.verse = ("", "The Ayah source could not be opened.", "")
            self.render()
        return GLib.SOURCE_CONTINUE

    def _loaded(self, process, result):
        if process != self.command:
            return
        self.command = None
        try:
            _, output, errors = process.communicate_utf8_finish(result)
            if not process.get_successful() or errors or not output.strip():
                output = "The Ayah source returned no verse."
        except GLib.Error:
            output = "The Ayah source could not be read."
        verse = verse_from_markup(output)
        if verse != self.verse:
            self.scroll.get_vadjustment().set_value(0)
        self.verse = verse
        self.render()

    def render(self, card=None):
        if card is not None:
            self.card = card
        if self.card is None:
            return
        card = self.card
        theme = _preset(card)
        width = max(SIZING["min_width"], min(card.width, SIZING["max_width"]))
        viewport_height = 900
        if surface := self.widget.get_native():
            display = self.widget.get_display()
            if gdk_surface := surface.get_surface():
                if monitor := display.get_monitor_at_surface(gdk_surface):
                    geometry = monitor.get_geometry()
                    width = max(1, min(width, geometry.width - 2 * SIZING["margin"]))
                    viewport_height = max(1, geometry.height - 2 * SIZING["margin"])
        top, right, bottom, left = theme["padding"]
        self.content.set_margin_top(top)
        arabic_inset = theme["border"] + SIZING["arabic_padding"]
        for item in (self.labels[0], self.rule, *self.labels[1:]):
            item.set_margin_start(arabic_inset if item == self.labels[0] else left)
            item.set_margin_end(arabic_inset if item == self.labels[0] else right)

        shadow_rgb = "0,0,0" if int(card.text[1:3], 16) >= 128 else "255,246,224"
        shadow = f"rgba({shadow_rgb},{max(0.3, min(0.8, 1 - card.opacity))})"
        markup, content_height = fit_verse(self.verse, width, theme, card.arabic_size, card.size,
                                           lambda index: self.labels[index].create_pango_layout(None), viewport_height)
        height = min(content_height, viewport_height)
        _panel(self.panel, card, theme, width, height)
        self.panel.set_size_request(width, ceil(height))
        show_footer = any(markup[1:])
        self.footer.set_visible(show_footer)
        self.content.set_margin_bottom(0 if show_footer else bottom)
        tint = SIZING["footer_tint"] * card.opacity if markup[0] else 0
        self.footer_css.load_from_string(
            f"box {{ padding-bottom: {bottom}px; background-image: linear-gradient(to bottom, "
            f"transparent, alpha({card.background}, {tint}) {SIZING['footer_fade']}px); }}"
        )
        for index, (label, css, value) in enumerate(zip(self.labels, self.text_css, markup, strict=True)):
            colour = card.accent if index == 2 else card.text
            css.load_from_string(f"label {{ color: {colour}; text-shadow: 0 1px 3px {shadow}; }}")
            label.set_markup(value)
            label.set_opacity(card.foreground_opacity)
            label.set_visible(bool(value))
        self.rule.set_visible(bool(self.verse[0]))
        self.rule.set_opacity(card.foreground_opacity)
        self.rule_css.load_from_string(f"box {{ background-color: {card.accent}; }}")
