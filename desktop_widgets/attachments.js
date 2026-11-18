import GLib from 'gi://GLib';

import {measureTrack} from '../avatar/motion.js';

const OWNERS = {thread: 'ayah', knob: 'ayah', avatar: 'clock'};
const MANAGED = new Set(['ayah', 'clock', ...Object.keys(OWNERS)]);

export function sessionWidgets(ids, mode) {
    return mode === 'stopped' || mode === 'hidden' ? ids.filter(id => !MANAGED.has(id)) : ids;
}

export function displayedWidgets(ids) {
    if (['ayah', 'thread', 'knob'].every(id => ids.includes(id)))
        return ids;
    return ids.filter(id => id !== 'thread' && id !== 'knob');
}

export function cordPosition(id, card, width, threadHeight) {
    const x = card.x + card.width - Math.min(70, card.width / 2) - width / 2;
    const bottom = card.y + card.height;
    return {x, y: id === 'knob' ? bottom + threadHeight - 12 : bottom};
}

export function avatarPosition(card, width, height, track = null) {
    // These fractions locate the feet and right edge of the existing flipbook sprite.
    return {
        x: (track?.right ?? card.x + card.width) - 54 - width * 139 / 203,
        y: (track?.top ?? card.y + card.height - 24) - height * 239 / 282,
    };
}

export class WidgetAttachments {
    constructor(extension) {
        this.extension = extension;
        this.idle = 0;
        this.allocations = new WeakMap();
        this.following = new WeakSet();
        this.lightOn = false;
    }

    owner(widget) {
        return this.extension.widgets.get(OWNERS[widget._settingsId]);
    }

    onTopFor(widget) {
        return this.owner(widget)?._settings.get_boolean('always-on-top');
    }

    allocated(widget, box) {
        if (widget._settingsId !== 'ayah' && widget._settingsId !== 'clock')
            return;
        const key = [box.x1, box.y1, box.x2, box.y2].join();
        if (this.allocations.get(widget) !== key) {
            this.allocations.set(widget, key);
            this.refresh();
        }
    }

    positionFor(widget) {
        const owner = this.owner(widget);
        const parent = widget.get_parent();
        if (!owner?.has_allocation() || !parent)
            return null;
        const [x, y] = owner.get_transformed_position();
        const [width, height] = owner.get_transformed_size();
        if (width <= 0 || height <= 0)
            return null;
        const card = {x, y, width, height};
        const id = widget._settingsId;
        let result;
        if (id === 'avatar') {
            const label = owner._elements.get('card')?.clutter_text;
            const [avatarWidth, avatarHeight] = widget.get_transformed_size();
            const key = [x, y, width, height, label?.height].join();
            if (key !== this.trackKey || owner !== this.trackOwner) {
                this.trackKey = key;
                this.trackOwner = owner;
                this.track = null;
                if (label?.has_allocation()) {
                    const [textX, textY] = label.get_transformed_position();
                    const [offsetX, offsetY] = label.get_layout_offsets();
                    this.track = measureTrack(label.get_layout(), textX + offsetX, textY + offsetY, 0);
                }
            }
            result = avatarPosition(card, avatarWidth || 203, avatarHeight || 282, this.track);
        } else {
            const [partWidth] = widget.get_transformed_size();
            const thread = this.extension.widgets.get('thread');
            const threadHeight = thread?.get_transformed_size()[1] || 64;
            result = cordPosition(id, card, partWidth || (id === 'knob' ? 40 : 8), threadHeight);
        }
        const [ok, parentX, parentY] = parent.transform_stage_point(result.x, result.y);
        return ok ? {x: parentX, y: parentY} : null;
    }

    lightStyle(widget) {
        const elementId = {ayah: 'verse', clock: 'card'}[widget._settingsId];
        if (!this.lightOn || !elementId)
            return '';
        const colour = widget._elements.get(elementId)?._settings.get_string('border-color');
        const hex = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(colour);
        const rgb = /^(?:rgba?)\((\d+),\s*(\d+),\s*(\d+)[,)]/.exec(colour);
        const channels = hex ? hex.slice(1).map(value => parseInt(value, 16)) : rgb?.slice(1) ?? [230, 184, 102];
        return ` box-shadow: inset 0 0 18px 1px rgba(${channels.join(',')},0.20);`;
    }

    lightChanged() {
        const on = /\/knob-on(?:-[^/]+)?\.svg$/.test(this.knobSettings?.get_string('image-path') ?? '');
        if (on === this.lightOn)
            return;
        this.lightOn = on;
        for (const id of ['ayah', 'clock'])
            this.extension.widgets.get(id)?.setStyle();
        this.extension.widgets.get('ayah')?._elements.get('verse')?._refreshCommand?.();
    }

    refresh() {
        if (this.idle)
            return;
        this.idle = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.idle = 0;
            const knobSettings = this.extension.widgets.get('knob')?._elements.get('knob')?._settings;
            if (knobSettings !== this.knobSettings) {
                if (this.knobSignal)
                    this.knobSettings.disconnect(this.knobSignal);
                this.knobSettings = knobSettings;
                this.knobSignal = knobSettings?.connect('changed::image-path', () => this.lightChanged());
                this.lightChanged();
            }
            for (const id of Object.keys(OWNERS)) {
                const widget = this.extension.widgets.get(id);
                if (!widget)
                    continue;
                const owner = this.owner(widget);
                if (owner) {
                    this.following.add(widget);
                    if (!owner._isDragging && widget.get_parent() !== owner.get_parent())
                        widget._setParent();
                } else if (this.following.delete(widget)) {
                    widget._setParent();
                }
                const parent = widget.get_parent();
                if (id === 'avatar' && parent && parent === owner?.get_parent()) {
                    widget.z_position = Math.max(widget.z_position, owner.z_position + 0.5);
                    parent.set_child_above_sibling(widget, owner);
                }
                widget.queue_relayout();
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    destroy() {
        if (this.idle)
            GLib.source_remove(this.idle);
        this.idle = 0;
        if (this.knobSignal)
            this.knobSettings.disconnect(this.knobSignal);
    }
}
