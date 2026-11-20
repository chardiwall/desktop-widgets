import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';
import {measureTrack} from '../desktop_widgets/bridge/track.js';

import {listeningFrame, overlaps, placeOnTrack, sampleWalk, umbrellaBox} from '../desktop_widgets/widgets/avatar/motion.js';

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
check(route.canWalk && route.x - route.walkDistance === track.ranges[0][0],
    'The route reaches the measured text clearance without crossing it');
check(route.y + asset.pivot[1] === track.top, 'The sole meets the top of the ink stroke');
check(route.x + route.width <= track.ranges[0][1], 'The full path fits before right-aligned text');
check(!placeOnTrack({...track, ranges: [[track.left, track.left + 65]]}, area, asset).canWalk,
    'A short track still has a perch');
check(!placeOnTrack({...track, top: 30}, area, asset), 'Insufficient vertical clearance rejects the track');
layout.set_text('12:30\n20% of the day', -1);
check(measureTrack(layout, 0, 0, 99) === null, 'Missing clock line gives no track');
layout.set_markup('12:30\n<span size="16pt">Thursday, 19 November</span>\n' + '━'.repeat(54), -1);
const smallTrack = measureTrack(layout, 0, 0, 99);
layout.set_markup('12:30\n<span size="26pt">Thursday, 19 November</span>\n' + '━'.repeat(54), -1);
const largeTrack = measureTrack(layout, 0, 0, 99);
check(largeTrack.ranges[0][0] > smallTrack.ranges[0][0] && largeTrack.right === smallTrack.right,
    'Wider Clock text shortens the walk with an unchanged track');
check(overlaps(route, {...route, x: route.x + route.width - 1}), 'A covering window blocks the route');
check(!overlaps(route, {...route, x: route.x + route.width}), 'Touching edges are clear');
const clearTrack = {top: 250, right: 420, ranges: [[0, 420]]};
const atWall = placeOnTrack(clearTrack, area, asset, 474, {back: 70, contact: 10});
check(atWall.x + atWall.seatShift + 70 === 474, 'The seated back reaches the wall while the shoes reach the track');
check(placeOnTrack(clearTrack, area, asset, 460).seatShift === 0, 'An unsupported wall keeps the seat on the line');
const umbrella = umbrellaBox({head: [75, 70], hand: [96, 129], crown: 50});
check(umbrella.x + umbrella.canopyX === 75 && umbrella.y + 42 < 50 &&
    umbrella.x + umbrella.gripX === 96 && umbrella.y + umbrella.gripY === 129,
    'The umbrella clears the crown and the handle meets the hand');
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
