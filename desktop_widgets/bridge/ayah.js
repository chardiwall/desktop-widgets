import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {fitVerse, SIZING, SPEC, verseFromText} from '../widgets/ayah/card.js';

const ART = import.meta.url.replace(/bridge\/ayah\.js$/, 'widgets/ayah/art/');
const WIDTH = /(?:^|;)\s*width:\s*(\d+)px\b/u;

function label(index) {
    const item = new St.Label({x_expand: true, y_align: Clutter.ActorAlign.START});
    const direction = index === 0 ? Clutter.TextDirection.RTL : Clutter.TextDirection.LTR;
    item.set_text_direction(direction);
    item.clutter_text.set_text_direction(direction);
    item.clutter_text.set({
        line_wrap: true,
        line_wrap_mode: Pango.WrapMode.WORD_CHAR,
        ellipsize: Pango.EllipsizeMode.NONE,
        line_alignment: index === 0 ? Pango.Alignment.RIGHT : Pango.Alignment.LEFT,
    });
    item.style = `text-align: ${index === 0 ? 'right' : 'left'};`;
    return item;
}

function place(actor, x, y, width, height) {
    actor.set_position(x, y);
    actor.set_size(width, height);
}

function palette(frame, settings, appearance) {
    const theme = SPEC.themes[appearance?.get_string('ayah-theme')];
    const background = frame.get_string('background-color').split(';', 1)[0];
    const alpha = background.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([.\d]+)\s*\)$/iu)?.[1];
    const nativeOpacity = !frame.get_boolean('show-background') || background === 'transparent' ? 0 : Number(alpha ?? 1);
    const settingsSchema = appearance?.settings_schema;
    if (theme) {
        const [size, width, presetTransparency] = settingsSchema?.has_key('ayah-preset-options') ?
            appearance.get_value('ayah-preset-options').deepUnpack() : [-1, -1, -1];
        const opacity = presetTransparency < 0 ? nativeOpacity : (100 - presetTransparency) / 100;
        const rgb = theme.background.slice(1).match(/../gu).map(value => parseInt(value, 16));
        return {...theme, size, width, opacity, textOpacity: 1, fill: `rgba(${rgb.join(',')},${opacity})`};
    }

    const custom = settingsSchema?.has_key('ayah-custom') ?
        appearance.get_value('ayah-custom').recursiveUnpack() : {};
    const base = SPEC.themes[custom.art_theme] ?? SPEC.custom;
    const [override, font] = settings.get_value('font-family-override').deepUnpack();
    const hasBorder = frame.get_boolean('show-border');
    const style = !hasBorder ? 'Minimal' : frame.get_int('border-radius') > 8 ? 'Glass' : 'Solid';
    const radius = base.style === style ? base.radius : !hasBorder ? 2 : style === 'Glass' ? 18 : 8;
    const border = base.style === style ? base.border : Number(hasBorder);
    return {...base, radius, border, font: override ? font : SPEC.custom.font,
        arabic_font: custom.arabic_font || SPEC.custom.arabic_font, arabicSize: custom.arabic_size,
        opacity: nativeOpacity, textOpacity: (custom.text_opacity ?? 100) / 100,
        fill: nativeOpacity ? background : 'transparent',
        text: settings.get_string('foreground-color').split(';', 1)[0],
        accent: settings.get_string('border-color').split(';', 1)[0]};
}

class AyahCard {
    constructor(frame, source, settings) {
        this.frame = frame;
        this.source = source;
        this.settings = settings;
        const schema = Gio.SettingsSchemaSource.get_default()?.lookup('io.github.desktopwidgets.Settings', true);
        this.appearance = schema?.has_key('ayah-theme') ? new Gio.Settings({settings_schema: schema}) : null;
        this.interface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});

        this.actor = new St.Widget({
            layout_manager: new Clutter.FixedLayout(), clip_to_allocation: true,
            x_align: Clutter.ActorAlign.START, y_align: Clutter.ActorAlign.START,
        });
        this.fill = new St.Widget();
        this.art = new St.Widget({layout_manager: new Clutter.FixedLayout(), clip_to_allocation: true});
        this.border = new St.Widget();
        this.footerFade = new St.Widget();
        this.footerTint = new St.Widget();
        this.rule = new St.Widget();
        this.labels = [label(0), label(1), label(2)];
        this.scroll = new St.ScrollView({overlay_scrollbars: true, clip_to_allocation: true,
            hscrollbar_policy: St.PolicyType.NEVER, vscrollbar_policy: St.PolicyType.AUTOMATIC});
        this.scroll.set_accessible_name('Ayah text');
        const body = new St.BoxLayout({vertical: true});
        this.scroll.set_child(body);
        this.textLayer = new St.Widget({layout_manager: new Clutter.FixedLayout()});
        body.add_child(this.textLayer);
        for (const child of [this.footerFade, this.footerTint, this.rule, ...this.labels])
            this.textLayer.add_child(child);
        for (const child of [this.fill, this.art, this.border, this.scroll])
            this.actor.add_child(child);
        this.scroll.connect('button-press-event', () => {
            this.scroll.grab_key_focus();
            return Clutter.EVENT_PROPAGATE;
        });
        this.scroll.connect('key-press-event', (_actor, event) => {
            const adjustment = this.scroll.vadjustment;
            switch (event.get_key_symbol()) {
            case Clutter.KEY_Page_Up: adjustment.value -= adjustment.page_size; break;
            case Clutter.KEY_Page_Down: adjustment.value += adjustment.page_size; break;
            case Clutter.KEY_Home: adjustment.value = adjustment.lower; break;
            case Clutter.KEY_End: adjustment.value = adjustment.upper - adjustment.page_size; break;
            default: return Clutter.EVENT_PROPAGATE;
            }
            return Clutter.EVENT_STOP;
        });

        // Keep AzClock's polling, error handling, and refresh command with its original label.
        source.opacity = 0;
        source.reactive = false;
        source.set_no_layout(true);
        source.set_size(0, 0);
        this.actor.add_child(source);

        const queue = () => {
            if (this.idle)
                return;
            this.idle = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this.idle = 0;
                this.refresh();
                return GLib.SOURCE_REMOVE;
            });
        };
        source.clutter_text.connectObject('notify::text', queue, this.actor);
        source.connectObject('notify::visible', queue, this.actor);
        settings.connectObject('changed', queue, this.actor);
        frame._settings.connectObject('changed', queue, this.actor);
        for (const key of ['ayah-theme', 'ayah-custom', 'ayah-preset-options']) {
            if (schema?.has_key(key))
                this.appearance.connectObject(`changed::${key}`, queue, this.actor);
        }
        this.interface.connectObject('changed::text-scaling-factor', queue, this.actor);
        St.ThemeContext.get_for_stage(global.stage).connectObject('changed', queue, this.actor);
        Main.layoutManager.connectObject('monitors-changed', queue, this.actor);
        global.display.connectObject('workareas-changed', queue, this.actor);

        this.actor.connect('destroy', () => {
            this.destroying = true;
            if (this.idle)
                GLib.source_remove(this.idle);
        });
        source.connect('destroy', () => {
            if (!this.destroying)
                this.actor.destroy();
        });
        queue();
    }

    workArea() {
        const location = JSON.parse(this.frame._settings.get_string('location-data'));
        const monitor = Main.layoutManager.monitors[location.monitorIndex] ?? Main.layoutManager.primaryMonitor;
        if (!monitor)
            return null;
        return {location, monitor, area: Main.layoutManager.getWorkAreaForMonitor(monitor.index)};
    }

    position(box) {
        const placement = this.workArea();
        if (!placement)
            return {x: 0, y: 0};
        const {location, monitor, area} = placement;
        const anchor = this.frame._settings.get_string('anchor-point');
        const width = box.get_width();
        const height = box.get_height();
        const offsetX = anchor.includes('Right') ? width : anchor.includes('Left') ? 0 : width / 2;
        const offsetY = anchor.includes('Bottom') ? height : anchor.includes('Top') ? 0 : height / 2;
        const clamp = (position, start, extent, size) =>
            Math.max(start + SIZING.margin, Math.min(position, start + extent - size - SIZING.margin));
        return {
            x: clamp(monitor.x + location.relativeX * monitor.width - offsetX, area.x, area.width, width),
            y: clamp(monitor.y + location.relativeY * monitor.height - offsetY, area.y, area.height, height),
        };
    }

    refresh() {
        this.actor.visible = this.source.visible;
        const {width: workWidth, height: workHeight} = this.workArea()?.area ?? global.stage;
        const theme = this.theme = palette(this.frame._settings, this.settings, this.appearance);
        const savedWidth = theme.width > 0 ? theme.width :
            Number(this.settings.get_string('background-color').match(WIDTH)?.[1] ?? SIZING.width);
        const width = Math.max(1, Math.min(Math.max(SIZING.min_width, savedWidth), SIZING.max_width, workWidth - 2 * SIZING.margin));
        const verse = verseFromText(this.source.clutter_text.text);
        if (this.verse?.some((text, i) => text !== verse[i]))
            this.scroll.vadjustment.value = 0;
        this.verse = verse;
        const size = theme.size > 0 ? theme.size : this.settings.get_int('font-size');
        const arabicSize = theme.arabicSize ?? size + SIZING.arabic_extra;
        const [top, , , left] = theme.padding;
        const arabicInset = theme.border + SIZING.arabic_padding;
        // Native colours can use CSS forms that Pango markup does not accept.
        const accentStyle = theme.accent;
        this.rule.style = `background-color: ${accentStyle}; color: ${theme.text};`;
        const colours = this.rule.get_theme_node();
        const accent = colours.get_background_color().to_string();
        theme.accent = accent.endsWith('ff') ? accent.slice(0, 7) : accent;
        const red = parseInt(colours.get_foreground_color().to_string().slice(1, 3), 16);
        const shadowRGB = red >= 128 ? '0,0,0' : '255,246,224';
        const shadow = `rgba(${shadowRGB},${Math.max(0.3, Math.min(0.8, 1 - theme.opacity))})`;
        const createLayout = index => this.labels[index].clutter_text.create_pango_layout('');
        const viewportHeight = Math.max(1, workHeight - 2 * SIZING.margin);
        const {markup, widths, heights, height: contentHeight} =
            fitVerse(verse, width, theme, arabicSize, size, createLayout, viewportHeight);
        const height = Math.min(contentHeight, viewportHeight);

        this.actor.set_size(width, height);
        place(this.scroll, 0, 0, width, height);
        this.textLayer.set_size(width, contentHeight);
        const overflow = contentHeight > height;
        this.scroll.set_mouse_scrolling(overflow);
        this.scroll.reactive = overflow;
        this.scroll.can_focus = overflow;
        place(this.fill, 0, 0, width, height);
        place(this.art, 0, 0, width, height);
        place(this.border, 0, 0, width, height);
        this.art.opacity = Math.round(theme.opacity * 255);
        this.border.opacity = Math.round(theme.opacity * 255);
        this.fill.style = `background-color: ${theme.fill}; border-radius: ${theme.radius}px;`;
        this.border.style = `border: ${theme.border}px solid ${accentStyle}; border-radius: ${theme.radius}px;`;
        const artKey = JSON.stringify([theme.art, width, height]);
        if (this.artKey !== artKey) {
            this.artKey = artKey;
            this.art.destroy_all_children();
            for (const art of theme.art ?? []) {
                const [vertical, horizontal] = art.anchor.split('-');
                const cornerScale = Math.min(1, width / SIZING.width);
                const scale = art.scenery ? Math.min(height / SIZING.height, SIZING.scenery_scale_max) : cornerScale;
                const w = Math.round(art.width * scale);
                const h = Math.round(w / art.ratio);
                const [x, y] = (art.inset ?? [0, 0]).map(offset => Math.round(offset * cornerScale));
                const layer = new St.Widget({opacity: Math.round(art.opacity * 255),
                    style: `background-image: url("${ART}${art.file}"); background-size: contain;`});
                place(layer, horizontal === 'left' ? x : width - w - x, vertical === 'top' ? y : height - h - y, w, h);
                this.art.add_child(layer);
            }
        }

        let y = top;
        let footerTop;
        this.rule.visible = Boolean(verse[0]);
        this.rule.opacity = Math.round(theme.textOpacity * 255);
        markup.forEach((value, i) => {
            const item = this.labels[i];
            item.visible = Boolean(value);
            item.opacity = Math.round(theme.textOpacity * 255);
            if (value) {
                const h = heights[i];
                const colour = i === 2 ? accentStyle : theme.text;
                item.style = `color: ${colour}; text-align: ${i === 0 ? 'right' : 'left'}; text-shadow: 0 1px 3px ${shadow};`;
                item.clutter_text.set_markup(value);
                place(item, i === 0 ? arabicInset : left, y, widths[i], h);
                y += h + SIZING.gap;
            }
            if (i === 0 && this.rule.visible) {
                place(this.rule, left, y, SIZING.rule_width, SIZING.rule_height);
                y += SIZING.rule_height + SIZING.gap;
            }
            if (i === 0)
                footerTop = y;
        });
        const tint = markup[0] && (markup[1] || markup[2]) ? SIZING.footer_tint * theme.opacity : 0;
        this.footerFade.visible = this.footerTint.visible = Boolean(tint);
        if (tint) {
            const colour = this.fill.get_theme_node().get_background_color().to_string().slice(0, 7);
            const opacity = Math.round(tint * 255);
            const fade = Math.min(SIZING.footer_fade, contentHeight - footerTop);
            this.footerFade.opacity = this.footerTint.opacity = opacity;
            this.footerFade.style = 'background-gradient-direction: vertical; ' +
                `background-gradient-start: transparent; background-gradient-end: ${colour};`;
            this.footerTint.style = `background-color: ${colour}; border-radius: 0 0 ${theme.radius}px ${theme.radius}px;`;
            place(this.footerFade, 0, footerTop, width, fade);
            place(this.footerTint, 0, footerTop + fade, width, contentHeight - footerTop - fade);
        }
    }
}

export function decorateAyah(frame, source, settings) {
    return new AyahCard(frame, source, settings);
}
