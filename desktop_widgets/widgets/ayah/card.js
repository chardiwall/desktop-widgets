import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Pango from 'gi://Pango';

const specFile = Gio.File.new_for_uri(import.meta.url).get_parent().get_child('themes.json');
const [, specBytes] = specFile.load_contents(null);
export const SPEC = JSON.parse(new TextDecoder().decode(specBytes));
export const {sizing: SIZING} = SPEC;

const divider = /^[━─]+$/u;
const marker = /(۝[0-9٠-٩۰-۹]+)/u;

function arabicText(value) {
    value = value.replace(/^[ ﴿﴾]+|[ ﴿﴾]+$/gu, '').replaceAll('۝ ', '۝');
    const chunks = value.split(marker);
    if (chunks.length < 3 || chunks.at(-1).trim())
        return value;
    // The legacy source appends each number. The following ayah's number belongs at each join.
    const parts = [chunks[0].trim()];
    for (let index = 1; index < chunks.length - 2; index += 2)
        parts.push(`${chunks[index + 2]} ${chunks[index + 1].trim()}`);
    return parts.join(' ');
}

export function verseFromText(plain) {
    const lines = plain.trim().split(/\r?\n/u).map(line => line.replace(/^[\s\u200e\u200f]+|[\s\u200e\u200f]+$/gu, ''));
    const index = lines.findIndex(line => divider.test(line));
    if (index === -1)
        return ['', plain.trim(), ''];
    const arabic = arabicText(lines.slice(0, index).filter(Boolean).join(' '));
    const remaining = lines.slice(index + 1).filter(line => line && !divider.test(line));
    return [arabic, remaining.slice(0, -1).join(' '), remaining.at(-1) ?? ''];
}

function verseMarkup(index, text, theme, points, leading) {
    const escape = value => GLib.markup_escape_text(value, -1);
    const font = index === 0 ? `${theme.arabic_font}, Amiri, Amiri Quran` : `${theme.font}, Amiri`;
    let body = escape(text);
    if (index === 0) {
        const ornament = value => `<span font_family="Amiri Quran, Amiri" foreground="${theme.accent}">${escape(value)}</span>`;
        const parts = text.split(marker);
        body = escape(parts[0]);
        for (let i = 1; i < parts.length; i += 2) {
            body += ornament(parts[i]);
            if (parts[i + 1])
                body += `\u00a0${escape(parts[i + 1].trimStart())}`;
        }
        body = `${ornament('﴿')}\u00a0${body}\u00a0${ornament('﴾')}`;
    } else if (index === 2) {
        body = `<span foreground="${theme.accent}">${body}</span>`;
    }
    return `<span font_family="${GLib.markup_escape_text(font, -1)}" size="${Math.round(points * Pango.SCALE)}" ` +
        `line_height="${leading}">${body}</span>`;
}

function spacingCorrection(layout) {
    const lines = layout.get_iter();
    let [previous] = lines.get_line_extents();
    let baseline = lines.get_baseline();
    let correction = 1;
    while (lines.next_line()) {
        const [ink] = lines.get_line_extents();
        const nextBaseline = lines.get_baseline();
        const deficit = SIZING.arabic_ink_gap * Pango.SCALE + previous.y + previous.height - ink.y;
        if (deficit > 0 && nextBaseline > baseline)
            correction = Math.max(correction, 1 + deficit / (nextBaseline - baseline));
        previous = ink;
        baseline = nextBaseline;
    }
    return correction;
}

export function fitVerse(verse, width, theme, arabicSize, englishSize, createLayout, viewportHeight) {
    const [top, right, bottom, left] = theme.padding;
    const arabicInset = theme.border + SIZING.arabic_padding;
    const englishWidth = Math.max(1, width - left - right);
    const widths = [Math.max(1, width - 2 * arabicInset), englishWidth, englishWidth];
    const sizes = [arabicSize, englishSize, englishSize * SIZING.reference_scale];
    const rule = verse[0] ? SIZING.rule_height : 0;
    const arabicLeading = Object.hasOwn(SPEC.arabic_leading, theme.arabic_font)
        ? SPEC.arabic_leading[theme.arabic_font] : 1.05;
    let layout;

    function measure(index, value, points) {
        if (!value)
            return ['', 0];
        const block = createLayout(index);
        block.set_wrap(Pango.WrapMode.WORD_CHAR);
        block.set_width(widths[index] * Pango.SCALE);
        let leading = index === 0 ? arabicLeading : 1;
        let markup;
        for (let pass = 0; pass < (index === 0 ? 3 : 1); pass++) {
            markup = verseMarkup(index, value, theme, points, leading);
            block.set_markup(markup, -1);
            const correction = index === 0 ? spacingCorrection(block) : 1;
            if (correction <= 1)
                break;
            leading *= correction + 0.015;
        }
        const [ink, logical] = block.get_pixel_extents();
        return [markup, Math.max(logical.height, ink.y + ink.height) - Math.min(0, ink.y)];
    }

    for (const factor of SIZING.reductions) {
        const measured = verse.map((value, i) => measure(i, value, Math.max(SIZING.min_size, sizes[i] * factor)));
        const markup = measured.map(([value]) => value);
        const heights = measured.map(([, height]) => height);
        const blocks = [...heights, rule].filter(Boolean);
        const height = Math.max(SIZING.min_height, top + bottom + blocks.reduce((sum, value) => sum + value, 0) +
            SIZING.gap * Math.max(0, blocks.length - 1));
        layout = {markup, heights, widths, height};
        if (height <= viewportHeight)
            break;
    }
    return layout;
}
