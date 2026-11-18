import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Mtk from 'gi://Mtk';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {ListeningScene} from './listening.js';
import {measureTrack, overlaps, placeOnTrack, sampleWalk} from './motion.js';
import {listening, walk} from './walk-data.js';

Gio._promisify(Gio.File.prototype, 'load_bytes_async');

const ROW_BYTES = walk.width * 4;
const FRAME_BYTES = ROW_BYTES * walk.height;
const PLAYER_ID = 'io.github.desktopwidgets.Media';
const PLAYER_PATH = '/io/github/desktopwidgets/Media';

function upload(bytes) {
    const image = new St.ImageContent();
    const cogl = global.stage.context.get_backend().get_cogl_context();
    if (!image.set_bytes(cogl, bytes, Cogl.PixelFormat.RGBA_8888, walk.width, walk.height, ROW_BYTES))
        throw new Error('Avatar texture upload failed');
    return image;
}

export class AvatarPilot {
    constructor(extension) {
        this.extension = extension;
        this.signals = new Map();
        this.windows = new Set();
        this.paused = false;
        this.request = null;
        this.timeline = null;
        this.timer = 0;
        this.refreshId = 0;
        this.geometry = null;
        this.rest = null;
        this.failed = false;
        this.playback = 'none';
        this.rain = false;

        try {
            this.setup();
        } catch (error) {
            this.disablePilot(error);
        }
    }

    setup() {
        this.actor = new Clutter.Actor({width: walk.width, height: walk.height, visible: false});
        this.listeningScene = new ListeningScene(this.actor, () => this.refresh());
        const button = new St.Button({accessible_name: 'Desktop avatar', can_focus: true, reactive: true});
        button.set_size(Math.floor(walk.width * 0.55), Math.floor(walk.height * 0.72));
        button.set_position((walk.width - button.width) / 2, walk.height * 0.1);
        this.actor.add_child(button);
        this.menu = new PopupMenu.PopupMenu(button, 0.5, St.Side.BOTTOM);
        this.menuManager = new PopupMenu.PopupMenuManager(button);
        this.menuManager.addMenu(this.menu);
        this.walkItem = this.menu.addAction('Show a walk', () => this.startWalk());
        this.menu.addAction('Music player…', () => this.openPlayer('music'));
        this.menu.addAction('القرآن · Al-Minshawi…', () => this.openPlayer('quran'));
        const rain = new PopupMenu.PopupSwitchMenuItem('Rain inside the clock', false);
        rain.setSensitive(Boolean(listening));
        this.menu.addMenuItem(rain);
        rain.connect('toggled', (_item, enabled) => {
            this.rain = enabled;
            this.refresh();
        });
        const pause = new PopupMenu.PopupSwitchMenuItem('Pause ambient activity', this.paused);
        this.menu.addMenuItem(pause);
        pause.connect('toggled', (_item, paused) => {
            this.paused = paused;
            this.schedule();
        });
        Main.uiGroup.add_child(this.menu.actor);
        this.menu.actor.hide();
        button.connect('clicked', () => this.menu.toggle());
        this.menu.connect('open-state-changed', () => this.schedule());

        this.animationSettings = St.Settings.get();
        this.watch(this.animationSettings, 'notify::enable-animations');
        this.watch(Main.sessionMode, 'updated');
        this.watch(Main.overview, 'showing', 'hidden');
        this.watch(Main.layoutManager, 'monitors-changed');
        this.watch(global.workspace_manager, 'active-workspace-changed');
        this.watch(global.display, 'restacked', 'workareas-changed');
        this.watch(global.window_group, 'child-added', 'child-removed');
        this.playerWatch = Gio.bus_watch_name(Gio.BusType.SESSION, PLAYER_ID, Gio.BusNameWatcherFlags.NONE,
            (connection, _name, owner) => this.watchPlayer(connection, owner),
            () => this.unwatchPlayer());
        this.refresh();
    }

    openPlayer(section) {
        try {
            const path = this.extension.dir.resolve_relative_path('avatar/media-player.py').get_path();
            const player = Gio.AppInfo.create_from_commandline(
                `/usr/bin/python3 ${GLib.shell_quote(path)} ${GLib.shell_quote(section)}`,
                'Avatar audio', Gio.AppInfoCreateFlags.SUPPORTS_STARTUP_NOTIFICATION);
            player.launch([], global.create_app_launch_context(global.get_current_time(), -1));
        } catch (error) {
            Main.notify('Avatar audio', error.message);
        }
    }

    watchPlayer(connection, owner) {
        this.unwatchPlayer();
        this.player = Gio.DBusActionGroup.get(connection, owner, PLAYER_PATH);
        const update = () => {
            const state = this.player.get_action_state('now-playing')?.deepUnpack();
            this.playback = state === 'music' || state === 'quran' ? state : 'none';
            this.refresh();
        };
        this.playerSignals = [
            this.player.connect('action-added', update),
            this.player.connect('action-state-changed', update),
        ];
        update();
    }

    unwatchPlayer() {
        for (const id of this.playerSignals ?? [])
            this.player.disconnect(id);
        this.playerSignals = [];
        this.player = null;
        this.playback = 'none';
        this.refresh();
    }

    watch(object, ...signals) {
        const ids = [];
        this.signals.set(object, ids);
        for (const signal of signals) {
            ids.push(object.connect(signal, () => {
                if (signal !== 'notify::text' || !this.hidden)
                    this.refresh();
            }));
        }
        if (object instanceof Clutter.Actor) {
            ids.push(object.connect('destroy', () => {
                this.signals.delete(object);
                if (object === this.body) {
                    this.body = null;
                    this.suspend();
                }
                this.refresh();
            }));
        }
    }

    unwatch(object) {
        for (const id of this.signals.get(object) ?? [])
            object.disconnect(id);
        this.signals.delete(object);
    }

    followWindows() {
        const windows = new Set(global.get_window_actors());
        for (const actor of this.windows) {
            if (!windows.has(actor))
                this.unwatch(actor);
        }
        for (const actor of windows) {
            if (!this.windows.has(actor))
                this.watch(actor, 'notify::allocation', 'notify::mapped');
        }
        this.windows = windows;
    }

    refresh() {
        if (!this.actor || this.refreshId)
            return;
        this.refreshId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this.refreshId = 0;
            try {
                this.update();
            } catch (error) {
                this.disablePilot(error);
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    update() {
        this.followWindows();
        const {widgets} = this.extension;
        const clock = widgets.get('clock');
        const avatar = widgets.get('avatar');
        const label = clock?._elements.get('card')?.clutter_text;
        const body = avatar?._elements.get('body');
        const watched = new Set([clock, avatar, label, body].filter(Boolean));
        for (const object of this.watched ?? []) {
            if (!watched.has(object))
                this.unwatch(object);
        }
        for (const object of watched) {
            if (!this.watched?.has(object)) {
                if (object === label)
                    this.watch(object, 'notify::allocation', 'notify::text');
                else
                    this.watch(object, 'notify::allocation', 'notify::mapped', 'parent-set');
            }
        }
        this.watched = watched;
        if (body !== this.body) {
            if (this.body && this.body.get_parent())
                this.body.opacity = this.bodyOpacity;
            this.body = body;
            this.bodyOpacity = body?.opacity;
        }

        const anchor = clock?.mapped ? clock : avatar;
        const parent = anchor?.get_parent();
        const blocked = !avatar?.mapped || !body?.mapped || !parent ||
            Main.sessionMode.isLocked || Main.overview.visible || clock?._isDragging;
        const geometry = blocked || !body.has_allocation() ? null : this.locate(clock, label, body);
        const aboveWindows = parent === Main.uiGroup;
        this.hidden = blocked || (geometry && !aboveWindows && this.covered(geometry));
        if (!geometry || this.hidden) {
            this.suspend();
            return;
        }
        const [success, x, y] = parent.transform_stage_point(geometry.x, geometry.y);
        if (!success) {
            this.suspend();
            return;
        }
        let card = null;
        if (clock?.mapped && clock.has_allocation()) {
            const [cardX, cardY] = clock.get_transformed_position();
            const [ok, localX, localY] = parent.transform_stage_point(cardX, cardY);
            const [width, height] = clock.get_transformed_size();
            if (ok)
                card = {x: localX, y: localY, width, height};
        }
        const key = [x, y, geometry.width, geometry.height, card?.x, card?.y, card?.width,
            card?.height, this.animationSettings.enable_animations].join();
        if (parent !== this.actor.get_parent() || key !== this.geometry?.key) {
            this.suspend();
            if (parent !== this.actor.get_parent()) {
                this.actor.get_parent()?.remove_child(this.actor);
                parent.add_child(this.actor);
            }
            this.actor.set_position(x, y);
            this.geometry = {...geometry, card, seatShift: geometry.seatShift ?? 0, key};
        }
        this.actor.z_position = anchor.z_position + 0.5;
        if (this.rest) {
            this.body.opacity = 0;
            this.actor.show();
        } else if (!this.request && !this.failed) {
            this.loadRest();
        }
        this.walkItem.setSensitive(this.canWalk());
        if (!this.canWalk())
            this.clearTimer();
        if (!this.timer)
            this.schedule();
        this.updateListening();
    }

    locate(clock, label, body) {
        const [bodyX, bodyY] = body.get_transformed_position();
        const [bodyWidth, bodyHeight] = body.get_transformed_size();
        if (clock?.mapped && label?.mapped && label.has_allocation()) {
            const [x, y] = label.get_transformed_position();
            const [offsetX, offsetY] = label.get_layout_offsets();
            const track = measureTrack(label.get_layout(), x + offsetX, y + offsetY, walk.pivot[1]);
            if (track) {
                const monitor = global.display.get_monitor_index_for_rect(
                    new Mtk.Rectangle({x: Math.round(track.right - 1), y: Math.round(track.top), width: 1, height: 1}));
                if (Main.layoutManager.monitors[monitor]) {
                    const [clockX] = clock.get_transformed_position();
                    const [clockWidth] = clock.get_transformed_size();
                    const geometry = placeOnTrack(track, Main.layoutManager.getWorkAreaForMonitor(monitor),
                        walk, clockX + clockWidth - 2);
                    if (geometry)
                        return geometry;
                }
            }
        }
        return {x: bodyX + (bodyWidth - walk.width) / 2, y: bodyY + bodyHeight - walk.height,
            width: walk.width, height: walk.height, canWalk: false};
    }

    covered(geometry) {
        const workspace = global.workspace_manager.get_active_workspace();
        // shortcut: any intersecting window suppresses the pilot, refine for partial occlusion after profiling.
        return [...this.windows].some(actor => {
            const window = actor.meta_window;
            return actor.mapped && window && !window.minimized &&
                window.get_window_type() !== Meta.WindowType.DESKTOP &&
                window.located_on_workspace(workspace) && overlaps(geometry, window.get_frame_rect());
        });
    }

    canWalk() {
        return Boolean(this.geometry?.canWalk && this.rest && !this.failed && !this.request &&
            !this.timeline && !this.wantsListening() && !this.listeningScene?.busy &&
            this.animationSettings.enable_animations);
    }

    wantsListening() {
        return Boolean(listening && (this.rain || this.playback !== 'none'));
    }

    updateListening() {
        if (!listening || this.timeline || !this.geometry || !this.rest)
            return;
        const effect = this.listeningScene;
        if (this.wantsListening() && !effect.frames && !this.request && !this.listeningFailed)
            this.loadListening();
        effect.configure(this.geometry, this.playback, this.rain, this.animationSettings.enable_animations);
    }

    async loadListening() {
        const request = new Gio.Cancellable();
        this.request = request;
        try {
            const count = listening.anchors.length - 1;
            const bytes = await this.readFrames('listening', count, request);
            if (this.request !== request)
                return;
            const frames = await this.prepareTextures(bytes, count);
            if (this.request === request && frames)
                this.listeningScene.frames = [this.rest, ...frames];
        } catch (error) {
            if (this.request === request) {
                this.listeningFailed = true;
                console.warn(`Avatar listening pose: ${error.message}`);
            }
        } finally {
            this.finishRequest(request);
            this.refresh();
        }
    }

    async loadRest() {
        const request = new Gio.Cancellable();
        this.request = request;
        try {
            const bytes = await this.readFrames('rest', 1, request);
            if (this.request === request) {
                this.rest = upload(bytes);
                this.actor.content = this.rest;
                this.body.opacity = 0;
                this.actor.show();
            }
        } catch (error) {
            this.assetError(request, error);
        } finally {
            this.finishRequest(request);
            this.refresh();
        }
    }

    async startWalk() {
        if (!this.canWalk())
            return;
        this.clearTimer();
        const request = new Gio.Cancellable();
        this.request = request;
        try {
            const count = walk.travel.length - 2;
            const bytes = await this.readFrames('walk', count, request);
            if (this.request !== request)
                return;
            const frames = await this.prepareTextures(bytes, count);
            if (this.request === request && frames)
                this.play([this.rest, ...frames, this.rest]);
        } catch (error) {
            this.assetError(request, error);
        } finally {
            this.finishRequest(request);
        }
    }

    async readFrames(name, count, request) {
        const file = this.extension.dir.resolve_relative_path(`avatar/${name}.rgba`);
        const [bytes] = await file.load_bytes_async(request);
        if (bytes.get_size() !== FRAME_BYTES * count)
            throw new Error(`Unexpected size for avatar ${name} pixels`);
        return bytes;
    }

    prepareTextures(bytes, count) {
        return new Promise((resolve, reject) => {
            const frames = [];
            const id = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                try {
                    const offset = frames.length * FRAME_BYTES;
                    frames.push(upload(GLib.Bytes.new_from_bytes(bytes, offset, FRAME_BYTES)));
                    if (frames.length < count)
                        return GLib.SOURCE_CONTINUE;
                    resolve(frames);
                } catch (error) {
                    reject(error);
                }
                this.cancelUpload = null;
                return GLib.SOURCE_REMOVE;
            });
            this.cancelUpload = () => {
                GLib.Source.remove(id);
                this.cancelUpload = null;
                resolve(null);
            };
        });
    }

    assetError(request, error) {
        if (this.request !== request)
            return;
        this.failed = true;
        console.warn(`Avatar pilot: ${error.message}`);
    }

    finishRequest(request) {
        if (this.request !== request)
            return;
        this.request = null;
        this.walkItem.setSensitive(this.canWalk());
        this.schedule();
    }

    play(frames) {
        const duration = Math.ceil((frames.length - 1) * 1000 / walk.fps);
        const timeline = Clutter.Timeline.new_for_actor(this.actor, duration);
        this.timeline = timeline;
        let current = 0;
        this.timelineSignals = [
            timeline.connect('new-frame', (_timeline, elapsed) => {
                const {frame, x} = sampleWalk(elapsed, walk);
                this.actor.translation_x = x;
                if (frame !== current) {
                    current = frame;
                    this.actor.content = frames[frame];
                }
            }),
            timeline.connect('completed', () => {
                this.stopWalk();
                this.refresh();
            }),
        ];
        timeline.start();
    }

    stopWalk() {
        if (this.timeline) {
            for (const id of this.timelineSignals)
                this.timeline.disconnect(id);
            this.timeline.stop();
            this.timeline = null;
            this.timelineSignals = [];
        }
        this.actor.translation_x = 0;
        this.actor.content = this.rest;
    }

    clearTimer() {
        if (this.timer) {
            GLib.Source.remove(this.timer);
            this.timer = 0;
        }
    }

    schedule() {
        this.clearTimer();
        if (!this.canWalk() || this.paused || this.menu.isOpen)
            return;
        this.timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 60 + Math.floor(Math.random() * 121), () => {
            this.timer = 0;
            this.startWalk();
            return GLib.SOURCE_REMOVE;
        });
    }

    suspend() {
        const active = this.geometry || this.request || this.timeline;
        this.geometry = null;
        this.clearTimer();
        if (!active && !this.actor?.visible)
            return;
        this.request?.cancel();
        this.request = null;
        this.cancelUpload?.();
        this.listeningScene?.reset();
        this.stopWalk();
        this.menu?.close();
        this.actor.hide();
    }

    disablePilot(error) {
        console.warn(`Avatar pilot disabled: ${error.message}`);
        this.destroy();
    }

    destroy() {
        if (this.refreshId)
            GLib.Source.remove(this.refreshId);
        this.refreshId = 0;
        for (const object of this.signals.keys())
            this.unwatch(object);
        this.suspend();
        if (this.playerWatch)
            Gio.bus_unwatch_name(this.playerWatch);
        this.playerWatch = 0;
        for (const id of this.playerSignals ?? [])
            this.player.disconnect(id);
        this.playerSignals = [];
        this.player = null;
        this.listeningScene?.destroy();
        this.listeningScene = null;
        if (this.body && this.body.get_parent())
            this.body.opacity = this.bodyOpacity;
        this.body = null;
        if (this.menu) {
            this.menuManager?.removeMenu(this.menu);
            this.menu.destroy();
            this.menu = null;
        }
        this.actor?.destroy();
        this.actor = null;
        this.rest = null;
    }
}
