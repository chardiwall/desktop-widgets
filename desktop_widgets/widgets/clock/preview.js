import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';

import {clockMarkup} from './face.js';

const [raw, cells, scale] = ARGV;
const card = JSON.parse(raw);
const layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context());
print(clockMarkup(card, new Date(2026, 10, 20, 4, 40, 20),
    '10 Jumada al-Akhirah 1448', Number(cells), Number(scale),
    {layout, headerWidth: card.headerWidth, height: card.height}));
