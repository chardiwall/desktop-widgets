import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {listeningFrame} from './motion.js';
import {listening} from './walk-data.js';

const NOTES = ['♪', '♫', '♪'];
const DROPS = 14;
const SAMPLE_US = 1000000 / 24;

function illustration(width, height, paint) {
    const area = new St.DrawingArea({width, height, visible: false});
    area.connect('repaint', () => {
        const context = area.get_context();
        paint(context);
        context.$dispose();
    });
    return area;
}

function headphones(context) {
    context.setSourceRGBA(0.12, 0.17, 0.22, 0.97);
    context.setLineWidth(4);
    context.arc(34, 34, 29, Math.PI, 2 * Math.PI);
    context.stroke();
    for (const x of [3, 64]) {
        context.arc(x, 34, 6, 0, 2 * Math.PI);
        context.fill();
        context.setSourceRGBA(0.78, 0.69, 0.54, 1);
        context.arc(x, 34, 2.5, 0, 2 * Math.PI);
        context.fill();
        context.setSourceRGBA(0.12, 0.17, 0.22, 0.97);
    }
}

function umbrella(context) {
    context.setSourceRGBA(0.21, 0.36, 0.40, 0.98);
    context.moveTo(3, 42);
    context.curveTo(21, -4, 91, -4, 109, 42);
    for (const x of [109, 74, 39])
        context.curveTo(x - 8, 35, x - 25, 35, x - 35, 42);
    context.closePath();
    context.fillPreserve();
    context.setSourceRGBA(0.72, 0.85, 0.85, 1);
    context.setLineWidth(2);
    context.stroke();
    context.moveTo(56, 38);
    context.lineTo(56, 100);
    context.curveTo(56, 108, 46, 108, 46, 102);
    context.stroke();
}

export class ListeningScene {
    constructor(actor, onIdle) {
        this.actor = actor;
        this.onIdle = onIdle;
        this.phase = 0;
        this.loop = 0;
        this.headset = 0;
        this.canopy = 0;
        this.mode = 'none';
        this.rain = false;
    }

    get busy() {
        return this.phase > 0 || this.headset > 0 || this.canopy > 0;
    }

    buildProps() {
        this.headphones = illustration(70, 44, headphones);
        this.umbrella = illustration(112, 110, umbrella);
        this.umbrella.set_pivot_point(0.5, 0.96);
        this.notes = NOTES.map(text => new St.Label({
            text, visible: false, style: 'font-size: 16px; color: #e7ce9e;',
        }));
        for (const part of [this.headphones, this.umbrella, ...this.notes])
            this.actor.add_child(part);
        this.rainLayer = new Clutter.Actor({clip_to_allocation: true, visible: false});
        this.drops = Array.from({length: DROPS}, () => new St.Widget({
            width: 2, height: 11, rotation_angle_z: 13,
            style: 'background-color: rgba(152, 207, 228, 0.46); border-radius: 1px;',
        }));
        for (const drop of this.drops)
            this.rainLayer.add_child(drop);
    }

    configure(view, mode, rain, animated) {
        if (!listening)
            return;
        this.mode = mode;
        this.rain = rain;
        this.view = view;
        if (!this.frames || (!rain && mode === 'none' && !this.busy))
            return;
        if (!this.headphones)
            this.buildProps();

        const {card} = view;
        if ((rain || this.canopy > 0) && card) {
            const parent = this.actor.get_parent();
            if (parent !== this.rainLayer.get_parent()) {
                this.rainLayer.get_parent()?.remove_child(this.rainLayer);
                parent.add_child(this.rainLayer);
            }
            this.rainLayer.set_position(card.x, card.y);
            this.rainLayer.set_size(card.width, card.height);
            this.rainLayer.z_position = this.actor.z_position - 0.25;
        }
        this.rainLayer.visible = Boolean((rain || this.canopy > 0) && card);
        if (!animated) {
            this.stopTimeline();
            this.phase = rain || mode !== 'none' ? 1 : 0;
            this.headset = mode !== 'none' ? 1 : 0;
            this.canopy = rain ? 1 : 0;
            this.paint(0);
        } else if (!this.timeline) {
            this.startTimeline();
        }
    }

    startTimeline() {
        this.last = GLib.get_monotonic_time();
        this.nextPaint = this.last + SAMPLE_US;
        this.time = 0;
        const timeline = Clutter.Timeline.new_for_actor(this.actor, 2400);
        timeline.set_repeat_count(-1);
        this.timeline = timeline;
        this.frameSignal = timeline.connect('new-frame', () => {
            const now = GLib.get_monotonic_time();
            if (now < this.nextPaint)
                return;
            this.nextPaint += (Math.floor((now - this.nextPaint) / SAMPLE_US) + 1) * SAMPLE_US;
            const delta = (now - this.last) / 1000000;
            this.last = now;
            this.time += delta;
            const audio = this.mode !== 'none';
            const target = audio || this.rain;
            const duration = listening.seated / listening.fps;
            this.phase = Math.max(0, Math.min(1, this.phase + (target ? delta : -delta) / duration));
            this.headset = Math.max(0, Math.min(1, this.headset + (audio ? delta : -delta) * 5));
            this.canopy = Math.max(0, Math.min(1, this.canopy + (this.rain ? delta : -delta) * 3));
            this.loop = this.phase === 1 && audio ? this.loop + delta : 0;
            this.paint(this.time);
            if (!target && !this.busy) {
                this.stopTimeline();
                this.onIdle();
            }
        });
        timeline.start();
    }

    paint(time) {
        const frame = listeningFrame(listening, this.phase, this.loop);
        const {head, hand, ground} = listening.anchors[frame];
        const progress = this.phase ** 2 * (3 - 2 * this.phase);
        this.actor.translation_x = this.view.seatShift * progress;
        this.actor.translation_y = -ground;
        if (this.actor.content !== this.frames[frame])
            this.actor.content = this.frames[frame];
        this.headphones.set_position(head[0] - 35, head[1] - 33);
        this.headphones.opacity = Math.round(this.headset * 255);
        this.headphones.visible = this.headset > 0;
        this.umbrella.set_position(hand[0] - 56, hand[1] - 101);
        this.umbrella.set_scale(0.15 + this.canopy * 0.85, 0.15 + this.canopy * 0.85);
        this.umbrella.opacity = Math.round(this.canopy * 255);
        this.umbrella.visible = this.canopy > 0;
        this.rainLayer.opacity = Math.round(this.canopy * 255);
        this.rainLayer.visible = Boolean(this.canopy > 0 && this.view.card);

        this.notes.forEach((note, index) => {
            const rise = (time * 0.66 + index / NOTES.length) % 1;
            note.set_position(head[0] + 29 + 17 * rise + index * 4, head[1] - 9 - 48 * rise);
            note.opacity = Math.round(230 * this.headset * (1 - rise));
            note.visible = this.headset > 0;
        });
        if (this.rainLayer.visible) {
            const {width, height} = this.view.card;
            this.drops.forEach((drop, index) => {
                const fall = (time * (0.8 + index % 4 * 0.14) + index * 0.37) % 1;
                drop.set_position((index + 0.5) * width / DROPS - 18 * fall, fall * (height + 11) - 11);
            });
        }
    }

    stopTimeline() {
        if (!this.timeline)
            return;
        this.timeline.disconnect(this.frameSignal);
        this.timeline.stop();
        this.timeline = null;
    }

    reset() {
        this.stopTimeline();
        this.phase = this.loop = this.headset = this.canopy = 0;
        this.frames = null;
        this.actor.translation_y = 0;
        this.rainLayer?.hide();
        this.umbrella?.hide();
        this.headphones?.hide();
        for (const note of this.notes ?? [])
            note.hide();
    }

    destroy() {
        this.reset();
        this.rainLayer?.destroy();
    }
}
