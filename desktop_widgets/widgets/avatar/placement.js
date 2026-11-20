import {overlaps, placeOnTrack} from './motion.js';

export function resolveAvatarPlacement({visible, body, clock, windows = []}, sprite, seat) {
    if (!visible)
        return {kind: 'hidden'};

    const sameDisplay = body?.monitor >= 0 && clock?.monitor === body.monitor;
    if (sameDisplay && clock.dragging)
        return {kind: 'hidden'};
    if (!body || clock?.pending || (sameDisplay && clock.trackPending))
        return {kind: 'pending'};

    if (sameDisplay && clock.track && clock.area) {
        const {track, area} = clock;
        const mirrored = clock.perchSide === 'left';
        // Reflect the coordinate system so both sides use the same walk and seat constraints.
        const perch = mirrored ? placeOnTrack({
            right: -track.left, top: track.top,
            ranges: track.ranges.map(([left, right]) => [-right, -left]).reverse(),
        }, {...area, x: -area.x - area.width}, sprite, -clock.leftWall, seat)
            : placeOnTrack(track, area, sprite, clock.rightWall, seat);
        if (perch) {
            if (mirrored) {
                perch.x = -perch.x - perch.width;
                perch.seatShift = -perch.seatShift;
            }
            const route = {...perch, x: mirrored ? perch.x : perch.x - perch.walkDistance,
                width: perch.width + perch.walkDistance};
            return {kind: 'perched', ...perch, ...(mirrored ? {mirrored} : {}),
                routeCovered: perch.canWalk && windows.some(window => overlaps(route, window))};
        }
    }

    return {kind: 'standalone', x: body.x + (body.width - sprite.width) / 2,
        y: body.y + body.height - sprite.height, width: sprite.width, height: sprite.height,
        canWalk: false, routeCovered: false, seatShift: 0, walkDistance: 0};
}
