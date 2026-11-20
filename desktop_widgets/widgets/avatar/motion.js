import Motion from 'gi://DesktopWidgetsMotion?version=1.0';
import GLib from 'gi://GLib';

const travelData = new WeakMap();

export function placeOnTrack(track, area, asset, rightWall = null, seat = {}) {
    const {width, height, pivot, travel} = asset;
    const [fits, x, y, canWalk, seatShift, walkDistance] = Motion.place(track.ranges.flat(), track.right, track.top,
        area.x, area.y, area.width, area.height, width, height, seat.contact ?? pivot[0], pivot[1],
        Math.max(...travel), rightWall ?? NaN, seat.back ?? width);
    return fits ? {x, y, width, height, canWalk, seatShift, walkDistance} : null;
}

export function sampleWalk(elapsed, asset) {
    let travel = travelData.get(asset.travel);
    if (!travel) {
        travel = new GLib.Variant('ad', asset.travel);
        travelData.set(asset.travel, travel);
    }
    const [frame, x] = Motion.sample(elapsed, asset.fps, travel);
    return {frame, x};
}

export function listeningFrame(asset, phase, elapsed) {
    return Motion.listening_frame(asset.seated, asset.fps, asset.anchors.length, phase, elapsed);
}

export function umbrellaBox({head, hand, crown = head[1] - 25}) {
    const x = Math.min(head[0] - 56, hand[0] - 12);
    const y = crown - 50;
    const right = Math.max(head[0] + 56, hand[0] + 4);
    return {x, y, width: Math.ceil(right - x), height: Math.ceil(hand[1] - y + 10),
        canopyX: head[0] - x, gripX: hand[0] - x, gripY: hand[1] - y};
}

export function overlaps(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x &&
        a.y < b.y + b.height && a.y + a.height > b.y;
}
