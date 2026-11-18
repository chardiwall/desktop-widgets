#!/bin/sh
set -eu

output=$(realpath -m "${1:-dist/native}")
cd "$(dirname "$0")/.."
source_dir=desktop_widgets/widgets/avatar
mkdir -p "$output"
c++ -std=c++17 -O2 -Wall -Wextra -Werror -fPIC -shared \
    $(pkg-config --cflags glib-2.0) "$source_dir/motion.cpp" \
    -Wl,-soname,libdesktopwidgets-motion.so.0 -o "$output/libdesktopwidgets-motion.so.0" \
    $(pkg-config --libs glib-2.0)
ln -sfn libdesktopwidgets-motion.so.0 "$output/libdesktopwidgets-motion.so"
g-ir-scanner --quiet --warn-all --warn-error --namespace=DesktopWidgetsMotion --nsversion=1.0 \
    --identifier-prefix=DesktopWidgetsMotion --symbol-prefix=desktop_widgets_motion \
    --include=GLib-2.0 --pkg=glib-2.0 --library=desktopwidgets-motion --library-path="$output" \
    --output="$output/DesktopWidgetsMotion-1.0.gir" "$source_dir/motion.h"
g-ir-compiler "$output/DesktopWidgetsMotion-1.0.gir" -o "$output/DesktopWidgetsMotion-1.0.typelib"

c++ -std=c++20 -O2 -Wall -Wextra -Werror \
    $(pkg-config --cflags gtk4 gstreamer-1.0) "$source_dir/player.cpp" "$source_dir/media.cpp" \
    -o "$output/avatar-audio" $(pkg-config --libs gtk4 gstreamer-1.0)
