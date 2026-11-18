#pragma once

#include <gst/gst.h>

#include <filesystem>
#include <string>
#include <vector>

inline constexpr char recitation[] = "https://cdn.mp3quran.net/download/audio/muhammad-minshawi/r2/";

std::vector<std::filesystem::path> music_files(const std::filesystem::path &folder);
std::string surah_uri(guint index);
GstElement *create_playbin();
