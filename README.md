# Islamic Desktop Widgets

Three widgets for Ubuntu GNOME. The **Ayah reminder** shows a daily Qur’an verse in Arabic with an English translation. The **Clock** shows the time and date. The **Avatar** is an animated desktop character that can stand on the clock or use its own placement.

## How it fits together

The GTK settings app changes visibility, card themes and placement through the GNOME host. The panel menu provides quick controls. AzClock renders the configured widgets in GNOME Shell, so they stay visible after the settings app closes. Blender renders the avatar frames offline, and the packaging scripts prepare them for the Shell runtime.

[Open the architecture diagram](docs/repository-overview.html)

| Directory | Contents |
| --- | --- |
| `desktop_widgets/` | Settings app, card preferences, session controls and GNOME integration |
| `avatar/` | Avatar motion, Shell rendering, rain effects and audio player |
| `character/3d/` | Blender model, rig, actions and rendered clips |
| `packaging/` | Ubuntu package, avatar asset staging and isolated preview |
| `tests/` | Settings, host integration and animation checks |

## Build and check

The settings package targets an existing local **AzClock 16.1** setup. It uses GTK 4, libadwaita and PyGObject. See the [GNOME integration notes](docs/desktop-widget-settings-plan.md) for host assumptions and the [avatar pilot guide](docs/avatar-pilot.md) for Blender rendering and the nested Shell preview.

```sh
sh packaging/build-deb.sh
/usr/bin/python3 -m unittest discover -s tests -v
gjs -m tests/widget-attachments.js
gjs -m tests/avatar-motion.js
```
