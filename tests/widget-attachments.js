import GLib from 'gi://GLib';
import {WidgetAttachments, avatarPosition, cordPosition, displayedWidgets, sessionWidgets} from '../desktop_widgets/attachments.js';

function equal(actual, expected) {
    if (JSON.stringify(actual) !== JSON.stringify(expected))
        throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

const ayah = {x: 1100, y: 70, width: 720, height: 245};
equal(cordPosition('thread', ayah, 8, 64), {x: 1746, y: 315});
equal(cordPosition('knob', ayah, 40, 64), {x: 1730, y: 367});
equal(cordPosition('knob', {...ayah, x: -700, height: 290}, 40, 64), {x: -70, y: 412});
equal(displayedWidgets(['knob', 'avatar', 'thread', 'clock']), ['avatar', 'clock']);
equal(displayedWidgets(['knob', 'ayah', 'clock']), ['ayah', 'clock']);
equal(displayedWidgets(['knob', 'avatar', 'thread', 'clock', 'ayah']), ['knob', 'avatar', 'thread', 'clock', 'ayah']);
const clock = {x: 1100, y: 600, width: 696, height: 244};
equal(avatarPosition(clock, 203, 282, {right: 1740, top: 790}), {x: 1547, y: 551});
equal(avatarPosition({...clock, x: -700, y: 142}, 203, 282), {x: -197, y: 123});

const events = [];
const parent = {set_child_above_sibling(child, sibling) { events.push([child.id, sibling.id]); }};
const clockActor = {id: 'clock', z_position: 5, get_parent: () => parent};
const avatarActor = {id: 'avatar', _settingsId: 'avatar', z_position: 0, get_parent: () => parent,
    queue_relayout() {}, _setParent() { events.push('fallback'); }};
const widgets = new Map([['clock', clockActor], ['avatar', avatarActor]]);
const attachments = new WidgetAttachments({widgets});
for (let index = 0; index < 2; index++) {
    avatarActor.z_position = 0;
    attachments.refresh();
    while (attachments.idle)
        GLib.MainContext.default().iteration(false);
    equal(avatarActor.z_position, 5.5);
}
widgets.delete('clock');
attachments.refresh();
while (attachments.idle)
    GLib.MainContext.default().iteration(false);
equal(events, [['avatar', 'clock'], ['avatar', 'clock'], 'fallback']);
attachments.destroy();
print('Widget attachment geometry passed.');

const managed = ['clock', 'avatar', 'ayah', 'thread', 'knob', 'another-widget'];
equal(sessionWidgets(managed, 'running'), managed);
equal(sessionWidgets(managed, 'hidden'), ['another-widget']);
equal(sessionWidgets(managed, 'stopped'), ['another-widget']);
