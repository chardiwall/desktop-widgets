import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';
import {measureTrack} from '../desktop_widgets/bridge/track.js';

import {listeningFrame, overlaps, placeOnTrack, sampleWalk} from '../desktop_widgets/widgets/avatar/motion.js';

function check(condition, message) {
    if (!condition)
        throw new Error(message);
}

const layout = Pango.Layout.new(PangoCairo.FontMap.get_default().create_context());
const area = {x: -200, y: 0, width: 800, height: 600};
const asset = {width: 60, height: 100, pivot: [32, 99], fps: 20, travel: [0, 5, 14, 5, 0]};
layout.set_text('12:30\nالظهر\n' + '━'.repeat(54) + '\n20% of the day', -1);
const track = measureTrack(layout, -100, 200, asset.pivot[1]);
const route = placeOnTrack(track, area, asset);
check(route.canWalk && route.x >= track.left, 'Measured line gives a clear route past multilingual text');
check(route.y + asset.pivot[1] === track.top, 'The sole meets the top of the ink stroke');
check(route.x + route.width <= track.ranges[0][1], 'The full path fits before right-aligned text');
check(!placeOnTrack({...track, ranges: [[track.left, track.left + 65]]}, area, asset).canWalk,
    'A short track still has a perch');
check(!placeOnTrack({...track, top: 30}, area, asset), 'Insufficient vertical clearance rejects the track');
layout.set_text('12:30\n20% of the day', -1);
check(measureTrack(layout, 0, 0, 99) === null, 'Missing clock line gives no track');
check(overlaps(route, {...route, x: route.x + route.width - 1}), 'A covering window blocks the route');
check(!overlaps(route, {...route, x: route.x + route.width}), 'Touching edges are clear');
const clearTrack = {top: 250, right: 420, ranges: [[0, 420]]};
const atWall = placeOnTrack(clearTrack, area, asset, 438);
check(atWall.x + atWall.seatShift + asset.width === 438, 'Listening reaches a wall within foot support');
check(placeOnTrack(clearTrack, area, asset, 460).seatShift === 14, 'An unsupported wall keeps the seat on the line');
const regular = [0, 25, 50, 75, 100].map(ms => sampleWalk(ms, asset));
const missed = [0, 100].map(ms => sampleWalk(ms, asset));
check(regular.at(-1).x === missed.at(-1).x, 'Missed frames cannot change travel');
check(regular[1].frame === 0 && regular[1].x === 2.5, 'Translation interpolates between sprite frames');
check(sampleWalk(2000, asset).x === 0 && sampleWalk(2000, asset).frame === 4, 'Late completion returns to rest');
const seated = {seated: 12, fps: 18, anchors: Array(24)};
check(listeningFrame(seated, 0.5, 1) === 6, 'An interrupted sit can reverse from the same frame');
check(listeningFrame(seated, 1, 0) === 12 && listeningFrame(seated, 1, 1) === 18,
    'Seated playback loops within its bead-turn frames');
print('Avatar geometry and motion checks passed.');
