# Ubuntu avatar pilot

The avatar renderer runs in AzClock 16.1 on GNOME Shell 50. The standard Ubuntu package integrates it through the shared GNOME bridge, and the staged copy provides an isolated development preview. It uses the configured `clock/card` and `avatar/body` identifiers. The avatar stands at the right of the measured progress stroke, walks left to the edge of the clear space beside the rendered Clock text, and returns. The route is measured again when the Clock typography changes. The existing avatar placement is used as a still fallback. Click the avatar to request a walk or pause random walks. Automatic walks use a 60–180 second rest interval and honour GNOME's animation preference.

## Listening and rain

Click the avatar and choose **Music player…** or **القرآن · Al-Minshawi…**. The Music tab opens a local folder picker and lists supported files directly inside that folder. The Qur’an tab has a searchable Arabic list of all 114 surahs in Muhammad Siddiq Al-Minshawi’s Mujawwad recording. The selected surah streams when played. The player has play/pause, previous and next, seek when available, volume, stop, and quit. Closing the window during playback keeps audio playing. Open the player again from the avatar to bring back the controls. [Al-Minshawi’s Mujawwad recording source](https://www.mp3quran.net/eng/minsh_mjwd/)

Music and recitation use one player process and the same listening animation. The avatar moves toward the right end of the clock, sits and reclines, turns its tasbih, and shows headphones and rising notes. It leans at the wall when its feet can stay supported by the clock line. **Rain inside the clock** works independently of playback, with visual rain clipped to the card and an umbrella anchored to the free hand. The pose and props have entry and exit transitions. The effects stop while the avatar is hidden. Reduced Motion uses the settled pose with static effects.

## Build and preview

From the repository root, run the following with Blender 5 and Python with Pillow. The C++ player uses GTK 4 and GStreamer. Building it requires the corresponding development packages and GObject Introspection tools. Playback uses the installed audio codecs. Use a new render directory for a different scene or walk. The shipped Blender scene is read-only input.

```sh
blender -b character/3d/character_animated.blend -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_walk.py -- dist/avatar-walk
blender -b character/3d/character_animated.blend -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_listening.py -- dist/avatar-listening
sh packaging/build-native.sh
/usr/bin/python3 packaging/stage-avatar.py \
  "$HOME/.local/share/gnome-shell/extensions/azclock@azclock.gitlab.com" \
  dist/avatar-walk dist/avatar-pilot/gnome-shell/extensions/azclock@azclock.gitlab.com \
  --listening dist/avatar-listening
sh packaging/preview-avatar.sh
```

The preview starts a nested GNOME Shell with temporary settings and a sample clock card. It prepares the same AzClock hooks and Avatar assets as installation and runs the settings app from this checkout. Use an Ubuntu Wayland session with GNOME's development kit. Stage into a fresh destination. For an interrupted render made with the same scene and script, pass `--resume` after the output path to reuse completed frames.

## Realistic Blender avatars

Open `avatar/girl.blend`, `avatar/boy.blend`, or `avatar/omani.blend` in Blender 5. The girl wears a rose dress and apricot hijab. The boy wears a cream T-shirt, blue jeans, and light trainers. The Omani avatar wears an ivory dishdasha and embroidered kumma. The girl and Omani avatar sit cross-legged. The boy sits with his knees up and forearms across them. The models open at frame 13, with standing poses at frames 1 and 25. Textures are packed inside each Blender file.

Choose `girl`, `boy`, or `omani` when rendering a desktop build.

```sh
variant=girl
blender -b "avatar/$variant.blend" -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_walk.py -- "dist/avatar-realistic-$variant/walk"
blender -b "avatar/$variant.blend" -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_listening.py -- "dist/avatar-realistic-$variant/listening"
sh packaging/build-deb.sh "dist/avatar-realistic-$variant/walk" "dist/avatar-realistic-$variant/listening"
```

The face, rig, and several clothing assets use MakeHuman and MPFB's CC0 graphics data. The Blender builder at `character/3d/make_realistic_avatars.py` takes a source directory containing the MakeHuman `base.obj`, the MPFB default rig and weights as `rig.json` and `weights.json`, and the MakeHuman system asset pack extracted under `assets/`. Place the MakeHuman macrodetails targets `asian-female-young`, `caucasian-male-young`, and `asian-male-young` at `girl.target`, `boy.target`, and `omani.target`, and the female and male child counterparts at `girl-youth.target` and `boy-youth.target`. The last builder argument supplies the original Blender scene for its kumma embroidery.

```sh
blender -b --python-exit-code 1 -P character/3d/make_realistic_avatars.py -- \
  /path/to/makehuman-sources avatar "$variant" character/3d/character_animated.blend
```

[MakeHuman graphics license](https://www.makehumancommunity.org/about/license.html) · [System asset pack](https://download.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html) · [MPFB standard rig data](https://github.com/makehumancommunity/mpfb2/tree/master/src/mpfb/data/rigs/standard)

## Verification

```sh
/usr/bin/python3 -m unittest discover -s tests -v
gjs -m tests/widget-attachments.js
sh packaging/build-native.sh
GI_TYPELIB_PATH="$PWD/dist/native" LD_LIBRARY_PATH="$PWD/dist/native" gjs -m tests/avatar-motion.js
GI_TYPELIB_PATH="$PWD/dist/native" LD_LIBRARY_PATH="$PWD/dist/native" gjs -m tests/avatar-pilot.js
c++ -std=c++20 $(pkg-config --cflags gstreamer-1.0) tests/avatar-media.cpp \
  desktop_widgets/widgets/avatar/media.cpp -o dist/native/test-avatar-media \
  $(pkg-config --libs gstreamer-1.0)
dist/native/test-avatar-media
```

The motion check exercises shaped Arabic and Latin text, missing and narrow tracks, work-area and window overlap, missed animation callbacks, and playback of the seated transition. Staging validates the numbered frames, alpha bounds, ground baseline, neutral closing pose and texture budget. The listening pose shares the standing texture.

In the nested preview, request a walk, play a local file and a surah, toggle rain during each state, and cover and uncover the clock. Check the props follow the moving pose, that rain remains clipped to the card, and that pause returns to standing only when rain is off. Test input through the margins, GNOME Reduced Motion, and repeated disable/enable. Profile the real session only after this check passes. [GNOME development session](https://gjs.guide/extensions/development/debugging.html) · [Battery test plan](avatar-resource-estimate.md#first-measurement-gate)

The pilot waits for a clear route before starting a walk in background mode. Focus, prayer reminders and further actions follow this slice. The standard integration disables the legacy `desk-avatar.service` during installation so the GNOME bridge owns avatar placement. [Architecture and activity roster](avatar-architecture.md)
