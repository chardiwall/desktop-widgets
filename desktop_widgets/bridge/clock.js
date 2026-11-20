import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {SIZING} from '../widgets/ayah/card.js';
import {clockDesign, clockMarkup, CLOCK_PADDING} from '../widgets/clock/face.js';
import {cardPosition, cardWorkArea, paintCardArt} from './ayah.js';

const ART = import.meta.url.replace(/bridge\/clock\.js$/, 'widgets/clock/art/');

class ClockCard {
    constructor(frame, source, settings, appearance) {
        this.position = box => cardPosition(frame, box);
        this.actor = new St.Widget({layout_manager: new Clutter.FixedLayout(), clip_to_allocation: true});
        this.art = new St.Widget({layout_manager: new Clutter.FixedLayout()});
        this.art.set_pivot_point(0.5, 0.5);
        this.border = new St.Widget();
        this.label = new St.Label();
        this.label.clutter_text.set_use_markup(true);
        source.opacity = 0;
        source.reactive = false;
        source.set_no_layout(true);
        this.actor.add_child(source);
        this.actor.add_child(this.art);
        this.actor.add_child(this.border);
        this.actor.add_child(this.label);

        let cachedDay = '';
        let hijri = '';
        const refresh = () => {
            if (!this.actor.mapped)
                return;
            const now = new Date();
            const day = GLib.DateTime.new_now_local().format('%F');
            if (day !== cachedDay || !hijri) {
                cachedDay = day;
                try {
                    const [, bytes] = GLib.file_get_contents(GLib.build_filenamev([
                        GLib.get_user_cache_dir(), 'clock-extras', `hijri-${day}.txt`]));
                    hijri = new TextDecoder().decode(bytes).trim();
                } catch {
                    hijri = '';
                }
            }

            const face = appearance.get_string('clock-face');
            const designName = appearance.get_string('clock-design');
            const design = clockDesign(designName);
            const font = settings.get_value('font-family-override').deepUnpack();
            const nativeWidth = Number(settings.get_string('background-color').match(/(?:^|;)\s*width:\s*(\d+)px\b/)?.[1] ?? SIZING.default_width);
            const explicitWidth = appearance.get_int('clock-card-width');
            const savedWidth = explicitWidth > 0 ? explicitWidth : nativeWidth;
            const area = cardWorkArea(frame)?.area ?? global.stage;
            const width = Math.max(1, Math.min(Math.max(SIZING.min_width, savedWidth), SIZING.max_width, area.width - 2 * SIZING.margin));
            const contentWidth = Math.max(1, width - 2 * CLOCK_PADDING);
            const accent = settings.get_string('border-color').split(';', 1)[0];
            const foreground = settings.get_string('foreground-color').split(';', 1)[0];
            const background = frame._settings.get_string('background-color').split(';', 1)[0];
            const visibleBackground = frame._settings.get_boolean('show-background');
            const opacity = !visibleBackground || background === 'transparent' ? 0 :
                Number(background.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([.\d]+)\s*\)$/i)?.[1] ?? 1);
            const border = frame._settings.get_boolean('show-border') ? 1 : 0;
            const radius = border ? Math.max(12, frame._settings.get_int('border-radius')) : 8;
            const styleKey = JSON.stringify([face, designName, accent, foreground, background, opacity, border, radius]);
            if (this.styleKey !== styleKey) {
                this.styleKey = styleKey;
                this.actor.style = `background-color: ${opacity ? background : 'transparent'}; border-radius: ${radius}px;`;
                this.border.style = `border-radius: ${radius}px; border: ${border}px solid ${accent};`;
                this.label.style = `color: ${foreground}; text-align: ${face === 'ar' ? 'right' : 'left'};`;
            }
            this.art.opacity = Math.round(Math.sqrt(opacity) * 255);
            this.border.opacity = Math.round(opacity * 219);
            this.art.set_scale(face === 'ar' ? -1 : 1, 1);
            this.label.opacity = Math.round(appearance.get_int('clock-text-opacity') * 2.55);
            this.actor._clockPerchSide = face === 'ar' ? 'left' : 'right';
            const text = this.label.clutter_text;
            text.set_line_alignment(face === 'ar' ? Pango.Alignment.RIGHT : Pango.Alignment.LEFT);
            const layout = text.create_pango_layout('');
            layout.set_markup('<span font_family="DejaVu Sans Mono" size="9pt">━━━━━━━━━━</span>', -1);
            const [tenCells] = layout.get_pixel_size();
            const cells = Math.max(8, Math.floor((contentWidth - 2) * 10 / Math.max(1, tenCells)));
            const headerWidth = Math.max(80, contentWidth - 100);
            const markup = clockMarkup({
                face, width, font: font[0] ? font[1] : '', size: settings.get_int('font-size'),
                accent, clock_design: designName, arabic_font: appearance.get_string('clock-arabic-font'),
            }, now, hijri, cells, 1, {layout, headerWidth, height: SIZING.height - 28});
            layout.set_markup(markup, -1);
            const [, textHeight] = layout.get_pixel_size();
            const height = Math.min(Math.max(SIZING.height, textHeight + 28), Math.max(1, area.height - 2 * SIZING.margin));
            this.actor.set_size(width, height);
            this.art.set_size(width, height);
            this.border.set_size(width, height);
            paintCardArt(this.art, ART, {...design, radius}, width, height);
            this.label.set_position(CLOCK_PADDING, Math.max(6, (height - textHeight) / 2));
            this.label.set_size(contentWidth, textHeight);
            text.set_markup(markup);
        };

        for (const object of [appearance, settings, frame._settings])
            object.connectObject('changed', refresh, this.actor);
        Main.layoutManager.connectObject('monitors-changed', refresh, this.actor);
        St.ThemeContext.get_for_stage(global.stage).connectObject('changed', refresh, this.actor);
        this.actor.connect('notify::mapped', refresh);
        const timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            refresh();
            return GLib.SOURCE_CONTINUE;
        });
        this.actor.connect('destroy', () => {
            this.destroying = true;
            GLib.Source.remove(timer);
        });
        source.connect('destroy', () => {
            if (!this.destroying)
                this.actor.destroy();
        });
    }
}

export function decorateClock(frame, source, settings) {
    const schema = Gio.SettingsSchemaSource.get_default()?.lookup('io.github.desktopwidgets.Settings', true);
    if (schema?.has_key('clock-card-width'))
        return new ClockCard(frame, source, settings, new Gio.Settings({settings_schema: schema}));
    return null;
}
