#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
uuid=azclock@azclock.gitlab.com
data=${1:-"$(pwd)/dist/avatar-pilot"}
extension="$data/gnome-shell/extensions/$uuid"
bundle=
if [ -f "$extension/extension.js" ]; then
    bundle=$(sed -n "s|^import {.*displayedWidgets} from './\\(desktop-widget-settings/[^']*\\)/bridge/attachments.js';$|\\1|p" \
        "$extension/extension.js")
fi
if [ -z "$bundle" ] || [ ! -f "$extension/$bundle/widgets/avatar/walk.rgba" ]; then
    echo "Stage the avatar pilot before opening the preview." >&2
    exit 1
fi

export GI_TYPELIB_PATH="$(pwd)/dist/native${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
export LD_LIBRARY_PATH="$(pwd)/dist/native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
preview=$(mktemp -d)
database="desktop_widgets_preview_$$"
trap 'rm -rf "$preview"; if [ -n "${XDG_RUNTIME_DIR:-}" ]; then rm -f "$XDG_RUNTIME_DIR/dconf/$database"; fi' EXIT
export XDG_CONFIG_HOME="$preview/config" XDG_CACHE_HOME="$preview/cache" XDG_STATE_HOME="$preview/state"
export XDG_DATA_HOME="$data" GSETTINGS_BACKEND=dconf DCONF_PROFILE="$preview/dconf-profile"
mkdir -p "$XDG_CONFIG_HOME"
printf 'user-db:%s\n' "$database" > "$DCONF_PROFILE"
export PYTHONPATH="$(pwd)${PYTHONPATH:+:$PYTHONPATH}"
export PATH="$preview/bin:$PATH"
export XDG_DATA_DIRS="$preview/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export GSETTINGS_SCHEMA_DIR="$preview/share/glib-2.0/schemas"
install -D -m 644 packaging/io.github.desktopwidgets.Settings.gschema.xml \
    "$GSETTINGS_SCHEMA_DIR/io.github.desktopwidgets.Settings.gschema.xml"
/usr/bin/glib-compile-schemas --strict "$GSETTINGS_SCHEMA_DIR"
install -D -m 644 packaging/io.github.desktopwidgets.Settings.desktop \
    "$preview/share/applications/io.github.desktopwidgets.Settings.desktop"
mkdir -p "$preview/bin"
cat > "$preview/bin/desktop-widget-settings" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 -B -m desktop_widgets.app "$@"
LAUNCHER
chmod +x "$preview/bin/desktop-widget-settings"

/usr/bin/dbus-run-session --dbus-daemon=/usr/bin/dbus-daemon -- sh -eu -s -- "$extension" "$(pwd)" "$uuid" <<'SESSION'
extension=$1
root=$2
uuid=$3
schema=org.gnome.shell.extensions.azclock
settings_path=/org/gnome/shell/extensions/azclock/widget-data
set_azclock() {
    /usr/bin/gsettings --schemadir "$extension/schemas" set "$@"
}
clock="$schema.widget-data:$settings_path/clock/"
clock_card="$schema.element-data:$settings_path/clock/element-data/card/"
avatar="$schema.widget-data:$settings_path/avatar/"
avatar_body="$schema.element-data:$settings_path/avatar/element-data/body/"

set_azclock "$schema" widgets "[{'avatar': <{'enabled': <true>}>}, {'clock': <{'enabled': <true>}>}]"
set_azclock "$clock" elements "[{'card': <{'enabled': <true>}>}]"
set_azclock "$clock" convert-old-location-done true
set_azclock "$clock" location-data '{"monitorIndex":0,"relativeX":0.1,"relativeY":0.4}'
set_azclock "$clock" lock-widget true
set_azclock "$clock_card" element-type Text_Label
set_azclock "$clock_card" font-family-override "(true, 'DejaVu Sans Mono')"
set_azclock "$clock_card" font-size 14
set_azclock "$clock_card" text '<span size="44pt">12:30</span><span size="16pt">:15</span>
Wednesday, 18 November
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
50% of the day'
set_azclock "$avatar" elements "[{'body': <{'enabled': <true>}>}]"
set_azclock "$avatar" anchor-point Bottom_Left
set_azclock "$avatar" lock-widget true
set_azclock "$avatar" convert-old-location-done true
set_azclock "$avatar" location-data '{"monitorIndex":0,"relativeX":0.05,"relativeY":0.9}'
set_azclock "$avatar_body" element-type Image_Element
set_azclock "$avatar_body" image-path "$root/dist/avatar-walk/0001.png"
set_azclock "$avatar_body" image-size 163
/usr/bin/gsettings set org.gnome.shell disable-user-extensions false
/usr/bin/gsettings set org.gnome.shell enabled-extensions "['$uuid']"

exec gnome-shell --devkit --wayland --no-x11
SESSION
