from pathlib import Path
import unittest

import gi

gi.require_versions({"Pango": "1.0", "PangoCairo": "1.0"})
from gi.repository import Pango, PangoCairo

from desktop_widgets.widgets.ayah.card import _spacing_correction, fit_verse, verse_from_markup, verse_markup
from desktop_widgets.widgets.ayah.themes import ART, PRESETS, SIZING, SPEC
from desktop_widgets.widgets.clock import themes as clock_themes


SHORT = ("إِنَّ مَعَ ٱلْعُسْرِ يُسْرًا", "Indeed, with hardship [will be] ease.", "Ash-Sharh 94:6")
MEDIUM = ("يَسْـَٔلُهُۥ مَن فِى ٱلسَّمَٰوَٰتِ وَٱلْأَرْضِ ۚ كُلَّ يَوْمٍ هُوَ فِى شَأْنٍۢ",
          "Whoever is within the heavens and earth asks Him; every day He is bringing about a matter.",
          "Ar-Rahmaan 55:29 · سُورَةُ الرَّحۡمَٰن")


class AyahLayoutTest(unittest.TestCase):
    def test_legacy_markup_becomes_three_plain_blocks(self):
        markup = ('<span size="190%">عَرَبِيّ\nنَصّ</span>\n‎<span alpha="1">━━</span>\n'
                  '‎<span foreground="#aa6622">━━</span>\n \nAn &amp;\nEnglish line.\n \nSurah 1:1')
        self.assertEqual(verse_from_markup(markup), ("عَرَبِيّ نَصّ", "An & English line.", "Surah 1:1"))

    def test_presets_load_all_ten_distinct_compositions(self):
        self.assertEqual(len(PRESETS), 10)
        self.assertIn("Blueprint B", PRESETS)
        for theme in PRESETS.values():
            for layer in theme["art"]:
                self.assertTrue((ART / layer["file"]).is_file(), layer)

    def test_clock_art_stays_at_the_edges_and_uses_its_own_files(self):
        directory = Path(clock_themes.__file__).with_name("art")
        self.assertEqual(len(clock_themes.DESIGNS), len(PRESETS))
        for name, theme in clock_themes.DESIGNS.items():
            with self.subTest(theme=name):
                scene, *ornaments = theme["art"]
                self.assertEqual(scene["anchor"], "bottom-right")
                scene_height = scene["width"] / scene["ratio"]
                self.assertGreaterEqual(scene_height, SIZING["height"] * 0.65)
                self.assertLessEqual(scene_height, SIZING["height"])
                for ornament in ornaments:
                    self.assertEqual(ornament["anchor"], "top-right")
                    self.assertLessEqual(ornament["width"], SIZING["default_width"] / 4)
                for layer in theme["art"]:
                    self.assertEqual(layer.get("inset", (0, 0))[0], 0)
                    self.assertLess(layer["opacity"], 0.8)
                    self.assertTrue((directory / layer["file"]).is_file())
                    self.assertFalse((ART / layer["file"]).exists())

    def test_blueprint_skyline_can_rise_behind_the_progress_rail(self):
        skyline, arch = clock_themes.DESIGNS["Blueprint"]["art"]
        self.assertGreater(skyline["width"] / skyline["ratio"], 150)
        self.assertEqual(arch["anchor"], "top-right")

    def test_verse_number_marks_the_start_of_each_following_ayah(self):
        theme = PRESETS["Oasis A"]
        for source, expected in (
            ("﴿ عَرَبِيّ ۝٥ ﴾", "عَرَبِيّ"),
            ("﴿ عَرَبِيّ ۝٥ نَصّ ۝٦ آخَر ۝٧ ﴾", "عَرَبِيّ ۝٦ نَصّ ۝٧ آخَر"),
        ):
            arabic, _, _ = verse_from_markup(f"{source}\n━━\nTranslation\nReference")
            self.assertEqual(arabic, expected)
            markup = verse_markup(0, arabic, theme, 21)
            self.assertIn(f'foreground="{theme["accent"]}"', markup)
            plain = Pango.parse_markup(markup, -1, "\0").text
            self.assertEqual(" ".join(plain.split()), f"﴿ {expected} ﴾")
            self.assertIn(f'foreground="{theme["accent"]}"', verse_markup(2, "Reference", theme, 12))

    def test_measured_fit_preserves_the_complete_verse_at_all_sizes(self):
        context = PangoCairo.FontMap.get_default().create_context()

        def create_layout(_index):
            return Pango.Layout.new(context)

        theme = PRESETS["Oasis A"]
        PangoCairo.context_set_resolution(context, 96)
        short, short_height = fit_verse(SHORT, SIZING["width"], theme, 24, 12, create_layout, 900)
        self.assertEqual(short_height, SIZING["height"])
        self.assertIn(f'size="{24 * Pango.SCALE}"', short[0])
        self.assertIn(f'size="{12 * Pango.SCALE}"', short[1])
        _, medium_height = fit_verse(MEDIUM, SIZING["width"], theme, 24, 12, create_layout, 900)
        self.assertGreater(medium_height, short_height)

        long_verse = (" ".join([MEDIUM[0]] * 8), " ".join([MEDIUM[1]] * 10), MEDIUM[2])
        for width in (SIZING["min_width"], SIZING["width"]):
            for scale in (1, 1.6):
                PangoCairo.context_set_resolution(context, 96 * scale)
                with self.subTest(width=width, scale=scale):
                    markup, content_height = fit_verse(long_verse, width, theme, 24, 12, create_layout, 420)
                    self.assertGreater(content_height, 420)
                    for index, (value, text) in enumerate(zip(markup, long_verse, strict=True)):
                        actual = Pango.parse_markup(value, -1, "\0").text
                        expected = f"﴿ {text} ﴾" if index == 0 else text
                        self.assertEqual(" ".join(actual.split()), expected)

    def test_arabic_font_spacing_leaves_clearance_for_wrapped_diacritics(self):
        context = PangoCairo.FontMap.get_default().create_context()
        PangoCairo.context_set_resolution(context, 153.6)
        arabic = " ".join([f"{MEDIUM[0]} ۝٢٩ {SHORT[0]}"] * 4)
        for font in SPEC["arabic_fonts"]:
            with self.subTest(font=font):
                theme = {**PRESETS["Graphite A"], "arabic_font": font}
                (markup, _, _), _ = fit_verse((arabic, "", ""), SIZING["min_width"], theme, 32, 12,
                                               lambda _: Pango.Layout.new(context), 900)
                layout = Pango.Layout.new(context)
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                layout.set_width((SIZING["min_width"] - 2 * (SIZING["arabic_padding"] + theme["border"])) * Pango.SCALE)
                layout.set_markup(markup, -1)
                self.assertGreater(layout.get_line_count(), 1)
                self.assertEqual(_spacing_correction(layout), 1)
