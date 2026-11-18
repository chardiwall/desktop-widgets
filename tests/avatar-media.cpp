#include "../desktop_widgets/widgets/avatar/media.h"
#include "../desktop_widgets/widgets/avatar/surahs.h"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <memory>

int main() {
    namespace fs = std::filesystem;
    const std::unique_ptr<char *, decltype(&g_strfreev)> catalogue(g_strsplit(surah_names, "|", -1), g_strfreev);
    assert(g_strv_length(catalogue.get()) == 114);
    assert(g_str_equal(catalogue.get()[0], "الفاتحة"));
    assert(g_str_equal(catalogue.get()[113], "الناس"));
    assert(surah_uri(0) == std::string(recitation) + "001.mp3");
    assert(surah_uri(113) == std::string(recitation) + "114.mp3");

    const std::unique_ptr<char, decltype(&g_free)> folder(g_dir_make_tmp("avatar-media-XXXXXX", nullptr), g_free);
    assert(folder);
    const fs::path path(folder.get());
    std::ofstream(path / "b.MP3").close();
    std::ofstream(path / "A.flac").close();
    std::ofstream(path / "notes.txt").close();
    fs::create_directory(path / "directory.wav");
    const auto tracks = music_files(path);
    assert(tracks.size() == 2 && tracks[0].filename() == "A.flac" && tracks[1].filename() == "b.MP3");

    gst_init(nullptr, nullptr);
    GstElement *player = create_playbin();
    GstElement *sink = gst_element_factory_make("fakesink", nullptr);
    assert(player && sink);
    constexpr char header[] = {
        'R', 'I', 'F', 'F', char(68), 3, 0, 0, 'W', 'A', 'V', 'E',
        'f', 'm', 't', ' ', 16, 0, 0, 0, 1, 0, 1, 0, 64, 31, 0, 0,
        char(128), 62, 0, 0, 2, 0, 16, 0, 'd', 'a', 't', 'a', 32, 3, 0, 0,
    };
    const auto audio = path / "Short sample.wav";
    std::ofstream wav(audio, std::ios::binary);
    const char silence[800]{};
    wav.write(header, sizeof(header));
    wav.write(silence, sizeof(silence));
    wav.close();
    const std::unique_ptr<char, decltype(&g_free)> uri(g_filename_to_uri(audio.c_str(), nullptr, nullptr), g_free);
    assert(uri);
    g_object_set(player, "audio-sink", sink, "uri", uri.get(), nullptr);
    GstBus *bus = gst_element_get_bus(player);
    assert(gst_element_set_state(player, GST_STATE_PLAYING) != GST_STATE_CHANGE_FAILURE);
    GstMessage *message = gst_bus_timed_pop_filtered(bus, 5 * GST_SECOND,
                                                    GstMessageType(GST_MESSAGE_ERROR | GST_MESSAGE_EOS));
    assert(message && GST_MESSAGE_TYPE(message) == GST_MESSAGE_EOS);
    gst_message_unref(message);
    gst_element_set_state(player, GST_STATE_NULL);
    gst_object_unref(bus);
    gst_object_unref(player);
    fs::remove_all(path);
}
