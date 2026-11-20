"""Native settings for the three desktop widgets."""

import argparse
from datetime import datetime
from html import escape
import subprocess

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, PangoCairo

from .bridge.gnome import ANCHORS, AzClockHost, HostError
from .bridge.integration import install_bridge
from .bridge.session import APP_ID, Session
from .settings import CARD_STYLES, CardEditor, STYLES, THEMES, WIDGETS, theme_preview
from .widgets.ayah.preview import AyahPreview, thumbnail
from .widgets.ayah.themes import SIZING as AYAH_SIZING
from .widgets.ayah.themes import SPEC as AYAH_SPEC

EXTENSIONS_URL = "https://extensions.gnome.org/extension/5156/desktop-clock/"
AYAH_COLUMNS = ("Lantern", "Blueprint", "Oasis", "Warm Earth", "Graphite")
SETTINGS_MIN_WIDTH = 890


def _row(group, title, control, subtitle=None):
    row = Adw.ActionRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    control.set_valign(Gtk.Align.CENTER)
    control.update_property([Gtk.AccessibleProperty.LABEL], [title])
    row.add_suffix(control)
    row.set_activatable_widget(control)
    group.add(row)
    return row


def _choice(values):
    return Gtk.DropDown.new_from_strings(list(values))


def _actions(group, apply, cancel):
    buttons = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
    discard = Gtk.Button(label="Cancel")
    commit = Gtk.Button(label="Apply")
    commit.add_css_class("suggested-action")
    discard.connect("clicked", lambda _: cancel())
    commit.connect("clicked", lambda _: apply())
    buttons.append(discard)
    buttons.append(commit)
    group.set_header_suffix(buttons)
    return commit, discard


def _percentage():
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    scale.set_size_request(162, -1)
    scale.set_draw_value(True)
    scale.set_format_value_func(lambda _, value, *unused: f"{value:.0f}%")
    return scale


class CardPage:
    def __init__(self, page, name, window):
        self.host = window.host
        self.notify = window.notify
        self.name = name
        custom = self.host.card(name, custom=True) if name == "ayah" else None
        preset_options = self.host.ayah_preset_options() if name == "ayah" else None
        self.editor = CardEditor(name, self.host.card(name), custom, preset_options)
        self.refreshing = False

        gallery = Adw.PreferencesGroup(title="Themes")
        page.add(gallery)
        self.apply_button, self.cancel_button = _actions(gallery, self.apply, self.cancel)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.tiles = {}
        previous = None
        if name == "ayah":
            ordered = [f"{family} {variant}" for variant in ("A", "B") for family in AYAH_COLUMNS
                       if f"{family} {variant}" in THEMES[name]]
            choices = [(theme, index % 5, index // 5) for index, theme in enumerate((*ordered, "Custom"))]
        else:
            choices = [(theme, index % 3, index // 3) for index, theme in enumerate((*THEMES[name], "Custom"))]
        for theme, column, row in choices:
            tile = Gtk.ToggleButton(hexpand=True)
            tile.update_property([Gtk.AccessibleProperty.LABEL], [theme])
            if previous is not None:
                tile.set_group(previous)
            previous = tile
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            if name == "ayah":
                tile_card = self.editor.custom if theme == "Custom" else theme_preview(name, theme, self.editor.draft)
                miniature = thumbnail(tile_card)
                css = None
            else:
                miniature = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
                miniature.set_size_request(-1, 68)
                css = Gtk.CssProvider()
                miniature.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            title = Gtk.Label(label=theme)
            title.add_css_class("caption")
            content.append(miniature)
            content.append(title)
            tile.set_child(content)
            tile.connect("toggled", self.choose_theme, theme)
            grid.attach(tile, column, row, 1, 1)
            self.tiles[theme] = (tile, miniature, css)
        gallery.add(grid)

        preview = Adw.PreferencesGroup(title="Preview")
        page.add(preview)
        if name == "ayah":
            self.sample = AyahPreview(self.host.element(name))
            preview.add(self.sample.widget)
        else:
            self.sample = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, halign=Gtk.Align.CENTER)
            self.css = Gtk.CssProvider()
            self.sample.get_style_context().add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            preview.add(self.sample)

        group = Adw.PreferencesGroup(title="Appearance")
        if name == "ayah":
            group.set_description("Editing a preset copies its appearance to Custom.")
        page.add(group)
        self.transparency = _percentage()
        if name == "ayah":
            self.transparency.connect("value-changed", lambda control: self.edit(transparency=100 - round(control.get_value())))
            _row(group, "Background opacity", self.transparency)
            self.text_opacity = _percentage()
            self.text_opacity.connect("value-changed", lambda control: self.edit(text_opacity=round(control.get_value())))
            _row(group, "Text opacity", self.text_opacity)
        else:
            self.transparency.connect("value-changed", lambda control: self.edit(transparency=round(control.get_value())))
            _row(group, "Box transparency", self.transparency, "100% leaves the wallpaper visible through the card.")

        self.style = _choice(STYLES)
        _row(group, "Card style", self.style)
        self.style.connect("notify::selected", lambda dropdown, _: self.edit(style=STYLES[dropdown.get_selected()]))

        self.colors = {}
        self.use_preview_colour = Gtk.Button(label="Use preview colour", valign=Gtk.Align.CENTER)
        self.use_preview_colour.connect("clicked", lambda _: self.edit(background=self.editor.draft.background))
        for field, title in (("background", "Background"), ("text", "Text colour"), ("accent", "Frame accent")):
            dialog = Gtk.ColorDialog(with_alpha=False)
            button = Gtk.ColorDialogButton.new(dialog)
            self.colors[field] = button
            row = _row(group, title, button)
            if field == "background":
                row.add_suffix(self.use_preview_colour)
            button.connect("notify::rgba", self.choose_color, field)

        available = {family.get_name() for family in PangoCairo.FontMap.get_default().list_families()}
        theme_fonts = (values[-1] for values in THEMES[name].values())
        available.update(theme_fonts)
        self.fonts = ["", *sorted(available - {""}, key=lambda font: (font.casefold(), font))]
        self.font = _choice(("System font", *self.fonts[1:]))
        self.font.set_enable_search(True)
        _row(group, "English font" if name == "ayah" else "Default font", self.font)
        self.font.connect("notify::selected", lambda dropdown, _: self.edit(font=self.fonts[dropdown.get_selected()]))
        if name == "ayah":
            self.arabic_fonts = ["", *AYAH_SPEC["arabic_fonts"]]
            self.arabic_font = _choice(("Amiri (default)", *self.arabic_fonts[1:]))
            _row(group, "Arabic font", self.arabic_font)
            self.arabic_font.connect("notify::selected",
                                     lambda dropdown, _: self.edit(arabic_font=self.arabic_fonts[dropdown.get_selected()]))

        self.size = Gtk.SpinButton.new_with_range(8, 48, 1)
        self.width = Gtk.SpinButton.new_with_range(
            AYAH_SIZING["min_width"] if name == "ayah" else 360,
            AYAH_SIZING["max_width"] if name == "ayah" else 1000, 10,
        )
        if name == "ayah":
            self.arabic_size = Gtk.SpinButton.new_with_range(AYAH_SIZING["min_size"], AYAH_SIZING["max_arabic_size"], 1)
            self.arabic_size.connect("value-changed", lambda control: self.edit(arabic_size=control.get_value_as_int()))
            _row(group, "Arabic text size", self.arabic_size, "Points")
        _row(group, "English text size" if name == "ayah" else "Base text size", self.size, "Points")
        _row(group, "Box width", self.width, "Pixels")
        self.size.connect("value-changed", lambda control: self.edit(size=control.get_value_as_int()))
        self.width.connect("value-changed", lambda control: self.edit(width=control.get_value_as_int()))
        self.render()

    def choose_theme(self, button, theme):
        if not self.refreshing and button.get_active():
            self.editor.select_theme(theme)
            self.render()

    def choose_color(self, button, _, field):
        rgba = button.get_rgba()
        value = "#" + "".join(f"{round(channel * 255):02x}" for channel in (rgba.red, rgba.green, rgba.blue))
        self.edit(**{field: value})

    def edit(self, **values):
        if self.refreshing:
            return
        try:
            self.editor.edit(**values)
        except ValueError as exc:
            self.notify(str(exc))
        self.render()

    def render(self):
        self.refreshing = True
        try:
            card = self.editor.draft
            for theme, (button, label, css) in self.tiles.items():
                button.set_active(theme == self.editor.theme)
                if css:
                    tile_card = self.editor.custom if theme == "Custom" else theme_preview(self.name, theme, card)
                    self.render_sample(tile_card, label, css, miniature=True)
                elif theme == "Custom":
                    thumbnail(self.editor.custom, overlay=label)
            self.transparency.set_value(100 - card.transparency if self.name == "ayah" else card.transparency)
            self.style.set_selected(STYLES.index(card.style))
            if card.font not in self.fonts:
                self.fonts.append(card.font)
                self.font.get_model().append(card.font)
            self.font.set_selected(self.fonts.index(card.font))
            if self.name == "ayah":
                self.text_opacity.set_value(card.text_opacity)
                if card.arabic_font not in self.arabic_fonts:
                    self.arabic_fonts.append(card.arabic_font)
                    self.arabic_font.get_model().append(card.arabic_font)
                self.arabic_font.set_selected(self.arabic_fonts.index(card.arabic_font))
                self.arabic_size.set_value(card.arabic_size)
            self.size.set_value(card.size)
            self.width.set_value(card.width)
            self.use_preview_colour.set_visible(not card.background_readable)
            for field, button in self.colors.items():
                rgba = Gdk.RGBA()
                rgba.parse(getattr(card, field))
                button.set_rgba(rgba)
            if self.name == "ayah":
                self.sample.render(card)
            else:
                self.render_sample(card, self.sample, self.css)
                self.sample.set_size_request(max(180, min(490, round(card.width / 1.7))), -1)
            self.apply_button.set_sensitive(self.editor.dirty)
            self.cancel_button.set_sensitive(self.editor.dirty)
        finally:
            self.refreshing = False

    def render_sample(self, card, label, css, miniature=False):
        radius, border = CARD_STYLES[card.style]
        # Swatches retain enough fill to identify a palette when the selected card is fully transparent.
        opacity = max(0.82, card.opacity) if miniature else card.opacity
        padding = 5 if miniature else 12
        css.load_from_string(
            f"label {{ background-color: alpha({card.background}, {opacity}); color: {card.text}; "
            f"border: {border}px solid {card.accent}; border-radius: {radius}px; padding: {padding}px; }}"
        )
        now = datetime.now()
        time = "16:40" if miniature else f"{now:%H:%M:%S}"
        size = 20 if miniature else card.size + 16
        date = "Wednesday, 18 November" if miniature else escape(now.strftime("%A, %d %B"))
        content = (
            f'<span size="{size}pt">{time}</span>\n'
            f'<span size="{8 if miniature else card.size}pt">{date}</span>\n'
            f'<span foreground="{card.accent}">━━━━━━━</span>'
            f'<span foreground="{card.accent}" alpha="35%">━━━</span>'
        )
        if not miniature:
            content += '\n<small>Day progress</small>'
        if card.font:
            content = f'<span font_family="{escape(card.font, quote=True)}">{content}</span>'
        label.set_markup(content)

    def apply(self):
        try:
            current = self.host.apply_card(self.name, self.editor.saved, self.editor.changes())
            custom = self.host.card(self.name, custom=True) if self.name == "ayah" and current.theme != "Custom" else None
        except (HostError, ValueError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.editor.mark_saved(current, custom)
        self.render()
        self.notify("Appearance saved")

    def cancel(self):
        try:
            custom = self.host.card(self.name, custom=True) if self.name == "ayah" else None
            options = self.host.ayah_preset_options() if self.name == "ayah" else None
            self.editor.cancel(self.host.card(self.name), custom, options)
        except (HostError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.render()


class PlacementPage:
    def __init__(self, page, window, names):
        self.host = window.host
        self.notify = window.notify
        self.names = names
        self.displays = []
        self.loading = False
        self.saved = None
        self.position = None

        group = Adw.PreferencesGroup(title="Desktop placement",
                                     description="Choose the display and anchor for each widget.")
        page.add(group)
        self.apply_button, self.cancel_button = _actions(group, self.apply, self.refresh)
        self.widget = _choice(WIDGETS[name] for name in names)
        self.monitor = Gtk.DropDown()
        self.widget.connect("notify::selected", lambda *_: self.refresh())
        self.monitor.connect("notify::selected", lambda *_: self.update_buttons())
        _row(group, "Widget", self.widget)
        _row(group, "Display", self.monitor)
        self.description = Gtk.Label(wrap=True, xalign=0)
        self.description.add_css_class("dim-label")
        group.add(self.description)

        self.grid = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True,
                             margin_top=12, margin_bottom=6)
        self.anchors = {}
        previous = None
        for index, (position, arrow) in enumerate(zip(ANCHORS, ("↖", "↑", "↗", "←", "•", "→", "↙", "↓", "↘"), strict=True)):
            button = Gtk.ToggleButton(label=arrow, tooltip_text=position)
            button.update_property([Gtk.AccessibleProperty.LABEL], [position])
            if previous is not None:
                button.set_group(previous)
            previous = button
            button.connect("toggled", self.select_anchor, position)
            self.grid.attach(button, index % 3, index // 3, 1, 1)
            self.anchors[position] = button
        group.add(self.grid)
        self.update_buttons()

    def refresh(self):
        self.loading = True
        try:
            index = self.widget.get_selected()
            self.displays = self.host.displays() if index < len(self.names) else []
            self.monitor.set_model(Gtk.StringList.new([label for _, label, _ in self.displays]))
            self.monitor.set_selected(Gtk.INVALID_LIST_POSITION)
            self.saved = None
            if self.displays:
                self.saved = self.host.position(self.names[index], self.displays)
                self.position = self.saved[1]
                self.anchors[self.position].set_active(True)
                for position, (key, _, _) in enumerate(self.displays):
                    if key == self.saved[0]:
                        self.monitor.set_selected(position)
                        break
            message = "Choose a display and an anchor." if self.displays else "No live displays are available."
        except (HostError, GLib.Error) as exc:
            self.displays = []
            self.monitor.set_model(None)
            message = str(exc)
        finally:
            self.loading = False
        self.description.set_label(message)
        self.grid.set_sensitive(bool(self.displays))
        self.update_buttons()

    def select_anchor(self, button, position):
        if not self.loading and button.get_active():
            self.position = position
            self.update_buttons()

    def update_buttons(self):
        selected = self.monitor.get_selected()
        valid = selected < len(self.displays)
        dirty = valid and (self.displays[selected][0], self.position) != self.saved
        self.apply_button.set_sensitive(bool(dirty and self.position))
        self.cancel_button.set_sensitive(bool(self.displays))

    def apply(self):
        widget = self.names[self.widget.get_selected()]
        display = self.displays[self.monitor.get_selected()][0]
        try:
            self.host.place(widget, display, self.position)
        except (HostError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.refresh()
        self.notify("Placement saved")


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, application, host, host_message):
        super().__init__(application=application, title="Desktop Widgets", default_width=940, default_height=720)
        self.set_size_request(SETTINGS_MIN_WIDTH, -1)
        self.host = host
        self.switches = {}
        self.toast = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        toolbar.set_content(content)
        self.toast.set_child(toolbar)
        self.set_content(self.toast)

        status = Adw.Banner(title=host_message, revealed=True)
        if host is None:
            status.set_button_label("Desktop Widgets extension")
            status.connect("button-clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(EXTENSIONS_URL, None))
        content.append(status)

        pane = Gtk.Box(hexpand=True, vexpand=True)
        stack = Gtk.Stack(hexpand=True, vexpand=True)
        sidebar = Gtk.StackSidebar(stack=stack, width_request=156)
        pane.append(sidebar)
        pane.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        pane.append(stack)
        content.append(pane)

        try:
            visible = host.visibility() if host else {}
        except (HostError, GLib.Error) as exc:
            status.set_title(str(exc))
            visible = {}
        for name, title in WIDGETS.items():
            page = Adw.PreferencesPage()
            stack.add_titled(page, name, title)
            general = Adw.PreferencesGroup(title=title)
            page.add(general)
            if name not in visible:
                general.set_description("This widget becomes available once it is configured in the project’s GNOME desktop setup.")
                continue
            switch = Gtk.Switch(active=visible[name])
            handler = switch.connect("notify::active", self.set_visibility, name)
            switch.visibility_handler = handler
            self.switches[name] = switch
            _row(general, "Show on desktop", switch)
            if name == "avatar":
                general.set_description("The avatar can stand on the clock when both are on the same display.")
            else:
                try:
                    CardPage(page, name, self)
                except (HostError, GLib.Error) as exc:
                    general.set_description(str(exc))

        names = [name for name in WIDGETS if name in visible]
        page = Adw.PreferencesPage()
        stack.add_titled(page, "placement", "Placement")
        if names:
            placement = PlacementPage(page, self, names)
            stack.connect("notify::visible-child-name", lambda *_: placement.refresh()
                          if stack.get_visible_child_name() == "placement" and not placement.displays else None)
        else:
            page.add(Adw.PreferencesGroup(title="Desktop placement",
                                          description="Configure a widget to choose its display and position."))
        if host and self.switches:
            disconnect = host.watch_visibility(self.refresh_switches)
            self.connect("close-request", lambda _: disconnect() or False)
            self.refresh_switches()

    def refresh_switches(self, *_):
        try:
            states = self.host.visibility()
        except (HostError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        for name, switch in self.switches.items():
            with switch.handler_block(switch.visibility_handler):
                switch.set_active(states.get(name, False))

    def notify(self, message):
        self.toast.add_toast(Adw.Toast(title=message))

    def set_visibility(self, switch, _, name):
        try:
            self.host.set_visible(name, switch.get_active())
        except (HostError, GLib.Error) as exc:
            with switch.handler_block(switch.visibility_handler):
                switch.set_active(not switch.get_active())
            self.notify(str(exc))


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.session = Session.discover()
        if self.session:
            self.session.watch_stopped(self.quit)

    def do_activate(self):
        if window := self.get_active_window():
            window.present()
            return
        try:
            host = AzClockHost.discover()
            message = host.status()
        except (HostError, GLib.Error) as exc:
            host = None
            message = str(exc)
        window = SettingsWindow(self, host, message)
        if self.session:
            try:
                self.session.reopen()
            except (HostError, GLib.Error, OSError, subprocess.SubprocessError) as exc:
                window.notify(str(exc))
        window.present()


def main():
    parser = argparse.ArgumentParser(prog="desktop-widget-settings", description="Manage Ayah, Clock and Avatar on GNOME.")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--install-gnome-integration", action="store_true",
                         help="back up AzClock and install the shared widget bridge and avatar")
    actions.add_argument("--set-widget", nargs=2, help=argparse.SUPPRESS)
    actions.add_argument("--quit-widgets", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if any(vars(options).values()):
        try:
            if options.install_gnome_integration:
                install_bridge()
            elif options.set_widget:
                widget, flag = options.set_widget
                if widget not in WIDGETS or flag not in ("on", "off"):
                    parser.error("Choose a configured widget and on or off.")
                AzClockHost.discover().set_visible(widget, flag == "on")
            else:
                session = Session.discover()
                if not session:
                    raise HostError("The Desktop Widgets session settings schema is missing.")
                session.quit()
        except (HostError, OSError, ValueError, GLib.Error, subprocess.SubprocessError) as exc:
            parser.exit(1, f"{exc}\n")
        return 0
    if Gdk.Display.get_default() is None:
        raise SystemExit("Open Desktop Widget Settings from a graphical GNOME session.")
    return Application().run()


if __name__ == "__main__":
    raise SystemExit(main())
