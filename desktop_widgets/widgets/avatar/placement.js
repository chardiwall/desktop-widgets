import {overlaps, placeOnTrack} from './motion.js';

export function resolveAvatarPlacement({visible, body, clock, windows = []}, sprite) {
    if (!visible)
        return {kind: 'hidden'};

    const sameDisplay = body?.monitor >= 0 && clock?.monitor === body.monitor;
    if (sameDisplay && clock.dragging)
        return {kind: 'hidden'};
    if (!body || clock?.pending || (sameDisplay && clock.trackPending))
        return {kind: 'pending'};

    if (sameDisplay && clock.track && clock.area) {
        const perch = placeOnTrack(clock.track, clock.area, sprite, clock.rightWall);
        if (perch) {
            return {kind: 'perched', ...perch,
                routeCovered: perch.canWalk && windows.some(window => overlaps(perch, window))};
        }
    }

    return {kind: 'standalone', x: body.x + (body.width - sprite.width) / 2,
        y: body.y + body.height - sprite.height, width: sprite.width, height: sprite.height,
        canWalk: false, routeCovered: false, seatShift: 0};
}
