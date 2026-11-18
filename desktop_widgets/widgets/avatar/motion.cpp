#include "motion.h"

#include <algorithm>
#include <cmath>

gboolean desktop_widgets_motion_place(const double *ranges, gsize range_length,
    double track_right, double track_top, double area_x, double area_y, double area_width,
    double area_height, double width, double height, double pivot_x, double pivot_y,
    double distance, double wall, double *x, double *y, gboolean *can_walk, double *seat_shift)
{
    constexpr double gap = 6;
    *x = *seat_shift = 0;
    *can_walk = false;
    *y = track_top - pivot_y;
    if (*y < area_y || *y + height > area_y + area_height)
        return false;

    const double area_right = area_x + area_width - gap;
    double perch = NAN;
    for (gsize length = range_length; length >= 2; length -= 2) {
        const double left = std::max(ranges[length - 2], area_x + gap);
        const double right = std::min(ranges[length - 1], area_right);
        if (right - left >= width + distance) {
            perch = right;
            *can_walk = true;
            break;
        }
        if (std::isnan(perch) && right - left >= width)
            perch = right;
    }
    if (std::isnan(perch))
        return false;

    *seat_shift = *can_walk ? distance : 0;
    *x = perch - width - *seat_shift;
    if (perch == track_right && wall <= area_right && wall - width + pivot_x <= perch)
        *seat_shift = std::max(*seat_shift, wall - width - *x);
    return true;
}

guint desktop_widgets_motion_sample(double elapsed, double fps, GVariant *travel, double *x)
{
    *x = 0;
    g_return_val_if_fail(g_variant_is_of_type(travel, G_VARIANT_TYPE("ad")), 0);
    gsize count = 0;
    const auto *positions = static_cast<const double *>(
        g_variant_get_fixed_array(travel, &count, sizeof(double)));
    if (count == 0)
        return 0;

    const double progress = std::clamp(elapsed * fps / 1000, 0.0, double(count - 1));
    const auto frame = static_cast<guint>(progress);
    const auto next = std::min<gsize>(frame + 1, count - 1);
    *x = positions[frame] + (positions[next] - positions[frame]) * (progress - frame);
    return frame;
}

guint desktop_widgets_motion_listening_frame(guint seated, double fps, guint count,
    double phase, double elapsed)
{
    if (phase < 1)
        return static_cast<guint>(std::round(std::max(phase, 0.0) * seated));
    if (count <= seated)
        return seated;
    return seated + static_cast<guint>(std::fmod(std::floor(elapsed * fps), count - seated));
}
