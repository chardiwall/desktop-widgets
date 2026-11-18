#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
uuid=azclock@azclock.gitlab.com
data=${1:-"$(pwd)/dist/avatar-pilot"}
extension="$data/gnome-shell/extensions/$uuid"
if [ ! -f "$extension/desktop-widget-settings/desktop_widgets/widgets/avatar/walk.rgba" ]; then
    echo "Stage the avatar pilot before opening the preview." >&2
    exit 1
fi

sh packaging/build-native.sh
install -m 755 dist/native/avatar-audio "$extension/desktop-widget-settings/desktop_widgets/widgets/avatar/avatar-audio"
export GI_TYPELIB_PATH="$(pwd)/dist/native${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
export LD_LIBRARY_PATH="$(pwd)/dist/native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
preview=$(mktemp -d)
trap 'rm -rf "$preview"' EXIT
export XDG_CONFIG_HOME="$preview/config" XDG_CACHE_HOME="$preview/cache" XDG_STATE_HOME="$preview/state"
export XDG_DATA_HOME="$data" GSETTINGS_BACKEND=keyfile

schema=org.gnome.shell.extensions.azclock
settings_path=/org/gnome/shell/extensions/azclock/widget-data
set_azclock() {
    gsettings --schemadir "$extension/schemas" set "$@"
}
clock="$schema.widget-data:$settings_path/clock/"
clock_card="$schema.element-data:$settings_path/clock/element-data/card/"
avatar="$schema.widget-data:$settings_path/avatar/"
avatar_body="$schema.element-data:$settings_path/avatar/element-data/body/"

set_azclock "$schema" widgets "[{'avatar': <{'enabled': <true>}>}, {'clock': <{'enabled': <true>}>}]"
set_azclock "$clock" elements "[{'card': <{'enabled': <true>}>}]"
set_azclock "$clock" location-data '{"monitorIndex":0,"relativeX":0.1,"relativeY":0.4}'
set_azclock "$clock" lock-widget true
set_azclock "$clock_card" element-type Text_Label
set_azclock "$clock_card" font-family-override "(true, 'DejaVu Sans Mono')"
set_azclock "$clock_card" text '<span size="44pt">12:30</span><span size="16pt">:15</span>
Wednesday, 18 November
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
50% of the day'
set_azclock "$avatar" elements "[{'body': <{'enabled': <true>}>}]"
set_azclock "$avatar" anchor-point Bottom_Left
set_azclock "$avatar" lock-widget true
set_azclock "$avatar" location-data '{"monitorIndex":0,"relativeX":0.05,"relativeY":0.9}'
set_azclock "$avatar_body" element-type Image_Element
set_azclock "$avatar_body" image-path "$(pwd)/dist/avatar-walk/0001.png"
set_azclock "$avatar_body" image-size 163
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell enabled-extensions "['$uuid']"

dbus-run-session -- gnome-shell --devkit --wayland --no-x11
