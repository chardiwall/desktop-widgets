import {resolveAvatarPlacement} from '../desktop_widgets/widgets/avatar/placement.js';

function check(condition, message) {
    if (!condition)
        throw new Error(message);
}

const avatar = {width: 96, height: 166, pivot: [48, 165], travel: [0, 34, 0]};
const body = {monitor: 0, x: 70, y: 510, width: 160, height: 166};
const clock = {
    monitor: 0,
    track: {right: 770, top: 480, ranges: [[290, 770]]},
    area: {x: 0, y: 0, width: 1200, height: 800},
    rightWall: 898,
};
const view = {visible: true, body, clock};
const clear = resolveAvatarPlacement(view, avatar);
check(clear.kind === 'perched' && clear.x === 674 && clear.y === 315 && clear.walkDistance === 384 && clear.canWalk,
    'The Avatar perches on the Clock when they share a display');
const covered = resolveAvatarPlacement({...view, windows: [{x: 300, y: 350, width: 40, height: 200}]}, avatar);
check(covered.kind === 'perched' && covered.x === clear.x && covered.routeCovered,
    'A partly obstructed route keeps the perch and blocks a new walk');
const leftClock = {...clock, perchSide: 'left', leftWall: 255, track: {...clock.track, left: 290}};
const left = resolveAvatarPlacement({...view, clock: leftClock, windows: [{x: 625, y: 350, width: 40, height: 200}]},
    avatar, {back: 115, contact: 10});
check(left.kind === 'perched' && left.mirrored && left.x === 290 && left.y === clear.y &&
    left.walkDistance === clear.walkDistance && left.routeCovered && left.seatShift === -16,
    'The Arabic layout mirrors the perch, wall lean, and window checks');
check(resolveAvatarPlacement({...view, clock: {...clock, trackPending: true}}, avatar).kind === 'pending',
    'Wait for the Clock to finish relayout before replacing the current placement');
check(resolveAvatarPlacement({...view, clock: {pending: true}}, avatar).kind === 'pending',
    'Wait for the Clock allocation to determine its display');
check(resolveAvatarPlacement({...view, body: null}, avatar).kind === 'pending',
    'Wait for the Avatar allocation before choosing a placement');
check(resolveAvatarPlacement({...view, visible: false}, avatar).kind === 'hidden',
    'A hidden desktop takes precedence over an available perch');

for (const unavailable of [null, {...clock, monitor: 1}, {...clock, track: null},
    {...clock, track: {...clock.track, ranges: [[760, 770]]}}]) {
    const fallback = resolveAvatarPlacement({...view, clock: unavailable}, avatar);
    check(fallback.kind === 'standalone' && fallback.x === 102 && fallback.y === 510 && !fallback.canWalk,
        'A disabled, distant or unusable Clock uses the saved standalone placement');
}
print('Avatar visibility and placement checks passed.');
