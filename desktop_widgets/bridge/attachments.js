const MANAGED = new Set(['ayah', 'clock', 'avatar']);

export function sessionWidgets(ids, mode) {
    return mode === 'stopped' || mode === 'hidden' ? ids.filter(id => !MANAGED.has(id)) : ids;
}

export function displayedWidgets(ids) {
    // Older AzClock configurations can still contain the retired pull-cord widgets.
    return ids.filter(id => id !== 'thread' && id !== 'knob');
}
