# Islamic Desktop Widgets

Three widgets for Ubuntu GNOME. The **Ayah reminder** shows a daily Qur’an verse in Arabic with an English translation. The **Clock** shows the time and date. The **Avatar** can stand and walk on the clock, fall back to its own desktop position, and react to music or Qur’an playback.

## How it fits together

The GTK settings app changes visibility, card themes and placement through one desktop bridge. The GNOME implementation uses GSettings and AzClock 16.1. AzClock keeps the widgets visible after settings closes. Blender renders the avatar frames offline. The packaging tools crop and pack them for the GNOME renderer, which uses C++ for motion and launches a C++ audio player on demand.

[![Architecture diagram showing the settings app and panel menu feeding one shared GNOME bridge for Ayah reminder, Clock, and Avatar](docs/repository-overview.svg)](docs/repository-overview.html)

| Directory | Contents |
| --- | --- |
| `desktop_widgets/widgets/ayah/` | Ayah reminder theme presets |
| `desktop_widgets/widgets/clock/` | Clock theme presets |
| `desktop_widgets/widgets/avatar/` | Motion, music and Qur’an playback |
| `desktop_widgets/bridge/` | Shared GNOME/AzClock integration, panel, placement and rendering |
| `desktop_widgets/app.py` | GTK settings window and commands |
| `character/3d/` | Blender scene, rig, actions and offline renders |
| `packaging/` and `tests/` | Ubuntu package, preview and verification |

## Build and install

Build on Ubuntu with Blender 5, Python 3 with Pillow and PyGObject, a C++20 compiler, pkg-config, GObject Introspection, GTK 4 and GStreamer development files. Render the walk and listening frames using the [avatar build guide](docs/avatar-pilot.md). Then run:

```sh
sh packaging/build-deb.sh
sudo apt install "./dist/desktop-widget-settings_0.4.0_$(dpkg --print-architecture).deb"
desktop-widget-settings --install-gnome-integration
```

The last command backs up a local AzClock 16.1 installation and transfers ownership from the legacy desktop avatar service. Log out and back in to load the bridge. The GNOME configuration needs the existing widget IDs `ayah/verse`, `clock/card` and `avatar/body`. For development, use the [isolated preview and checks](docs/avatar-pilot.md#verification).
