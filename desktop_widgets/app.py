"""Native settings for the three desktop widgets."""

import argparse
from dataclasses import replace
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
from .settings import (
    CLOCK_FACES, STYLES, THEMES, THEME_FAMILIES, WIDGETS,
    Card, CardEditor, custom_preview, fit_card_dimensions, theme_preview,
)
from .widgets.ayah.preview import AyahPreview
from .widgets.ayah.themes import PRESETS as AYAH_PRESETS
from .widgets.ayah.themes import SIZING as AYAH_SIZING
from .widgets.ayah.themes import SPEC as AYAH_SPEC

from .widgets.clock.preview import ClockPreview
from .widgets.clock.themes import DESIGNS

EXTENSIONS_URL = "https://extensions.gnome.org/extension/5156/desktop-clock/"
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


def _toggle_group(parent, labels, changed):
    row = Gtk.Box(halign=Gtk.Align.CENTER)
    row.add_css_class("linked")
    buttons = {}
    for key, label in labels.items():
        button = Gtk.ToggleButton(label=label)
        if buttons:
            button.set_group(next(iter(buttons.values())))
        button.connect("toggled", lambda item: changed() if item.get_active() else None)
        row.append(button)
        buttons[key] = button
    parent.append(row)
    return buttons


class CardPage:
    def __init__(self, page, name, window):
        self.host = window.host
        self.window = window
        self.notify = window.notify
        self.name = name
        custom = self.host.card(name, custom=True)
        preset_options = self.host.ayah_preset_options() if name == "ayah" else None
        self.editor = CardEditor(name, self.host.card(name), custom, preset_options)
        self.refreshing = False

        if name == "clock":
            faces = Adw.PreferencesGroup(title="Clock face")
            page.add(faces)
            tiles = Gtk.Box(spacing=10, homogeneous=True, halign=Gtk.Align.CENTER)
            faces.add(tiles)
            self.face_tiles = {}
            for face, title in CLOCK_FACES.items():
                tile = Gtk.ToggleButton()
                tile.update_property([Gtk.AccessibleProperty.LABEL], [title])
                if self.face_tiles:
                    tile.set_group(self.face_tiles["en"][0])
                content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                sample = ClockPreview(238)
                content.append(sample.widget)
                content.append(Gtk.Label(label=title))
                tile.set_child(content)
                tile.connect("toggled", lambda item, value=face: self.edit(face=value) if item.get_active() else None)
                tiles.append(tile)
                self.face_tiles[face] = (tile, sample)

        themes = Adw.PreferencesGroup(title="Theme")
        page.add(themes)
        self.apply_button, self.cancel_button = _actions(themes, self.apply, self.cancel)
        self.themes = _choice(())
        self.themes.connect("notify::selected", self.choose_theme)
        self.theme_row = _row(themes, "Theme for this widget", self.themes)
        save = Gtk.Button(label="Save as Custom")
        save.set_sensitive(self.host.has_theme_library)
        save.connect("clicked", self.save_theme)
        _row(themes, "Add this appearance to Themes", save)

        preview = Adw.PreferencesGroup(title="Preview")
        page.add(preview)
        self.sample = AyahPreview(self.host.element(name)) if name == "ayah" else ClockPreview()
        preview.add(self.sample.widget)

        group = Adw.PreferencesGroup(title="Appearance")
        group.set_description("Edits create a custom appearance for this widget.")
        page.add(group)
        self.transparency = _percentage()
        self.transparency.connect("value-changed", lambda control: self.edit(transparency=100 - round(control.get_value())))
        _row(group, "Background and artwork opacity", self.transparency)
        self.text_opacity = _percentage()
        self.text_opacity.connect("value-changed", lambda control: self.edit(text_opacity=round(control.get_value())))
        _row(group, "Text opacity", self.text_opacity)

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
        theme_fonts = (preset["font"] for preset in THEMES[name].values())
        available.update(theme_fonts)
        self.fonts = ["", *sorted(available - {""}, key=lambda font: (font.casefold(), font))]
        self.font = _choice(("System font", *self.fonts[1:]))
        self.font.set_enable_search(True)
        _row(group, "English font", self.font)
        self.font.connect("notify::selected", lambda dropdown, _: self.edit(font=self.fonts[dropdown.get_selected()]))
        self.arabic_fonts = ["", *AYAH_SPEC["arabic_fonts"]]
        self.arabic_font = _choice(("Theme default", *self.arabic_fonts[1:]))
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
        self.refresh_themes()

    def refresh_themes(self):
        self.library = self.host.custom_themes()
        self.theme_names = ["Custom", *THEMES[self.name], *self.library]
        labels = [f"{theme} A" if self.name == "clock" and theme in THEME_FAMILIES else theme
                  for theme in self.theme_names]
        self.refreshing = True
        self.themes.set_model(Gtk.StringList.new(labels))
        self.refreshing = False
        self.render()

    def choose_theme(self, dropdown, _):
        if not self.refreshing and dropdown.get_selected() < len(self.theme_names):
            self.select_theme(self.theme_names[dropdown.get_selected()])

    def select_theme(self, theme):
        try:
            if theme in self.library:
                self.editor.select_custom(theme, self.library[theme])
            else:
                self.editor.select_theme(theme)
        except ValueError as exc:
            self.notify(str(exc))
        self.render()

    def save_theme(self, _):
        dialog = Adw.MessageDialog(
            transient_for=self.window, heading="Save a custom theme",
            body="Your theme will be available to both the Clock and Ayah reminder.",
        )
        entry = Gtk.Entry(placeholder_text="Theme name", activates_default=True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def save(_dialog, response):
            if response != "save":
                return
            try:
                name = self.host.save_custom_theme(entry.get_text(), self.name, self.editor.draft)
            except (HostError, ValueError, GLib.Error) as exc:
                self.notify(str(exc))
                return
            for page in self.window.cards.values():
                page.refresh_themes()
            self.select_theme(name)
            self.notify(f"Saved {name} to Themes")

        dialog.connect("response", save)
        dialog.present()
        entry.grab_focus()

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
            selected = card.custom_name if card.custom_name in self.library else self.editor.theme
            self.themes.set_selected(self.theme_names.index(selected) if selected in self.theme_names else 0)
            if self.name == "clock":
                for face, (tile, preview) in self.face_tiles.items():
                    tile.set_active(card.face == face)
                    preview.render(replace(card, face=face))
            design = DESIGNS.get(card.clock_design)
            if self.name == "clock" and design:
                self.theme_row.set_subtitle(design["story"])
            self.transparency.set_value(100 - card.transparency)
            self.text_opacity.set_value(card.text_opacity)
            self.style.set_selected(STYLES.index(card.style))
            if card.font not in self.fonts:
                self.fonts.append(card.font)
                self.font.get_model().append(card.font)
            self.font.set_selected(self.fonts.index(card.font))
            if card.arabic_font not in self.arabic_fonts:
                self.arabic_fonts.append(card.arabic_font)
                self.arabic_font.get_model().append(card.arabic_font)
            self.arabic_font.set_selected(self.arabic_fonts.index(card.arabic_font))
            if self.name == "ayah":
                self.arabic_size.set_value(card.arabic_size)
            self.size.set_value(card.size)
            self.width.set_value(card.width)
            self.use_preview_colour.set_visible(not card.background_readable)
            for field, button in self.colors.items():
                rgba = Gdk.RGBA()
                rgba.parse(getattr(card, field))
                button.set_rgba(rgba)
            self.sample.render(card)
            self.apply_button.set_sensitive(self.editor.dirty)
            self.cancel_button.set_sensitive(self.editor.dirty)
        finally:
            self.refreshing = False

    def apply(self):
        try:
            current = self.host.apply_card(self.name, self.editor.saved, self.editor.changes())
            custom = self.host.card(self.name, custom=True) if current.theme != "Custom" else None
        except (HostError, ValueError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.editor.mark_saved(current, custom)
        self.render()
        self.notify("Appearance saved")

    def cancel(self):
        try:
            custom = self.host.card(self.name, custom=True)
            options = self.host.ayah_preset_options() if self.name == "ayah" else None
            self.editor.cancel(self.host.card(self.name), custom, options)
        except (HostError, GLib.Error) as exc:
            self.notify(str(exc))
            return
        self.render()


class ThemesPage:
    def __init__(self, page, window):
        self.window = window
        self.group = Adw.PreferencesGroup(title="Theme library")
        page.add(self.group)
        self.rows = []

    def refresh(self):
        for row in self.rows:
            self.group.remove(row)
        self.rows.clear()
        for family in THEME_FAMILIES:
            self.add_theme(family, DESIGNS[family]["family_story"])
        if self.window.host:
            for name, snapshot in self.window.host.custom_themes().items():
                self.add_theme(name, f"Saved from {WIDGETS[snapshot['widget']]}", snapshot)

    def add_theme(self, name, story, snapshot=None):
        row = Adw.ActionRow(title=name, subtitle=story, activatable=True, use_markup=False)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda _: ThemeWindow(self.window, name, snapshot).present())
        self.group.add(row)
        self.rows.append(row)


class ThemeWindow(Adw.Window):
    def __init__(self, owner, name, snapshot):
        super().__init__(transient_for=owner, modal=True, title=name, default_width=1020, default_height=580)
        self.owner = owner
        self.name = name
        self.snapshot = snapshot
        self.saved = {widget: page.host.card(widget) for widget, page in owner.cards.items()}
        initial = self.saved.get("clock") or self.saved.get("ayah") or Card()
        if snapshot:
            initial = custom_preview(snapshot["widget"], snapshot, initial)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=name))
        toolbar.add_top_bar(header)
        self.set_content(toolbar)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_top=16, margin_bottom=16,
                       margin_start=20, margin_end=20)
        scroll = Gtk.ScrolledWindow(child=body, hscrollbar_policy=Gtk.PolicyType.NEVER)
        toolbar.set_content(scroll)

        targets = {"both": "Both", "clock": "Clock", "ayah": "Ayah"}
        self.targets = _toggle_group(body, targets, self.render)
        self.targets["both"].set_active(True)
        self.variants = {}
        if not snapshot:
            self.variants = _toggle_group(body, {0: "Variant A", 1: "Variant B"}, self.render)
            self.variants[0].set_active(True)

        previews = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, row_spacing=12, column_spacing=12,
                               min_children_per_line=1, max_children_per_line=3, homogeneous=True,
                               halign=Gtk.Align.CENTER, valign=Gtk.Align.START)
        body.append(previews)
        self.panels = {}
        for key, title, sample in (
            ("ayah", WIDGETS["ayah"], AyahPreview(width=294)),
            ("en", "English clock", ClockPreview(294)),
            ("ar", "الساعة بالعربية", ClockPreview(294)),
        ):
            panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.START)
            heading = Gtk.Label(label=title, wrap=True)
            heading.set_size_request(-1, 30)
            heading.add_css_class("heading")
            panel.append(heading)
            panel.append(sample.widget)
            story = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
            story.add_css_class("dim-label")
            panel.append(story)
            previews.append(panel)
            self.panels[key] = (sample, story, panel.get_parent())

        controls = Adw.PreferencesGroup(title="Opacity", halign=Gtk.Align.CENTER)
        controls.set_size_request(570, -1)
        body.append(controls)
        self.background = _percentage()
        self.background.set_value(100 - initial.transparency)
        _row(controls, "Background and artwork", self.background)
        self.text = _percentage()
        self.text.set_value(initial.text_opacity)
        _row(controls, "Text", self.text)
        for scale in (self.background, self.text):
            scale.connect("value-changed", lambda _: self.render())

        self.apply_button = Gtk.Button(label="Apply theme")
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", self.apply)
        header.pack_end(self.apply_button)
        self.error = Gtk.Label(wrap=True, xalign=0)
        self.error.add_css_class("error")
        body.append(self.error)
        self.render()

    def selection(self):
        target = next((key for key, button in self.targets.items() if button.get_active()), "both")
        return ("ayah", "clock") if target == "both" else (target,)

    def card(self, widget):
        base = self.saved.get(widget, Card())
        if self.snapshot:
            card = replace(custom_preview(widget, self.snapshot, base), custom_name=self.name)
        else:
            variant = int(self.variants[1].get_active())
            name = THEME_FAMILIES[self.name][widget][variant]
            card = theme_preview(widget, name, base)
        return fit_card_dimensions(replace(card, transparency=100 - round(self.background.get_value()),
                                           text_opacity=round(self.text.get_value())))

    def render(self):
        if not hasattr(self, "text"):
            return
        widgets = self.selection()
        self.apply_button.set_sensitive(all(widget in self.saved for widget in widgets))
        self.error.set_label("")
        for key, (preview, story, panel) in self.panels.items():
            widget = "ayah" if key == "ayah" else "clock"
            panel.set_visible(widget in widgets)
            if widget not in widgets:
                continue
            card = self.card(widget)
            if widget == "clock":
                card = replace(card, face=key)
                description = DESIGNS[card.clock_design]["story"]
            else:
                description = AYAH_PRESETS.get(card.art_theme, {}).get("story", "")
            preview.render(card)
            story.set_label(description)

    def apply(self, _):
        updates = {}
        for widget in self.selection():
            editor = CardEditor(widget, self.saved[widget])
            editor.draft = self.card(widget)
            updates[widget] = (editor.saved, editor.changes())
        try:
            applied = self.owner.host.apply_cards(updates)
        except (HostError, ValueError, GLib.Error) as exc:
            self.error.set_label(str(exc))
            return
        for widget, card in applied.items():
            page = self.owner.cards[widget]
            options = self.owner.host.ayah_preset_options() if widget == "ayah" else None
            page.editor.cancel(card, self.owner.host.card(widget, custom=True), options)
            page.refresh_themes()
        self.owner.notify(f"Applied {self.name}")
        self.close()


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
        super().__init__(application=application, title="Desktop Widgets", default_width=940, default_height=800)
        self.set_size_request(SETTINGS_MIN_WIDTH, -1)
        self.host = host
        self.switches = {}
        self.cards = {}
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
        self.stack = stack
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
                    self.cards[name] = CardPage(page, name, self)
                except (HostError, GLib.Error) as exc:
                    general.set_description(str(exc))

        page = Adw.PreferencesPage()
        stack.add_titled(page, "themes", "Themes")
        self.themes_page = ThemesPage(page, self)
        stack.connect("notify::visible-child-name", lambda *_: self.themes_page.refresh()
                      if stack.get_visible_child_name() == "themes" else None)

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
