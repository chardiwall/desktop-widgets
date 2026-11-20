import GLib from 'gi://GLib';

const file = GLib.filename_from_uri(import.meta.url)[0];
const [, bytes] = GLib.file_get_contents(GLib.build_filenamev([GLib.path_get_dirname(file), 'themes.json']));
const designs = JSON.parse(new TextDecoder().decode(bytes));
const arabicMonths = ['المحرّم', 'صفر', 'ربيع الأول', 'ربيع الآخر', 'جمادى الأولى', 'جمادى الآخرة',
    'رجب', 'شعبان', 'رمضان', 'شوّال', 'ذو القعدة', 'ذو الحجة'];
const englishMonths = ['Muharram', 'Safar', 'Rabi al-Awwal', 'Rabi al-Thani', 'Jumada al-Ula', 'Jumada al-Akhirah',
    'Rajab', "Sha'ban", 'Ramadan', 'Shawwal', 'Dhu al-Qadah', 'Dhu al-Hijjah'];

export const CLOCK_PADDING = 18;

export function clockDesign(name) {
    return Object.hasOwn(designs, name) ? designs[name] : designs.Lantern;
}

export function clockMarkup(card, date, hijri = '', cells = 44, scale = 1, fit = null) {
    const design = clockDesign(card.clock_design);
    const arabic = card.face === 'ar';
    const locale = arabic ? 'ar-EG' : 'en-GB';
    const numerals = text => arabic ? String(text).replace(/[0-9]/g, digit => '٠١٢٣٤٥٦٧٨٩'[digit]) : String(text);
    const escaped = text => GLib.markup_escape_text(text, -1);
    const accent = /^#[0-9a-f]{6}$/i.test(card.accent) ? card.accent : design.accent;
    const font = (arabic ? card.arabic_font : card.font) || (arabic ? design.arabic_font : 'sans-serif');
    let textScale = scale;
    const pt = size => `${Math.max(5, Math.floor(size * textScale))}pt`;
    const span = (text, size, attrs = '') => `<span size="${pt(size)}" ${attrs}>${text}</span>`;
    const size = Math.min(design.size + 8, design.size + (card.size - 14) * 0.55, card.width / 8);
    const detailSize = Math.max(9, card.size * 0.91);
    const timeParts = [date.getHours(), date.getMinutes(), date.getSeconds()].map(value => String(value).padStart(2, '0'));
    const [hour, minute, second] = timeParts.map(numerals);
    const time = () => {
        const dial = span(`${hour}:${minute}`, size, 'weight="bold" font_features="tnum"');
        const seconds = span(arabic ? second : `:${second}`, size * 0.39,
            `foreground="${accent}" rise="${Math.round(size * textScale * 145)}"`);
        return (arabic ? '\u200f' : '') + `\u2066${arabic ? '\u202D' + seconds + '\u2002' + dial + '\u202C' : dial + seconds}\u2069`;
    };
    const dateText = new Intl.DateTimeFormat(locale, {weekday: 'long', month: 'long', day: 'numeric'}).format(date);
    const calendar = () => span(escaped(dateText), detailSize);
    if (arabic && hijri) {
        const match = /^(\d+) (.+) (\d+)$/.exec(hijri);
        const month = englishMonths.indexOf(match?.[2]);
        hijri = month >= 0 ? numerals(`${match[1]} ${arabicMonths[month]} ${match[3]} هـ`) : '';
    }
    const lunar = () => hijri ? span(escaped(hijri), detailSize * 0.88, 'alpha="83%"') : '';
    const title = () => span(escaped(design.title[Number(arabic)]), detailSize * 1.02,
        `foreground="${accent}" ${arabic ? '' : 'style="italic"'}`);
    const day = (date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds()) / 86400;
    const percent = new Intl.NumberFormat(locale, {style: 'percent'}).format(day);
    const readout = () => span(arabic ? `${percent} من اليوم` : `${percent} of the day`,
        detailSize * 0.94, `foreground="${accent}" ${arabic ? '' : 'style="italic"'}`);
    const filled = Math.round(cells * day);
    const on = `<span foreground="${accent}">${'━'.repeat(filled)}</span>`;
    const off = `<span alpha="26%">${'━'.repeat(cells - filled)}</span>`;
    const rail = `<span size="${Math.max(5, Math.round(9 * scale))}pt" font_family="DejaVu Sans Mono">\u200e${arabic ? off + on : on + off}</span>`;
    const block = lines => `<span font_family="${escaped(font)}" line_height="${arabic ? 0.73 : 1.02}">${lines.map(line => line()).filter(Boolean).join('\n')}</span>`;
    const header = [title, time, calendar, lunar];
    const all = [...header, () => rail, readout];
    if (fit) {
        const {layout, headerWidth, height} = fit;
        layout.set_markup(block(header), -1);
        const [width] = layout.get_pixel_size();
        layout.set_markup(block(all), -1);
        const [, textHeight] = layout.get_pixel_size();
        textScale *= Math.min(1, headerWidth / Math.max(1, width), height / Math.max(1, textHeight));
    }
    return block(all);
}
