import unittest

from desktop_widgets.gnome import HostError
from desktop_widgets.integration import HOOKS, PANEL_MARKER, patch_extension


class IntegrationPatchTest(unittest.TestCase):
    def test_integration_applies_once_and_refuses_ambiguous_hooks(self):
        source = "\n".join(before for before, _ in HOOKS) + "\n        this._syncClockTimerToNearestSecond();"
        patched = patch_extension(source)
        self.assertEqual(patch_extension(patched), patched)
        self.assertIn("this._widgetAttachments = new WidgetAttachments(this);", patched)
        self.assertIn(PANEL_MARKER, patched)
        self.assertIn("this._widgetIndicator?.displayedWidgets(widgetIds)", patched)
        with self.assertRaises(HostError):
            patch_extension(source + "\n" + HOOKS[0][0])
