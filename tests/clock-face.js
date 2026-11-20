import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';

import {clockMarkup} from '../desktop_widgets/widgets/clock/face.js';
import {measureTrack} from '../desktop_widgets/bridge/track.js';

const layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context());
const date = new Date(2026, 10, 20, 4, 40, 27);
const card = {size: 14, width: 460, accent: '#d7b45d', clock_design: 'Lantern'};
for (const face of ['en', 'ar']) {
    layout.set_markup(clockMarkup({...card, face}, date, '10 Jumada al-Akhirah 1448'), -1);
    const text = layout.get_text();
    const dial = face === 'ar' ? '٠٤:٤٠' : '04:40';
    const seconds = face === 'ar' ? '٢٧' : ':27';
    const position = value => layout.index_to_pos(new TextEncoder().encode(text.slice(0, text.indexOf(value))).length).x;
    if (!text.includes(dial) || !text.includes(seconds) || (position(seconds) < position(dial)) !== (face === 'ar'))
        throw new Error(`The ${face} clock placed seconds on the wrong side of its dial.`);
    const dialLine = text.split('\n').find(line => line.includes(dial));
    if (face === 'ar' && Pango.find_base_dir(dialLine, -1) !== Pango.Direction.RTL)
        throw new Error('The Arabic dial line must follow the right-aligned paragraph direction.');
    if (!measureTrack(layout, 0, 0, 150))
        throw new Error(`The ${face} clock has no measurable avatar rail.`);
}
print('Clock numeral direction and perch rail checks passed.');
