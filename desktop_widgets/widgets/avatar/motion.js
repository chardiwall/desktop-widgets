import Motion from 'gi://DesktopWidgetsMotion?version=1.0';
import GLib from 'gi://GLib';

const travelData = new WeakMap();

export function placeOnTrack(track, area, asset, rightWall = null) {
    const {width, height, pivot, travel} = asset;
    const [fits, x, y, canWalk, seatShift] = Motion.place(track.ranges.flat(), track.right, track.top,
        area.x, area.y, area.width, area.height, width, height, ...pivot, Math.max(...travel), rightWall ?? NaN);
    return fits ? {x, y, width: width + seatShift, height, canWalk, seatShift} : null;
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

export function overlaps(a, b) {
    return a.x < b.x + b.width && a.x + a.width > b.x &&
        a.y < b.y + b.height && a.y + a.height > b.y;
}
