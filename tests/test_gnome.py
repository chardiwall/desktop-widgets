import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from gi.repository import Gio, GLib

from desktop_widgets.bridge.gnome import AzClockHost, HostError
from desktop_widgets.settings import CardEditor

SCHEMA = """<schemalist>
  <schema id="org.gnome.shell.extensions.azclock" path="/org/gnome/shell/extensions/azclock/">
    <key name="widgets" type="aa{sv}"><default>[]</default></key>
  </schema>
  <schema id="org.gnome.shell.extensions.azclock.widget-data">
    <key name="elements" type="aa{sv}"><default>[]</default></key>
    <key name="background-color" type="s"><default>'rgba(57,51,62,0.55)'</default></key>
    <key name="show-background" type="b"><default>true</default></key>
    <key name="show-border" type="b"><default>true</default></key>
    <key name="border-radius" type="i"><default>18</default></key>
    <key name="anchor-point" type="s"><default>'Top_Left'</default></key>
    <key name="location-data" type="s"><default>'{"monitorIndex":0,"relativeX":0.03,"relativeY":0.05}'</default></key>
    <key name="convert-old-location-done" type="b"><default>false</default></key>
    <key name="lock-widget" type="b"><default>true</default></key>
  </schema>
  <schema id="org.gnome.shell.extensions.azclock.element-data">
    <key name="background-color" type="s"><default>'rgba(0,0,0,0); width: 600px'</default></key>
    <key name="show-background" type="b"><default>true</default></key>
    <key name="border-color" type="s"><default>'#e6b866'</default></key>
    <key name="foreground-color" type="s"><default>'#fff4e8'</default></key>
    <key name="font-family-override" type="(bs)"><default>(true, 'Ubuntu Sans')</default></key>
    <key name="font-size" type="i"><default>14</default></key>
    <key name="image-path" type="s"><default>''</default></key>
    <key name="command" type="s"><default>'clock-card'</default></key>
  </schema>
</schemalist>"""


def entry(name, enabled=True, **metadata):
    return {name: GLib.Variant("a{sv}", {"enabled": GLib.Variant("b", enabled), **metadata})}


class AzClockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        directory = Path(cls.directory.name)
        (directory / "azclock.gschema.xml").write_text(SCHEMA)
        subprocess.run(["glib-compile-schemas", "--strict", directory], check=True)
        cls.source = Gio.SettingsSchemaSource.new_from_directory(str(directory), None, False)

    def setUp(self):
        self.host = AzClockHost(self.source, Gio.memory_settings_backend_new())
        self.entries = [
            entry("avatar"), entry("clock", position=GLib.Variant("u", 7)),
            entry("ayah"), entry("another-widget", detail=GLib.Variant("s", "unrelated widget")),
        ]
        self.host.root.set_value("widgets", GLib.Variant("aa{sv}", self.entries))
        for widget, element in (("avatar", "body"), ("clock", "card"), ("ayah", "verse")):
            self.host.widget(widget).set_value("elements", GLib.Variant("aa{sv}", [entry(element)]))

    def test_turning_off_clock_preserves_order_and_unrelated_settings(self):
        self.host.set_visible("clock", False)

        expected = list(self.entries)
        expected[1] = entry("clock", False, position=GLib.Variant("u", 7))
        actual = self.host.root.get_value("widgets")
        self.assertEqual(actual.unpack(), GLib.Variant("aa{sv}", expected).unpack())
        self.assertEqual(actual.get_child_value(1).lookup_value("clock", None).lookup_value("position", None).get_type_string(), "u")
        self.assertEqual(self.host.visibility(), {"ayah": True, "clock": False, "avatar": True})

        self.host.set_visible("clock", True)
        self.assertEqual(self.host.root.get_value("widgets").unpack(), GLib.Variant("aa{sv}", self.entries).unpack())

    def test_unconfigured_widget_is_not_created_by_a_toggle(self):
        self.host.widget("avatar").reset("elements")
        self.assertNotIn("avatar", self.host.visibility())
        with self.assertRaisesRegex(HostError, "not configured"):
            self.host.set_visible("avatar", False)
        self.assertEqual(self.host.root.get_value("widgets"), GLib.Variant("aa{sv}", self.entries))

    def test_card_edits_preserve_existing_renderer_and_other_widgets(self):
        ayah = self.host.card("ayah")
        saved = self.host.card("clock")
        self.host.apply_card("clock", saved, {"style": "Solid", "background": "#442b45", "width": 710})

        card = self.host.card("clock")
        self.assertEqual((card.style, card.background, card.width), ("Solid", "#442b45", 710))
        self.assertEqual(self.host.element("clock").get_string("command"), "clock-card")
        self.assertEqual(self.host.card("ayah"), ayah)
        self.assertEqual(self.host.visibility(), {"ayah": True, "clock": True, "avatar": True})

    def test_applying_a_stale_colour_keeps_the_newer_native_setting(self):
        saved = self.host.card("clock")
        self.host.element("clock").set_string("foreground-color", "#ffffff")

        with self.assertRaisesRegex(HostError, "changed"):
            self.host.apply_card("clock", saved, {"text": "#c28369"})
        self.assertEqual(self.host.card("clock").text, "#ffffff")

    def test_placement_re_resolves_a_selected_display_after_reordering(self):
        self.host.displays = lambda: [("DP-2", "Wide", 0), ("HDMI-1", "Side", 1)]
        self.host.place("ayah", "HDMI-1", "Top right")
        location = self.host.widget("ayah").get_string("location-data")
        self.assertEqual(json.loads(location), {"monitorIndex": 1, "relativeX": 0.96, "relativeY": 0.06})
        self.assertTrue(self.host.widget("ayah").get_boolean("convert-old-location-done"))
        self.assertEqual(self.host.position("ayah", self.host.displays()), ("HDMI-1", "Top right"))

        self.host.displays = lambda: [("HDMI-1", "Side", 0), ("DP-2", "Wide", 1)]
        self.host.place("ayah", "HDMI-1", "Bottom right")
        self.assertEqual(json.loads(self.host.widget("ayah").get_string("location-data"))["monitorIndex"], 0)

    def test_disconnected_target_leaves_current_placement_unchanged(self):
        saved = self.host.widget("clock").get_string("location-data")
        self.host.displays = lambda: [("DP-2", "Wide", 0)]
        with self.assertRaisesRegex(HostError, "disconnected"):
            self.host.place("clock", "HDMI-1", "Top right")
        self.assertEqual(self.host.widget("clock").get_string("location-data"), saved)

    def test_changing_only_display_preserves_the_existing_anchor_offset(self):
        self.host.displays = lambda: [("DP-2", "Wide", 0), ("HDMI-1", "Side", 1)]
        self.host.place("ayah", "HDMI-1", "Top left")
        location = json.loads(self.host.widget("ayah").get_string("location-data"))
        self.assertEqual(location, {"monitorIndex": 1, "relativeX": 0.03, "relativeY": 0.05})

    def test_changing_width_keeps_the_existing_element_background(self):
        label = self.host.element("ayah")
        label.set_string("background-color", "#334455; width: 600px")
        self.host.apply_card("ayah", self.host.card("ayah"), {"width": 720})
        self.assertEqual(label.get_string("background-color"), "#334455; width: 720px")

    def test_enabling_avatar_brings_it_in_front_of_the_clock(self):
        self.host.root.set_value("widgets", GLib.Variant("aa{sv}", [
            entry("clock"), entry("another-widget"), entry("avatar", False), entry("ayah"),
        ]))
        self.host.set_visible("avatar", True)
        stack = self.host.root.get_value("widgets").unpack()
        self.assertEqual([next(iter(row)) for row in stack], ["avatar", "clock", "another-widget", "ayah"])

    def test_card_transparency_round_trips_without_fading_the_text(self):
        clock = self.host.card("clock")
        updated = self.host.apply_card("clock", clock, {"style": "Solid", "transparency": 67})
        self.assertEqual((updated.style, updated.transparency, updated.text), ("Solid", 67, clock.text))
        self.assertEqual(self.host.widget("clock").get_string("background-color"), "rgba(57,51,62,0.33)")

    def test_transparency_preserves_native_colours_and_other_declarations(self):
        frame = self.host.widget("clock")
        for native, colour, transparency, channels in (
            ("white", "#ffffff", 0, "255,255,255"),
            ("#33445580", "#334455", 50, "51,68,85"),
            ("rgba(12.5,30,45,0.6)", "#0d1e2d", 40, "12.5,30,45"),
        ):
            with self.subTest(native=native):
                frame.set_string("background-color", native + "; box-shadow: none")
                saved = self.host.card("clock")
                self.assertEqual((saved.background, saved.transparency), (colour, transparency))
                updated = self.host.apply_card("clock", saved, {"transparency": 67})
                self.assertEqual((updated.background, updated.transparency), (colour, 67))
                self.assertEqual(frame.get_string("background-color"),
                                 f"rgba({channels},0.33); box-shadow: none")

    def test_unreadable_background_rejects_transparency_edit_before_writing(self):
        frame = self.host.widget("clock")
        frame.set_string("background-color", "var(--desktop-background)")
        saved = self.host.card("clock")
        with self.assertRaisesRegex(HostError, "saved background colour"):
            self.host.apply_card("clock", saved, {"transparency": 65, "size": 24})
        self.assertEqual(frame.get_string("background-color"), "var(--desktop-background)")
        self.assertEqual(self.host.card("clock").size, saved.size)

    def test_choosing_preview_colour_repairs_an_unreadable_background(self):
        frame = self.host.widget("clock")
        frame.set_string("background-color", "var(--desktop-background)")
        editor = CardEditor("clock", self.host.card("clock"))
        self.assertFalse(editor.draft.background_readable)
        editor.edit(background=editor.draft.background)
        self.assertTrue(editor.dirty)
        editor.edit(transparency=65)
        self.assertEqual(editor.changes(), {"background": "#39333e", "transparency": 65})
        updated = self.host.apply_card("clock", editor.saved, editor.changes())
        self.assertTrue(updated.background_readable)
        self.assertEqual(frame.get_string("background-color"), "rgba(57,51,62,0.35)")

    def test_style_change_preserves_native_background(self):
        frame = self.host.widget("clock")
        frame.set_string("background-color", "white")
        updated = self.host.apply_card("clock", self.host.card("clock"), {"style": "Minimal"})
        self.assertEqual((updated.style, updated.background), ("Minimal", "#ffffff"))
        self.assertEqual(frame.get_string("background-color"), "white")

    def test_system_font_family_with_punctuation_round_trips(self):
        clock = self.host.card("clock")
        updated = self.host.apply_card("clock", clock, {"font": "Family's & Sans"})
        self.assertEqual(updated.font, "Family's & Sans")
        updated = self.host.apply_card("clock", updated, {"font": ""})
        self.assertEqual(updated.font, "")
