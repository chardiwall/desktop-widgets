import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {sessionWidgets} from './attachments.js';

const APP_ID = 'io.github.desktopwidgets.Settings';
const MODE = 'session-mode';
const SHELL_SESSION = GLib.uuid_string_random();
const WIDGETS = [['ayah', 'Ayah reminder'], ['clock', 'Clock'], ['avatar', 'Avatar']];

export class WidgetIndicator {
    constructor(extension) {
        this.extension = extension;
        const schema = Gio.SettingsSchemaSource.get_default()?.lookup(APP_ID, true);
        if (!schema)
            return;

        this.session = new Gio.Settings({settings_schema: schema});
        if (this.session.get_string('shell-session') !== SHELL_SESSION) {
            this.session.set_boolean('resume-legacy-avatar', false);
            this.session.set_string(MODE, 'running');
            this.session.set_string('shell-session', SHELL_SESSION);
        }
        this.button = new PanelMenu.Button(0.5, 'Desktop Widgets');
        this.button.add_child(new St.Icon({icon_name: APP_ID + '-symbolic', style_class: 'system-status-icon'}));
        this.button.menu.addAction('Open Settings', () => {
            const app = Shell.AppSystem.get_default().lookup_app(APP_ID + '.desktop');
            if (app)
                app.activate();
            else
                Main.notifyError('Desktop Widgets', 'The settings app could not be found.');
        });

        this.quick = new PopupMenu.PopupMenuSection();
        this.button.menu.addMenuItem(this.quick);
        this.switches = new Map();
        for (const [id, label] of WIDGETS) {
            const item = new PopupMenu.PopupSwitchMenuItem(label, false);
            item.connect('toggled', (_, enabled) => this.run(['--set-widget', id, enabled ? 'on' : 'off']));
            this.quick.addMenuItem(item);
            this.switches.set(id, item);
        }
        this.visibility = this.quick.addAction('Hide all widgets', () => {
            const next = this.mode === 'hidden' ? 'running' : 'hidden';
            if (!this.session.set_string(MODE, next))
                Main.notifyError('Desktop Widgets', 'The widget session setting is read-only.');
        });
        this.button.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.button.menu.addAction('Quit Desktop Widgets', () => this.run(['--quit-widgets']));

        this.button.connect('captured-event', (_, event) => {
            if (event.type() !== Clutter.EventType.BUTTON_PRESS || event.get_button() !== 3)
                return Clutter.EVENT_PROPAGATE;
            this.quick.actor.hide();
            this.button.menu.toggle();
            return Clutter.EVENT_STOP;
        });
        this.button.menu.connect('open-state-changed', (_, open) => {
            if (!open)
                this.quick.actor.show();
        });
        this.sessionChanged = this.session.connect('changed::' + MODE, () => {
            this.extension._createWidgets();
        });
        Main.panel.addToStatusArea('desktop-widgets-lantern', this.button);
        this.refresh();
    }

    get mode() {
        return this.session?.get_string(MODE) ?? 'running';
    }

    displayedWidgets(ids) {
        return sessionWidgets(ids, this.mode);
    }

    refresh() {
        if (!this.button)
            return;
        const mode = this.mode;
        this.button.visible = mode !== 'stopped';

        const flags = Object.assign({}, ...this.extension.settings.get_value('widgets').recursiveUnpack());
        for (const [id, item] of this.switches) {
            item.setToggleState(flags[id]?.enabled === true);
            item.setSensitive(Boolean(flags[id]));
        }
        this.visibility.label.text = mode === 'hidden' ? 'Show all widgets' : 'Hide all widgets';
    }

    run(args) {
        if (this.pending) {
            this.refresh();
            return;
        }
        try {
            const process = Gio.Subprocess.new(['desktop-widget-settings', ...args], Gio.SubprocessFlags.STDERR_PIPE);
            this.pending = true;
            process.communicate_utf8_async(null, null, (subprocess, result) => {
                this.pending = false;
                try {
                    const [, , errorOutput] = subprocess.communicate_utf8_finish(result);
                    if (!subprocess.get_successful())
                        throw new Error(errorOutput?.trim() || 'The action could not be completed.');
                } catch (error) {
                    Main.notifyError('Desktop Widgets', error.message);
                }
                this.refresh();
            });
        } catch (error) {
            this.pending = false;
            Main.notifyError('Desktop Widgets', error.message);
            this.refresh();
        }
    }

    destroy() {
        if (this.sessionChanged)
            this.session.disconnect(this.sessionChanged);
        this.button?.destroy();
        this.button = null;
    }
}
