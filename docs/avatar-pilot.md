# Ubuntu avatar pilot

This first slice adds a native avatar renderer to a staged copy of AzClock 16.1 on GNOME Shell 50. It uses the configured `clock/card` and `avatar/body` identifiers. The avatar stands on the measured progress stroke, walks out and back when enough space is clear, and uses the existing avatar placement as a still fallback. Click the avatar to request a walk or pause random walks. Automatic walks use a 60–180 second rest interval and honour GNOME's animation preference.

## Listening and rain

Click the avatar and choose **Music player…** or **القرآن · Al-Minshawi…**. The Music tab opens a local folder picker and lists supported files directly inside that folder. The Qur’an tab has a searchable Arabic list of all 114 surahs in Muhammad Siddiq Al-Minshawi’s Mujawwad recording. The selected surah streams when played. The player has play/pause, previous and next, seek when available, volume, stop, and quit. Closing the window during playback keeps audio playing. Open the player again from the avatar to bring back the controls. [Al-Minshawi’s Mujawwad recording source](https://www.mp3quran.net/eng/minsh_mjwd/)

Music and recitation use one player process and the same listening animation. The avatar moves toward the right end of the clock, sits and reclines, turns its tasbih, and shows headphones and rising notes. It leans at the wall when its feet can stay supported by the clock line. **Rain inside the clock** works independently of playback, with visual rain clipped to the card and an umbrella anchored to the free hand. The pose and props have entry and exit transitions. The effects stop while the avatar is hidden. Reduced Motion uses the settled pose with static effects.

## Build and preview

From the repository root, run the following with Blender 5 and Python with Pillow. Playback uses the Ubuntu GTK 4 and GStreamer bindings and installed audio codecs. Use a new render directory for a different scene or walk. The shipped Blender scene is read-only input.

```sh
blender -b character/3d/character_animated.blend -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_walk.py -- dist/avatar-walk
blender -b character/3d/character_animated.blend -t 3 --python-exit-code 1 \
  -P character/3d/render_avatar_listening.py -- dist/avatar-listening
/usr/bin/python3 packaging/stage-avatar.py \
  "$HOME/.local/share/gnome-shell/extensions/azclock@azclock.gitlab.com" \
  dist/avatar-walk dist/avatar-pilot/gnome-shell/extensions/azclock@azclock.gitlab.com \
  --listening dist/avatar-listening
sh packaging/preview-avatar.sh
```

The preview starts a nested GNOME Shell using temporary settings and a sample clock card. Use a regular Ubuntu Wayland session with GNOME's development kit available. The staging command refuses to overwrite an existing destination. For an interrupted render made with the same scene and script, pass `--resume` after the output path to reuse completed frames.

## Verification

```sh
gjs -m tests/avatar-motion.js
/usr/bin/python3 -m unittest discover -s tests -v
```

The motion check exercises shaped Arabic and Latin text, missing and narrow tracks, work-area and window overlap, missed animation callbacks, and playback of the seated transition. Staging validates the numbered frames, alpha bounds, ground baseline, neutral closing pose and texture budget. The listening pose shares the standing texture.

In the nested preview, request a walk, play a local file and a surah, toggle rain during each state, and cover and uncover the clock. Check the props follow the moving pose, that rain remains clipped to the card, and that pause returns to standing only when rain is off. Test input through the margins, GNOME Reduced Motion, and repeated disable/enable. Profile the real session only after this check passes. [GNOME development session](https://gjs.guide/extensions/development/debugging.html) · [Battery test plan](avatar-resource-estimate.md#first-measurement-gate)

The current pilot uses one fixed-size outfit. It conservatively pauses in background mode when a window intersects the available route. Focus, prayer reminders and further actions follow this slice. Before adopting the staged renderer in the existing desktop, migrate ownership from `desk-avatar.service` so a single player owns avatar placement. [Architecture and activity roster](avatar-architecture.md)
