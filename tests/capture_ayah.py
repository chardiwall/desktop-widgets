"""Capture the GTK Ayah card against fixed light and dark wallpaper fixtures."""

import argparse
from html import escape
import json
from pathlib import Path
from shlex import quote
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_widgets.app import Adw, Gdk, Gio, GLib, Gtk
from desktop_widgets.bridge.gnome import AzClockHost, HostError
from desktop_widgets.settings import Card, theme_preview
from desktop_widgets.widgets.ayah.card import verse_from_markup
from desktop_widgets.widgets.ayah.preview import AyahPreview
from desktop_widgets.widgets.ayah.themes import PRESETS
from gi.repository import Graphene

PASSAGES = {"short": (94, 6, 6), "multi": (94, 5, 7), "long": (2, 282, 282)}
WALLPAPERS = {
    "light": "linear-gradient(138deg, #fbefce, #c1d5da 49%, #f4dfb8 50%, #a8cdcc)",
    "dark": "linear-gradient(138deg, #24172c, #183038 49%, #354259 50%, #26172c)",
}


def passage(arabic, english, surah, first, last):
    ar, en = arabic[surah - 1], english[surah - 1]
    digits = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    verse = " ".join(f'{ar["ayahs"][n - 1]["text"].lstrip(chr(0xFEFF))} ۝{str(n).translate(digits)}'
                    for n in range(first, last + 1))
    translation = " ".join(en["ayahs"][n - 1]["text"] for n in range(first, last + 1))
    ref = f"{en['englishName']} {surah}:{first}" + (f"-{last}" if last > first else "")
    return escape(f"﴿ {verse} ﴾\n━━━━━━━━\n{translation}\n{ref} · {ar['name']}")


def settle(condition, message):
    context = GLib.MainContext.default()
    deadline = monotonic() + 6
    while monotonic() < deadline:
        context.iteration(False)
        if condition():
            return
        sleep(0.01)
    raise RuntimeError(message)


def capture(window, surface, destination):
    wait_until = monotonic() + 0.18
    settle(lambda: monotonic() >= wait_until, "The preview did not paint.")
    width, height = surface.get_width(), surface.get_height()
    paintable = Gtk.WidgetPaintable.new(surface)
    snapshot = Gtk.Snapshot.new()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None or not window.get_renderer().render_texture(
            node, Graphene.Rect().init(0, 0, width, height)).save_to_png(str(destination)):
        raise RuntimeError(f"Could not save {destination}")


def check_screenshots(output, passages, theme):
    host = AzClockHost.discover()
    settings = AzClockHost(host.source, Gio.memory_settings_backend_new()).element("ayah")
    settings.set_boolean("polling-enabled", False)
    preview = AyahPreview(settings)
    surface = Gtk.Overlay()
    wallpaper = Gtk.Box()
    css = Gtk.CssProvider()
    wallpaper.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    surface.set_child(wallpaper)
    preview.widget.set_halign(Gtk.Align.CENTER)
    preview.widget.set_valign(Gtk.Align.CENTER)
    surface.add_overlay(preview.widget)
    window = Adw.Window(title="Ayah screenshot check", default_width=540, default_height=720)
    window.set_content(surface)
    window.present()
    settle(lambda: window.get_mapped() and window.get_width() > 0, "The preview window did not open.")

    with TemporaryDirectory(prefix="ayah-capture-") as scratch:
        for name, markup in passages.items():
            fixture = Path(scratch) / f"{name}.pango"
            fixture.write_text(markup, encoding="utf-8")
            long = name == "long"
            window.get_settings().set_property("gtk-xft-dpi", round(96 * 1024 * (1.6 if long else 1)))
            card = theme_preview("ayah", theme, Card(width=360 if long else 460, transparency=55))
            preview.widget.set_size_request(card.width, -1)
            preview.render(card)
            settings.set_string("command", f"cat {quote(str(fixture))}")
            expected = verse_from_markup(markup)
            settle(lambda: preview.verse == expected, f"The {name} passage did not load.")
            arabic, translation, reference = (label.get_text() for label in preview.labels)
            if " ".join(arabic.split()) != f"﴿ {expected[0]} ﴾" or (translation, reference) != expected[1:]:
                raise RuntimeError(f"The {name} preview omitted part of the passage.")
            if long:
                preview.panel.set_size_request(card.width, 620)
            settle(lambda: preview.widget.get_width() >= card.width, "The card viewport was too narrow to capture.")
            for tone, paint in WALLPAPERS.items():
                css.load_from_string(f"box {{ background-image: {paint}; }}")
                scroll = preview.scroll.get_vadjustment()
                scroll.set_value(0)
                stem = f"{name}-{tone}"
                capture(window, surface, output / f"{stem}.png")
                if long:
                    assert scroll.get_upper() > scroll.get_page_size() > 0, "The long passage must scroll in the card."
                    scroll.set_value(scroll.get_upper() - scroll.get_page_size())
                    capture(window, surface, output / f"{stem}-end.png")
    window.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=PRESETS, default="Graphite A")
    parser.add_argument("--output", type=Path, default=Path("dist/ayah-preview/regression"))
    parser.add_argument("--quran-data", type=Path, default=Path(GLib.get_user_data_dir()) / "daily-ayah")
    args = parser.parse_args()
    try:
        arabic, english = [
            json.loads((args.quran_data / f"{edition}.json").read_text(encoding="utf-8"))["data"]["surahs"]
            for edition in ("quran-uthmani", "en.sahih")
        ]
        fixtures = {name: passage(arabic, english, *ref) for name, ref in PASSAGES.items()}
        if Gdk.Display.get_default() is None:
            parser.error("Run the screenshot check from a graphical desktop session.")
        Adw.init()
        args.output.mkdir(parents=True, exist_ok=True)
        check_screenshots(args.output, fixtures, args.theme)
    except (OSError, RuntimeError, HostError, GLib.Error) as error:
        parser.error(str(error))
    print(f"Ayah screenshots saved to {args.output}")


if __name__ == "__main__":
    main()
