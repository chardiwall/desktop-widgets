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
        if (/^━{8,}$/.test(text.replaceAll('\u200e', '').trim())) {
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
