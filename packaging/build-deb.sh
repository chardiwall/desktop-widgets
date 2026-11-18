#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
version=0.4.0
package=desktop-widget-settings
architecture=$(dpkg-architecture -qDEB_HOST_ARCH)
multiarch=$(dpkg-architecture -qDEB_HOST_MULTIARCH)
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT

library="$staging/usr/lib/$package"
install -d "$staging/DEBIAN" "$library/desktop_widgets"
for file in desktop_widgets/*.py desktop_widgets/bridge/*.py desktop_widgets/bridge/*.js \
    desktop_widgets/widgets/ayah/*.py desktop_widgets/widgets/clock/*.py desktop_widgets/widgets/avatar/*.js; do
    install -D -m 644 "$file" "$library/$file"
done
/usr/bin/python3 packaging/stage-avatar.py --pack-only \
    "${1:-dist/avatar-walk}" "$library/desktop_widgets/widgets/avatar" \
    --listening "${2:-dist/avatar-listening}"
sh packaging/build-native.sh "$staging/native"
install -D -m 644 "$staging/native/libdesktopwidgets-motion.so.0" \
    "$staging/usr/lib/$multiarch/libdesktopwidgets-motion.so.0"
install -D -m 644 "$staging/native/DesktopWidgetsMotion-1.0.typelib" \
    "$staging/usr/lib/$multiarch/girepository-1.0/DesktopWidgetsMotion-1.0.typelib"
install -m 755 "$staging/native/avatar-audio" "$library/desktop_widgets/widgets/avatar/avatar-audio"
rm -r "$staging/native"
install -D -m 755 packaging/desktop-widget-settings "$staging/usr/bin/$package"
install -D -m 644 packaging/io.github.desktopwidgets.Settings.desktop \
    "$staging/usr/share/applications/io.github.desktopwidgets.Settings.desktop"
install -D -m 644 packaging/io.github.desktopwidgets.Settings.gschema.xml \
    "$staging/usr/share/glib-2.0/schemas/io.github.desktopwidgets.Settings.gschema.xml"
install -D -m 644 packaging/icons/io.github.desktopwidgets.Settings.svg \
    "$staging/usr/share/icons/hicolor/scalable/apps/io.github.desktopwidgets.Settings.svg"
install -D -m 644 packaging/icons/io.github.desktopwidgets.Settings-symbolic.svg \
    "$staging/usr/share/icons/hicolor/symbolic/apps/io.github.desktopwidgets.Settings-symbolic.svg"
cat > "$staging/DEBIAN/control" <<CONTROL
Package: $package
Version: $version
Architecture: $architecture
Section: x11
Priority: optional
Maintainer: Desktop Widgets contributors
Depends: libc6, libgcc-s1, libstdc++6, libglib2.0-0t64, python3, python3-gi, gir1.2-gtk-4.0 (>= 4.10), gir1.2-adw-1 (>= 1.6), gir1.2-pango-1.0, libgstreamer1.0-0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good
Description: Settings for an existing GNOME desktop widget setup
 Control the Ayah reminder, Clock and Avatar configured in AzClock.
 Set themes, colours, display and position for the Ayah and Clock cards.
 Includes a GNOME status menu for quick controls and quitting the widgets.
CONTROL
mkdir -p dist
dpkg-deb --root-owner-group --build "$staging" "dist/${package}_${version}_${architecture}.deb"
