#include "media.h"

#include <algorithm>
#include <array>
#include <memory>
#include <string_view>

namespace fs = std::filesystem;
using Text = std::unique_ptr<char, decltype(&g_free)>;

std::vector<fs::path> music_files(const fs::path &folder) {
    constexpr std::array formats{".mp3", ".ogg", ".oga", ".opus", ".flac", ".wav",
                                 ".aac", ".m4a", ".aiff", ".wma"};
    std::vector<fs::path> tracks;
    for (const auto &entry : fs::directory_iterator(folder)) {
        Text extension(g_ascii_strdown(entry.path().extension().c_str(), -1), g_free);
        if (std::ranges::any_of(formats, [&](const char *format) {
                return std::string_view(extension.get()) == format;
            }) && entry.is_regular_file())
            tracks.push_back(entry.path());
    }
    std::ranges::sort(tracks, [](const auto &a, const auto &b) {
        Text first(g_filename_display_basename(a.c_str()), g_free);
        Text second(g_filename_display_basename(b.c_str()), g_free);
        Text left(g_utf8_casefold(first.get(), -1), g_free);
        Text right(g_utf8_casefold(second.get(), -1), g_free);
        const int order = g_strcmp0(left.get(), right.get());
        return order ? order < 0 : a.filename() < b.filename();
    });
    return tracks;
}

std::string surah_uri(guint index) {
    Text uri(g_strdup_printf("%s%03u.mp3", recitation, index + 1), g_free);
    return uri.get();
}

GstElement *create_playbin() {
    GstElement *player = gst_element_factory_make("playbin", nullptr);
    if (player)
        g_object_set(player, "flags", 0x02, nullptr); // GST_PLAY_FLAG_AUDIO
    return player;
}
