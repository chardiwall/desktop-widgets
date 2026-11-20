import unittest

from desktop_widgets.settings import Card, CardEditor, theme_preview


class CardEditorTest(unittest.TestCase):
    def test_preview_is_discarded_without_writing_to_the_host(self):
        current = Card(background="#39333e")
        editor = CardEditor("ayah", current)
        editor.select_theme("Lantern A")
        editor.edit(background="#60282a")

        self.assertTrue(editor.dirty)
        self.assertEqual(editor.draft.background, "#60282a")
        self.assertEqual(editor.changes(), {"background": "#60282a", "accent": "#ffbc72",
                                           "style": "Solid", "text": "#fff0d7", "font": "Literata",
                                           "arabic_font": "Amiri", "art_theme": "Lantern A"})

        editor.cancel()

        self.assertEqual(editor.draft, current)
        self.assertFalse(editor.dirty)

    def test_custom_colours_survive_switching_between_presets(self):
        editor = CardEditor("clock", Card())
        editor.edit(accent="#319b86")
        editor.select_theme("Blueprint")
        self.assertEqual(editor.draft.accent, "#88d9fa")
        editor.select_theme("Custom")
        self.assertEqual(editor.draft.accent, "#319b86")

    def test_cancel_restores_the_applied_preset_and_keeps_the_custom_colours(self):
        editor = CardEditor("clock", Card())
        editor.edit(accent="#319b86")
        editor.select_theme("Blueprint")
        editor.mark_saved(editor.draft)
        editor.select_theme("Graphite")
        self.assertEqual(editor.draft.accent, "#ad98ce")
        editor.cancel()

        self.assertEqual(editor.theme, "Blueprint")
        self.assertFalse(editor.dirty)
        editor.select_theme("Custom")
        self.assertEqual(editor.draft.accent, "#319b86")

    def test_choosing_a_theme_preserves_the_users_transparency(self):
        editor = CardEditor("clock", Card(transparency=82))
        editor.select_theme("Blueprint")
        self.assertEqual(editor.draft.transparency, 82)
        self.assertEqual(editor.draft.font, "DejaVu Sans Mono")

    def test_cancel_reloads_custom_even_when_the_current_preset_is_unchanged(self):
        custom = Card(text_opacity=62)
        preset = theme_preview("ayah", "Graphite A", Card())
        editor = CardEditor("ayah", preset, Card())

        editor.edit(text_opacity=30)
        editor.cancel(preset, custom)
        self.assertFalse(editor.dirty)
        editor.select_theme("Custom")
        self.assertEqual(editor.draft, custom)

    def test_applying_a_preset_reloads_the_committed_custom_card(self):
        custom = Card(text_opacity=62)
        editor = CardEditor("ayah", custom)
        editor.select_theme("Graphite A")
        editor.edit(text_opacity=30)
        editor.select_theme("Oasis A")
        editor.mark_saved(editor.draft, custom)
        editor.select_theme("Custom")
        self.assertEqual(editor.draft, custom)
