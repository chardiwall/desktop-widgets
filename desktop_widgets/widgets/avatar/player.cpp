#include "media.h"
#include "surahs.h"

#include <gtk/gtk.h>
#include <gst/gst.h>

#include <algorithm>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace {
namespace fs = std::filesystem;
constexpr char app_id[] = "io.github.desktopwidgets.Media";

enum class Section { music, quran };
struct Selection {
    Section section;
    guint index;
    bool operator==(const Selection &) const = default;
};

using Names = std::unique_ptr<char *, decltype(&g_strfreev)>;
using Text = std::unique_ptr<char, decltype(&g_free)>;

void label(GtkWidget *widget, const char *text) {
    gtk_accessible_update_property(GTK_ACCESSIBLE(widget), GTK_ACCESSIBLE_PROPERTY_LABEL, text, -1);
}

GtkDropDown *choices(const char *name, GtkStringList *model = nullptr) {
    auto *expression = gtk_property_expression_new(GTK_TYPE_STRING_OBJECT, nullptr, "string");
    auto *dropdown = GTK_DROP_DOWN(gtk_drop_down_new(G_LIST_MODEL(model), expression));
    gtk_drop_down_set_enable_search(dropdown, true);
    label(GTK_WIDGET(dropdown), name);
    return dropdown;
}

struct FolderScan {
    fs::path folder;
    unsigned revision;
};

class Player {
public:
    int run(int argc, char **argv) {
        app = gtk_application_new(app_id, G_APPLICATION_HANDLES_COMMAND_LINE);
        g_signal_connect(app, "startup", G_CALLBACK(+[](GtkApplication *, Player *self) {
            self->startup();
        }), this);
        g_signal_connect(app, "command-line", G_CALLBACK(+[](GApplication *, GApplicationCommandLine *line,
                                                            Player *self) -> int {
            int count;
            Names args(g_application_command_line_get_arguments(line, &count), g_strfreev);
            if (count > 2 || (count == 2 && !g_str_equal(args.get()[1], "music") &&
                                          !g_str_equal(args.get()[1], "quran")))
                return 2;
            if (!self->window)
                self->build_window();
            if (count == 2)
                gtk_stack_set_visible_child_name(self->tabs, args.get()[1]);
            gtk_window_present(self->window);
            self->update_info();
            return 0;
        }), this);
        const int result = g_application_run(G_APPLICATION(app), argc, argv);
        if (timer)
            g_source_remove(timer);
        if (bus_watch)
            g_source_remove(bus_watch);
        if (pipeline) {
            gst_element_set_state(pipeline, GST_STATE_NULL);
            gst_object_unref(pipeline);
        }
        g_clear_object(&session);
        g_clear_object(&state);
        g_object_unref(app);
        return result;
    }

private:
    GtkApplication *app{};
    GtkWindow *window{};
    GtkStack *tabs{};
    GtkDropDown *tracks{}, *surahs{};
    GtkLabel *folder_label{}, *status{};
    GtkRange *seek{};
    GtkButton *previous{}, *play{}, *next{}, *stop_button{};
    GstElement *pipeline{};
    GSettings *session{};
    GSimpleAction *state{};
    guint bus_watch{}, timer{}, folder_revision{};
    bool playing{}, want_play{}, updating_progress{};
    std::optional<Selection> current;
    std::vector<fs::path> files;
    Names catalogue{g_strsplit(surah_names, "|", -1), g_strfreev};
    const guint surah_count{g_strv_length(catalogue.get())};

    void startup() {
        gst_init(nullptr, nullptr);
        pipeline = create_playbin();
        if (pipeline) {
            GstBus *bus = gst_element_get_bus(pipeline);
            bus_watch = gst_bus_add_watch(bus, +[](GstBus *, GstMessage *message, gpointer data) -> gboolean {
                static_cast<Player *>(data)->on_message(message);
                return G_SOURCE_CONTINUE;
            }, this);
            gst_object_unref(bus);
        }
        state = g_simple_action_new_stateful("now-playing", nullptr, g_variant_new_string("none"));
        g_signal_connect(state, "change-state", G_CALLBACK(+[](GSimpleAction *, GVariant *, gpointer) {}), nullptr);
        g_action_map_add_action(G_ACTION_MAP(app), G_ACTION(state));
        auto *source = g_settings_schema_source_get_default();
        auto *schema = source ? g_settings_schema_source_lookup(source, "io.github.desktopwidgets.Settings", true)
                              : nullptr;
        if (schema) {
            session = g_settings_new_full(schema, nullptr, nullptr);
            g_settings_schema_unref(schema);
            g_signal_connect(session, "changed::session-mode", G_CALLBACK(+[](GSettings *settings, const char *,
                                                                               Player *self) {
                Text mode(g_settings_get_string(settings, "session-mode"), g_free);
                if (g_str_equal(mode.get(), "stopped"))
                    g_application_quit(G_APPLICATION(self->app));
            }), this);
            Text mode(g_settings_get_string(session, "session-mode"), g_free);
        }
    }

    void build_window() {
        window = GTK_WINDOW(gtk_application_window_new(app));
        gtk_window_set_title(window, "Avatar audio");
        gtk_window_set_default_size(window, 460, -1);
        g_signal_connect(window, "close-request", G_CALLBACK(+[](GtkWindow *widget, Player *self) -> gboolean {
            if (self->want_play) {
                gtk_widget_set_visible(GTK_WIDGET(widget), false);
                return true;
            }
            self->stop();
            self->window = nullptr;
            ++self->folder_revision;
            return false;
        }), this);
        g_signal_connect(window, "notify::visible", G_CALLBACK(+[](GtkWindow *, GParamSpec *, Player *self) {
            self->update_timer();
        }), this);
        auto *box = GTK_BOX(gtk_box_new(GTK_ORIENTATION_VERTICAL, 12));
        gtk_widget_set_margin_top(GTK_WIDGET(box), 16);
        gtk_widget_set_margin_bottom(GTK_WIDGET(box), 16);
        gtk_widget_set_margin_start(GTK_WIDGET(box), 16);
        gtk_widget_set_margin_end(GTK_WIDGET(box), 16);
        gtk_window_set_child(window, GTK_WIDGET(box));
        tabs = GTK_STACK(gtk_stack_new());
        auto *switcher = gtk_stack_switcher_new();
        gtk_stack_switcher_set_stack(GTK_STACK_SWITCHER(switcher), tabs);
        gtk_widget_set_halign(switcher, GTK_ALIGN_CENTER);
        gtk_box_append(box, switcher);
        gtk_box_append(box, GTK_WIDGET(tabs));

        auto *music = GTK_BOX(gtk_box_new(GTK_ORIENTATION_VERTICAL, 8));
        auto *folder = gtk_button_new_with_label("Choose music folder…");
        gtk_widget_set_halign(folder, GTK_ALIGN_START);
        g_signal_connect(folder, "clicked", G_CALLBACK(+[](GtkButton *, Player *self) {
            self->choose_folder();
        }), this);
        gtk_box_append(music, folder);
        folder_label = GTK_LABEL(gtk_label_new("Choose a folder to list its audio files."));
        gtk_label_set_xalign(folder_label, 0);
        gtk_label_set_wrap(folder_label, true);
        gtk_box_append(music, GTK_WIDGET(folder_label));
        tracks = choices("Music file");
        gtk_box_append(music, GTK_WIDGET(tracks));
        gtk_stack_add_titled(tabs, GTK_WIDGET(music), "music", "Music");

        auto *quran = GTK_BOX(gtk_box_new(GTK_ORIENTATION_VERTICAL, 8));
        auto *heading = GTK_LABEL(gtk_label_new("محمد صديق المنشاوي · المصحف المجوّد"));
        gtk_widget_set_direction(GTK_WIDGET(heading), GTK_TEXT_DIR_RTL);
        gtk_label_set_xalign(heading, 1);
        gtk_box_append(quran, GTK_WIDGET(heading));
        auto *list = gtk_string_list_new(nullptr);
        for (guint i = 0; i < surah_count; ++i) {
            Text name(g_strdup_printf("%u. %s", i + 1, catalogue.get()[i]), g_free);
            gtk_string_list_append(list, name.get());
        }
        surahs = choices("السورة", list);
        gtk_widget_set_direction(GTK_WIDGET(surahs), GTK_TEXT_DIR_RTL);
        gtk_box_append(quran, GTK_WIDGET(surahs));
        gtk_box_append(quran, gtk_link_button_new_with_label(
            "https://www.mp3quran.net/eng/minsh_mjwd/", "Recording source · MP3Quran"));
        gtk_stack_add_titled(tabs, GTK_WIDGET(quran), "quran", "القرآن");

        status = GTK_LABEL(gtk_label_new(nullptr));
        gtk_label_set_xalign(status, 0);
        gtk_label_set_wrap(status, true);
        gtk_box_append(box, GTK_WIDGET(status));
        seek = GTK_RANGE(gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0, 1, 1));
        gtk_scale_set_draw_value(GTK_SCALE(seek), false);
        label(GTK_WIDGET(seek), "Playback position");
        g_signal_connect(seek, "change-value", G_CALLBACK(+[](GtkRange *, GtkScrollType, double seconds,
                                                            Player *self) -> gboolean {
            if (self->current && !self->updating_progress)
                gst_element_seek_simple(self->pipeline, GST_FORMAT_TIME,
                    GstSeekFlags(GST_SEEK_FLAG_FLUSH | GST_SEEK_FLAG_KEY_UNIT), gint64(seconds * GST_SECOND));
            return false;
        }), this);
        gtk_box_append(box, GTK_WIDGET(seek));

        auto *buttons = GTK_BOX(gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6));
        gtk_box_append(box, GTK_WIDGET(buttons));
        previous = button(buttons, "Previous", +[](GtkButton *, Player *self) { self->step(-1); });
        play = button(buttons, "Play", +[](GtkButton *, Player *self) { self->play_or_pause(); });
        next = button(buttons, "Next", +[](GtkButton *, Player *self) { self->step(1); });
        stop_button = button(buttons, "Stop", +[](GtkButton *, Player *self) { self->stop(); });
        auto *volume = gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0, 1, 0.05);
        label(volume, "Volume");
        gtk_widget_set_size_request(volume, 90, -1);
        gtk_scale_set_draw_value(GTK_SCALE(volume), false);
        gtk_range_set_value(GTK_RANGE(volume), 1);
        g_signal_connect(volume, "value-changed", G_CALLBACK(+[](GtkRange *range, Player *self) {
            if (self->pipeline)
                g_object_set(self->pipeline, "volume", gtk_range_get_value(range), nullptr);
        }), this);
        gtk_box_append(buttons, volume);
        button(buttons, "Quit", +[](GtkButton *, Player *self) { g_application_quit(G_APPLICATION(self->app)); });
        const auto refresh = +[](GObject *, GParamSpec *, Player *self) { self->refresh_controls(); };
        g_signal_connect(tabs, "notify::visible-child-name", G_CALLBACK(refresh), this);
        g_signal_connect(tracks, "notify::selected", G_CALLBACK(refresh), this);
        g_signal_connect(surahs, "notify::selected", G_CALLBACK(refresh), this);
    }

    GtkButton *button(GtkBox *box, const char *title, void (*callback)(GtkButton *, Player *)) {
        auto *widget = gtk_button_new_with_label(title);
        g_signal_connect(widget, "clicked", G_CALLBACK(callback), this);
        gtk_box_append(box, widget);
        return GTK_BUTTON(widget);
    }

    void choose_folder() {
        auto *dialog = gtk_file_dialog_new();
        gtk_file_dialog_set_title(dialog, "Choose music folder");
        gtk_file_dialog_select_folder(dialog, window, nullptr, +[](GObject *source, GAsyncResult *result, gpointer data) {
            auto &self = *static_cast<Player *>(data);
            GFile *folder = gtk_file_dialog_select_folder_finish(GTK_FILE_DIALOG(source), result, nullptr);
            if (!folder)
                return;
            Text path(g_file_get_path(folder), g_free);
            g_object_unref(folder);
            if (!self.window)
                return;
            if (!path) {
                gtk_label_set_text(self.folder_label, "Choose a folder stored on this device.");
                return;
            }
            self.scan_folder(path.get());
        }, this);
        g_object_unref(dialog);
    }

    void scan_folder(const char *path) {
        gtk_label_set_text(folder_label, "Reading folder…");
        GTask *task = g_task_new(nullptr, nullptr, +[](GObject *, GAsyncResult *result, gpointer data) {
            auto &self = *static_cast<Player *>(data);
            auto *task = G_TASK(result);
            const auto &scan = *static_cast<FolderScan *>(g_task_get_task_data(task));
            if (!self.window || scan.revision != self.folder_revision)
                return;
            if (self.current && self.current->section == Section::music)
                self.stop();
            GError *error = nullptr;
            std::unique_ptr<std::vector<fs::path>> found(
                static_cast<std::vector<fs::path> *>(g_task_propagate_pointer(task, &error)));
            self.files = found ? std::move(*found) : std::vector<fs::path>{};
            auto *model = gtk_string_list_new(nullptr);
            for (const auto &file : self.files) {
                Text name(g_filename_display_basename(file.c_str()), g_free);
                gtk_string_list_append(model, name.get());
            }
            gtk_drop_down_set_model(self.tracks, G_LIST_MODEL(model));
            g_object_unref(model);
            Text name(g_filename_display_basename(scan.folder.c_str()), g_free);
            Text message(error ? g_strdup_printf("Cannot read folder: %s", error->message)
                               : g_strdup_printf("%s · %zu audio files", name.get(), self.files.size()), g_free);
            g_clear_error(&error);
            gtk_label_set_text(self.folder_label, message.get());
            self.refresh_controls();
        }, this);
        g_task_set_task_data(task, new FolderScan{path, ++folder_revision},
                             +[](gpointer data) { delete static_cast<FolderScan *>(data); });
        g_task_run_in_thread(task, +[](GTask *task, gpointer, gpointer data, GCancellable *) {
            try {
                auto *tracks = new std::vector<fs::path>(music_files(static_cast<FolderScan *>(data)->folder));
                g_task_return_pointer(task, tracks, +[](gpointer items) { delete static_cast<std::vector<fs::path> *>(items); });
            } catch (const std::exception &error) {
                g_task_return_new_error(task, G_IO_ERROR, G_IO_ERROR_FAILED, "%s", error.what());
            }
        });
        g_object_unref(task);
    }

    GtkDropDown *dropdown(Section section) const { return section == Section::music ? tracks : surahs; }
    guint count(Section section) const { return section == Section::music ? files.size() : surah_count; }
    std::optional<Selection> selected() const {
        const auto section = g_str_equal(gtk_stack_get_visible_child_name(tabs), "music") ? Section::music : Section::quran;
        const guint index = gtk_drop_down_get_selected(dropdown(section));
        if (index >= count(section))
            return std::nullopt;
        return Selection{section, index};
    }

    void playback(Selection selection) {
        if (!pipeline)
            return;
        if (current != selection) {
            gst_element_set_state(pipeline, GST_STATE_NULL);
            publish(false);
            const auto [section, index] = selection;
            Text local(section == Section::music ? g_filename_to_uri(files[index].c_str(), nullptr, nullptr) : nullptr,
                       g_free);
            const auto uri = section == Section::quran ? surah_uri(index) : local ? local.get() : "";
            if (uri.empty()) {
                stop("Audio unavailable: could not open the selected file.");
                return;
            }
            g_object_set(pipeline, "uri", uri.c_str(), nullptr);
            current = selection;
        }
        want_play = true;
        if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE)
            stop("Audio could not start.");
        else
            update_info();
    }

    void play_or_pause() {
        const auto selection = selected();
        if (!selection || !pipeline)
            return;
        if (current == selection && want_play) {
            want_play = false;
            gst_element_set_state(pipeline, GST_STATE_PAUSED);
            publish(false);
            update_info();
        } else {
            playback(*selection);
        }
    }

    void step(int direction) {
        if (const auto selection = selected()) {
            const auto [section, index] = *selection;
            const auto target = guint(std::clamp(int(index) + direction, 0, int(count(section)) - 1));
            gtk_drop_down_set_selected(dropdown(section), target);
            playback({section, target});
        }
    }

    void update_progress() {
        gint64 duration = 0, position = 0;
        const bool available = current && gst_element_query_duration(pipeline, GST_FORMAT_TIME, &duration) &&
                               gst_element_query_position(pipeline, GST_FORMAT_TIME, &position) && duration > 0;
        if (available) {
            updating_progress = true;
            gtk_range_set_range(seek, 0, double(duration) / GST_SECOND);
            gtk_range_set_value(seek, double(position) / GST_SECOND);
            updating_progress = false;
        }
        gtk_widget_set_sensitive(GTK_WIDGET(seek), available);
    }

    void update_timer() {
        const bool needs_timer = window && gtk_widget_get_visible(GTK_WIDGET(window)) && playing;
        if (needs_timer && !timer) {
            timer = g_timeout_add(300, +[](gpointer data) -> gboolean {
                static_cast<Player *>(data)->update_progress();
                return G_SOURCE_CONTINUE;
            }, this);
        } else if (!needs_timer && timer) {
            g_source_remove(timer);
            timer = 0;
        }
    }

    void publish(bool active) {
        playing = active && current.has_value();
        const char *value = playing ? current->section == Section::music ? "music" : "quran" : "none";
        g_simple_action_set_state(state, g_variant_new_string(value));
        update_timer();
    }

    void on_message(GstMessage *message) {
        if (!window || !current)
            return;
        if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR) {
            GError *error = nullptr;
            gst_message_parse_error(message, &error, nullptr);
            Text text(g_strdup_printf("Audio unavailable: %s", error->message), g_free);
            g_error_free(error);
            stop(text.get());
        } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_EOS) {
            const auto [section, index] = *current;
            if (index + 1 < count(section)) {
                gtk_drop_down_set_selected(dropdown(section), index + 1);
                playback({section, index + 1});
            } else {
                stop();
            }
        } else if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_STATE_CHANGED && GST_MESSAGE_SRC(message) == GST_OBJECT(pipeline)) {
            GstState next_state;
            gst_message_parse_state_changed(message, nullptr, &next_state, nullptr);
            publish(next_state == GST_STATE_PLAYING && want_play);
            update_info();
        }
    }

    void refresh_controls() {
        const auto selection = selected();
        gtk_button_set_label(play, want_play && current == selection ? "Pause" : "Play");
        for (auto *control : {previous, play, next})
            gtk_widget_set_sensitive(GTK_WIDGET(control), selection.has_value() && pipeline);
        gtk_widget_set_sensitive(GTK_WIDGET(stop_button), current.has_value());
    }

    void update_info() {
        if (current) {
            const auto [section, index] = *current;
            Text title(section == Section::music ? g_filename_display_basename(files[index].c_str())
                                                 : g_strdup_printf("سورة %s", catalogue.get()[index]), g_free);
            Text message(g_strdup_printf("%s · %s", playing ? "Playing" : want_play ? "Loading" : "Paused",
                                         title.get()), g_free);
            gtk_label_set_text(status, message.get());
        } else {
            gtk_label_set_text(status, pipeline ? "Select audio to play." : "GStreamer playback is unavailable.");
        }
        refresh_controls();
        update_progress();
    }

    void stop(const char *message = nullptr) {
        if (pipeline)
            gst_element_set_state(pipeline, GST_STATE_NULL);
        current.reset();
        want_play = false;
        publish(false);
        update_info();
        if (message)
            gtk_label_set_text(status, message);
    }
};
}

int main(int argc, char **argv) {
    return Player{}.run(argc, argv);
}
