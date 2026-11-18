const PANGO_SCALE = 1024;
const GAP = 6;

export function measureTrack(layout, originX, originY, pivotY) {
    const bytes = new TextEncoder().encode(layout.get_text());
    const decoder = new TextDecoder();
    const iter = layout.get_iter();
    const ink = [];
    let track = null;
    do {
        const line = iter.get_line_readonly();
        const text = decoder.decode(bytes.subarray(line.start_index, line.start_index + line.length));
        const [rect] = iter.get_line_extents();
        if (!rect.width || !rect.height)
            continue;
        const left = originX + rect.x / PANGO_SCALE;
        const top = originY + rect.y / PANGO_SCALE;
        const right = left + rect.width / PANGO_SCALE;
        const bottom = top + rect.height / PANGO_SCALE;
        if (/^━{8,}$/.test(text.trim())) {
            if (track)
                return null;
            track = {left, right, top};
        } else {
            ink.push({left, right, top, bottom});
        }
    } while (iter.next_line());

    if (!track)
        return null;
    track.ranges = [[track.left, track.right]];
    for (const obstacle of ink.filter(r => r.top < track.top && r.bottom > track.top - pivotY)) {
        track.ranges = track.ranges.flatMap(([left, right]) => {
            if (obstacle.right + GAP <= left || obstacle.left - GAP >= right)
                return [[left, right]];
            return [[left, obstacle.left - GAP], [obstacle.right + GAP, right]]
                .filter(([start, end]) => start < end);
        });
    }
    return track;
}

export function placeOnTrack(track, area, asset, rightWall = null) {
    const {width, height, pivot, travel} = asset;
    const distance = Math.max(...travel);
    const y = track.top - pivot[1];
    if (y < area.y || y + height > area.y + area.height)
        return null;
    const ranges = track.ranges.map(([left, right]) =>
        [Math.max(left, area.x + GAP), Math.min(right, area.x + area.width - GAP)]);
    const route = ranges.findLast(([left, right]) => right - left >= width + distance);
    const range = route ?? ranges.findLast(([left, right]) => right - left >= width);
    if (!range)
        return null;
    const right = range[1];
    const canWalk = Boolean(route);
    const x = right - width - (canWalk ? distance : 0);
    let seatShift = canWalk ? distance : 0;
    if (rightWall !== null && right === track.right) {
        const wallSeat = rightWall - width;
        if (wallSeat + pivot[0] <= right && rightWall <= area.x + area.width - GAP)
            seatShift = Math.max(seatShift, wallSeat - x);
    }
    return {x, y, width: width + seatShift, height, canWalk, seatShift};
}

export function sampleWalk(elapsed, asset) {
    const {fps, travel} = asset;
    const progress = Math.max(0, Math.min(travel.length - 1, elapsed * fps / 1000));
    const frame = Math.floor(progress);
    const next = Math.min(frame + 1, travel.length - 1);
    const x = travel[frame] + (travel[next] - travel[frame]) * (progress - frame);
    return {frame, x};
}

export function listeningFrame(asset, phase, elapsed) {
    if (phase < 1)
        return Math.round(Math.max(0, phase) * asset.seated);
    return asset.seated + Math.floor(elapsed * asset.fps) % (asset.anchors.length - asset.seated);
}

export function overlaps(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x &&
        a.y < b.y + b.height && a.y + a.height > b.y;
}
