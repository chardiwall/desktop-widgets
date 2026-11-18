#pragma once

#include <glib.h>

G_BEGIN_DECLS

/**
 * desktop_widgets_motion_place:
 * @ranges: (array length=range_length): paired left and right limits in logical pixels
 * @range_length: number of coordinates in @ranges
 * @track_right: right edge of the track
 * @track_top: top of the track
 * @area_x: left of the visible work area
 * @area_y: top of the visible work area
 * @area_width: width of the work area
 * @area_height: height of the work area
 * @width: sprite width
 * @height: sprite height
 * @pivot_x: horizontal pivot within the sprite
 * @pivot_y: vertical pivot within the sprite
 * @distance: maximum walk displacement
 * @wall: optional right wall, or NaN for no wall
 * @x: (out): sprite left edge
 * @y: (out): sprite top edge
 * @can_walk: (out): whether a full walk fits
 * @seat_shift: (out): horizontal displacement available for sitting
 * Returns: whether the sprite fits on the track
 */
gboolean desktop_widgets_motion_place(const double *ranges, gsize range_length,
    double track_right, double track_top, double area_x, double area_y, double area_width,
    double area_height, double width, double height, double pivot_x, double pivot_y,
    double distance, double wall, double *x, double *y, gboolean *can_walk, double *seat_shift);

/**
 * desktop_widgets_motion_sample:
 * @elapsed: elapsed milliseconds
 * @fps: frames per second
 * @travel: travel positions as a variant of type ad
 * @x: (out): interpolated horizontal displacement
 * Returns: the current sprite frame index
 */
guint desktop_widgets_motion_sample(double elapsed, double fps, GVariant *travel, double *x);

/**
 * desktop_widgets_motion_listening_frame:
 * @seated: first seated frame
 * @fps: frames per second
 * @count: total number of frames
 * @phase: progress through the entry transition
 * @elapsed: elapsed seconds in the seated loop
 * Returns: the current sprite frame index
 */
guint desktop_widgets_motion_listening_frame(guint seated, double fps, guint count,
    double phase, double elapsed);

G_END_DECLS
