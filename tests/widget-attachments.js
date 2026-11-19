import {displayedWidgets, sessionWidgets} from '../desktop_widgets/bridge/attachments.js';

function equal(actual, expected) {
    if (JSON.stringify(actual) !== JSON.stringify(expected))
        throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

equal(displayedWidgets(['knob', 'avatar', 'thread', 'clock', 'ayah']), ['avatar', 'clock', 'ayah']);
equal(displayedWidgets(['ayah', 'thread', 'other']), ['ayah', 'other']);

const configured = ['clock', 'avatar', 'ayah', 'thread', 'knob', 'another-widget'];
equal(sessionWidgets(configured, 'running'), configured);
equal(displayedWidgets(sessionWidgets(configured, 'running')), ['clock', 'avatar', 'ayah', 'another-widget']);
equal(displayedWidgets(sessionWidgets(configured, 'hidden')), ['another-widget']);
equal(displayedWidgets(sessionWidgets(configured, 'stopped')), ['another-widget']);
print('Widget session visibility checks passed.');
