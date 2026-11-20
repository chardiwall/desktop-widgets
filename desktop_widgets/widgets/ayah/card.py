"""Pango layout for the GTK Ayah card."""

from html import escape
import re

from gi.repository import GLib, Pango

from .themes import SIZING, SPEC

MARKER = re.compile(r"(۝[0-9٠-٩۰-۹]+)")


def _arabic_text(value):
    value = value.strip(" ﴿﴾").replace("۝ ", "۝")
    chunks = MARKER.split(value)
    if len(chunks) < 3 or chunks[-1].strip():
        return value
    # The source puts each number after its ayah. Use the following ayah's number at each join.
    return " ".join([chunks[0].strip(), *(
        chunks[index + 2] + " " + chunks[index + 1].strip()
        for index in range(1, len(chunks) - 2, 2)
    )])


def verse_from_markup(markup):
    try:
        plain = Pango.parse_markup(markup, -1, "\0").text
    except GLib.Error:
        plain = markup
    lines = [line.strip(" \t\r\u200e\u200f") for line in plain.strip().splitlines()]
    divider = next((i for i, line in enumerate(lines) if re.fullmatch("[━─]+", line)), None)
    if divider is None:
        return "", plain.strip(), ""
    arabic = _arabic_text(" ".join(filter(None, lines[:divider])))
    remaining = [line for line in lines[divider + 1:] if line and not re.fullmatch("[━─]+", line)]
    return arabic, " ".join(remaining[:-1]), remaining[-1] if remaining else ""


def verse_markup(index, text, theme, points, leading=None):
    if not text:
        return ""
    if leading is None:
        leading = SPEC["arabic_leading"].get(theme["arabic_font"], 1.05) if index == 0 else 1
    accent = theme["accent"]
    if index == 0:
        font = theme["arabic_font"] + ", Amiri, Amiri Quran"

        def ornament(value):
            return f'<span font_family="Amiri Quran, Amiri" foreground="{accent}">{escape(value)}</span>'

        parts = MARKER.split(text)
        body = escape(parts[0]) + "".join(
            ornament(parts[i]) + ("\u00a0" + escape(parts[i + 1].lstrip()) if parts[i + 1] else "")
            for i in range(1, len(parts), 2)
        )
        body = ornament("﴿") + "\u00a0" + body + "\u00a0" + ornament("﴾")
    else:
        font = theme["font"] + ", Amiri"
        body = escape(text)
        if index == 2:
            body = f'<span foreground="{accent}">{body}</span>'
    return (f'<span font_family="{escape(font)}" size="{round(points * Pango.SCALE)}" '
            f'line_height="{leading}">{body}</span>')


def _spacing_correction(layout):
    lines = layout.get_iter()
    previous, baseline = lines.get_line_extents()[0], lines.get_baseline()
    correction = 1
    while lines.next_line():
        ink = lines.get_line_extents()[0]
        next_baseline = lines.get_baseline()
        deficit = SIZING["arabic_ink_gap"] * Pango.SCALE + previous.y + previous.height - ink.y
        if deficit > 0 and next_baseline > baseline:
            correction = max(correction, 1 + deficit / (next_baseline - baseline))
        previous, baseline = ink, next_baseline
    return correction


def fit_verse(verse, width, theme, arabic_size, english_size, create_layout, viewport_height):
    top, right, bottom, left = theme["padding"]
    arabic_inset = theme["border"] + SIZING["arabic_padding"]
    english_width = max(1, width - left - right)
    widths = (max(1, width - 2 * arabic_inset), english_width, english_width)
    sizes = (arabic_size, english_size, english_size * SIZING["reference_scale"])
    rule = SIZING["rule_height"] if verse[0] else 0

    def measure(index, value, points):
        if not value:
            return "", 0
        layout = create_layout(index)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_width(widths[index] * Pango.SCALE)
        leading = SPEC["arabic_leading"].get(theme["arabic_font"], 1.05) if index == 0 else 1
        for _ in range(3 if index == 0 else 1):
            markup = verse_markup(index, value, theme, points, leading)
            layout.set_markup(markup, -1)
            if index != 0 or (correction := _spacing_correction(layout)) <= 1:
                break
            leading *= correction + 0.015
        ink, logical = layout.get_pixel_extents()
        return markup, max(logical.height, ink.y + ink.height) - min(0, ink.y)

    for factor in SIZING["reductions"]:
        markup, heights = zip(*(measure(i, value, max(SIZING["min_size"], sizes[i] * factor))
                                for i, value in enumerate(verse)), strict=True)
        blocks = [block for block in (*heights, rule) if block]
        height = max(SIZING["min_height"], top + bottom + sum(blocks) + SIZING["gap"] * max(0, len(blocks) - 1))
        if height <= viewport_height:
            break
    return markup, height
