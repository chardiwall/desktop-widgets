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

from .gnome import ANCHORS, AzClockHost, HostError
from .integration import install_attachments
from .session import APP_ID, MODE, Session
from .settings import CardEditor, STYLES, THEMES, WIDGETS, theme_preview

EXTENSIONS_URL = "https://extensions.gnome.org/extension/5156/desktop-clock/"
FONTS = ("Ubuntu Sans", "Noto Sans", "Noto Serif", "DejaVu Sans Mono", "Amiri", "Noto Naskh Arabic")


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


class CardPage:
    def __init__(self, page, name, window):
        self.host = window.host
        self.notify = window.notify
        self.name = name
        self.editor = CardEditor(name, self.host.card(name))
        self.refreshing = False

        gallery = Adw.PreferencesGroup(title="Themes")
        page.add(gallery)
        self.apply_button, self.cancel_button = _actions(gallery, self.apply, self.cancel)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.tiles = {}
        previous = None
        for index, theme in enumerate((*THEMES[name], "Custom")):
            tile = Gtk.ToggleButton(hexpand=True)
            tile.update_property([Gtk.AccessibleProperty.LABEL], [theme])
            if previous is not None:
                tile.set_group(previous)
            previous = tile
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            miniature = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
            miniature.set_size_request(-1, 68)
            title = Gtk.Label(label=theme)
            title.add_css_class("caption")
            content.append(miniature)
            content.append(title)
            tile.set_child(content)
            css = Gtk.CssProvider()
            miniature.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            tile.connect("toggled", self.choose_theme, theme)
            grid.attach(tile, index % 3, index // 3, 1, 1)
            self.tiles[theme] = (tile, miniature, css)
        gallery.add(grid)

        preview = Adw.PreferencesGroup(title="Preview")
        page.add(preview)
        self.sample = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, halign=Gtk.Align.CENTER)
        self.css = Gtk.CssProvider()
        self.sample.get_style_context().add_provider(self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        preview.add(self.sample)

        group = Adw.PreferencesGroup(title="Appearance")
        page.add(group)
        self.transparency = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.transparency.set_size_request(162, -1)
        self.transparency.set_draw_value(True)
        self.transparency.set_format_value_func(lambda _, value, *unused: f"{value:.0f}%")
        self.transparency.connect("value-changed", lambda control: self.edit(transparency=round(control.get_value())))
        _row(group, "Box transparency", self.transparency, "100% leaves the wallpaper visible through the card.")

        self.style = _choice(STYLES)
        _row(group, "Card style", self.style)
        self.style.connect("notify::selected", lambda dropdown, _: self.edit(style=STYLES[dropdown.get_selected()]))

        self.colors = {}
        for field, title in (("background", "Background"), ("text", "Text colour"), ("accent", "Frame accent")):
            dialog = Gtk.ColorDialog(with_alpha=False)
            button = Gtk.ColorDialogButton.new(dialog)
            self.colors[field] = button
            _row(group, title, button)
            button.connect("notify::rgba", self.choose_color, field)

        available = {family.get_name() for family in PangoCairo.FontMap.get_default().list_families()}
        theme_fonts = (values[-1] for values in THEMES[name].values())
        self.fonts = tuple(dict.fromkeys(("", self.editor.saved.font, *theme_fonts,
                                         *(font for font in FONTS if font in available))))
        self.font = _choice(("System font", *self.fonts[1:]))
        _row(group, "Default font", self.font, "The renderer can specify fonts for individual lines.")
        self.font.connect("notify::selected", lambda dropdown, _: self.edit(font=self.fonts[dropdown.get_selected()]))

        self.size = Gtk.SpinButton.new_with_range(8, 48, 1)
        self.width = Gtk.SpinButton.new_with_range(360, 1000, 10)
        _row(group, "Base text size", self.size, "Points")
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
                tile_card = self.editor.custom if theme == "Custom" else theme_preview(self.name, theme, card)
                self.render_sample(tile_card, label, css, miniature=True)
            self.transparency.set_value(card.transparency)
            self.style.set_selected(STYLES.index(card.style))
            self.font.set_selected(self.fonts.index(card.font) if card.font in self.fonts else 0)
            self.size.set_value(card.size)
            self.width.set_value(card.width)
            for field, button in self.colors.items():
                rgba = Gdk.RGBA()
                rgba.parse(getattr(card, field))
                button.set_rgba(rgba)
            self.render_sample(card, self.sample, self.css)
            self.sample.set_size_request(max(180, min(490, round(card.width / 1.7))), -1)
            self.apply_button.set_sensitive(self.editor.dirty)
            self.cancel_button.set_sensitive(self.editor.dirty)
        finally:
            self.refreshing = False

    def render_sample(self, card, label, css, miniature=False):
        radius = {"Glass": 13, "Solid": 8, "Minimal": 4}[card.style]
        border = 1 if card.style != "Minimal" else 0
        opacity = (100 - card.transparency) / 100
        # Swatches retain enough fill to identify a palette when the selected card is fully transparent.
        swatch_opacity = max(0.82, opacity) if miniature else opacity
        padding = 5 if miniature else 12
        css.load_from_string(
            f"label {{ background-color: alpha({card.background}, {swatch_opacity}); color: {card.text}; "
            f"border: {border}px solid {card.accent}; border-radius: {radius}px; padding: {padding}px; }}"
        )
        font = escape(card.font or "Sans", quote=True)
        if self.name == "ayah":
            arabic_size = 12 if miniature else card.size + 9
            translation_size = 8 if miniature else card.size
            content = (
                f'<span font_family="Amiri, Noto Naskh Arabic" size="{arabic_size}pt">'
                'فَإِنَّ مَعَ الْعُسْرِ يُسْرًا</span>\n'
                f'<span foreground="{card.accent}">━━━━</span>\n'
                f'<span size="{translation_size}pt">Indeed, with hardship comes ease.</span>'
            )
            if not miniature:
                content += '\n<small>Ash-Sharh · 94:5</small>'
        else:
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
        label.set_markup(f'<span font_family="{font}">{content}</span>')

    def apply(self):
        try:
            current = self.host.apply_card(self.name, self.editor.saved, self.editor.changes())
        except (HostError, ValueError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.editor.mark_saved(current)
        self.render()
        self.notify("Appearance saved")

    def cancel(self):
        try:
            self.editor.cancel(self.host.card(self.name))
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
                                     description="Adjust the monitor and anchor for each card.")
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
        super().__init__(application=application, title="Desktop Widgets", default_width=860, default_height=660)
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
                general.set_description("The avatar follows the clock when it is visible.")
            else:
                if name == "ayah" and (cord_visible := host.cord_visible()) is not None:
                    cord = Adw.PreferencesGroup(title="Pull cord")
                    page.add(cord)
                    toggle = Gtk.Switch(active=cord_visible)
                    handler = toggle.connect("notify::active", self.set_visibility, "cord")
                    toggle.visibility_handler = handler
                    self.switches["cord"] = toggle
                    _row(cord, "Show line and switch", toggle, "Shows both parts below the Ayah card.")
                try:
                    CardPage(page, name, self)
                except (HostError, GLib.Error) as exc:
                    general.set_description(str(exc))

        names = [name for name in ("ayah", "clock") if name in visible]
        page = Adw.PreferencesPage()
        stack.add_titled(page, "placement", "Placement")
        if names:
            placement = PlacementPage(page, self, names)
            stack.connect("notify::visible-child-name", lambda *_: placement.refresh()
                          if stack.get_visible_child_name() == "placement" and not placement.displays else None)
        else:
            page.add(Adw.PreferencesGroup(title="Desktop placement",
                                          description="Configure an Ayah or Clock card to choose its display and position."))
        if host and self.switches:
            handler = host.root.connect("changed::widgets", self.refresh_switches)
            self.connect("close-request", lambda _: host.root.disconnect(handler) or False)
            self.refresh_switches()

    def refresh_switches(self, *_):
        try:
            states = self.host.visibility()
            if "cord" in self.switches:
                states["cord"] = self.host.cord_visible() is True
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
            if name == "cord":
                self.host.set_cord_visible(switch.get_active())
            else:
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
            self.session.settings.connect("changed::" + MODE, self.on_mode)

    def on_mode(self, settings, _):
        if settings.get_string(MODE) == "stopped":
            self.quit()

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
                         help="back up AzClock and install the widget attachment hooks")
    actions.add_argument("--toggle-pull-cord", action="store_true", help=argparse.SUPPRESS)
    actions.add_argument("--set-widget", nargs=2, help=argparse.SUPPRESS)
    actions.add_argument("--quit-widgets", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if any(vars(options).values()):
        try:
            if options.install_gnome_integration:
                install_attachments()
            elif options.toggle_pull_cord:
                AzClockHost.discover().toggle_light()
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
