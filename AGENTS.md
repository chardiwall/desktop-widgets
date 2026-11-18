# Repository Guidelines

## Project Structure

The desktop avatar pipeline lives in `character/3d/`. `make_character.py` builds the model, `rig.py` binds its meshes to the armature, and `anim.py` creates Blender Actions and renders flipbook frames. `character_animated.blend` is the assembled scene. `clips/<action>/` contains numbered transparent PNG frames. `poses.py` renders reference poses, and `posesheet.py` combines them into `pose_sheet.png`.

## Build and Preview

Open `character_animated.blend` in Blender 5 to inspect the rig and actions. To rebuild, start Blender with the MCP for Blender add-on listening on `127.0.0.1:9876`. Use a scratch scene because the modeling script clears scene objects. In scratch copies of the render scripts, set `OUT` to an existing writable output directory and set `anim.py` to its `clips/` subdirectory. Run each command after the preceding stage succeeds, keeping the same Blender session.

```bash
cd character/3d
python3 bl.py make_character.py
python3 bl.py rig.py
python3 bl.py anim.py
```

Use the paths to your scratch scripts in these commands if they live elsewhere. After rigging, `python3 bl.py poses.py` renders pose stills. Run `posesheet.py` from the directory containing those stills with Python, Pycairo, and PyGObject with GDK 4, GdkPixbuf, and PangoCairo available.

## Coding Style and Naming

Use four spaces for Python indentation and `snake_case` for functions, pose names, and clip names. Preserve `.L` and `.R` bone suffixes and keep object names consistent across modeling, rigging, and animation. Keep clip frames zero-padded (`0001.png`).

## Testing

Use pose renders to inspect sleeve and robe deformation, hand placement, and the tasbih. For animation changes, scrub the affected action in Blender and check that its first and last frames return to the rest pose. Check the rendered PNGs for transparency, consecutive frame numbers, and smooth playback at 12 fps.

## Commits and Pull Requests

Use a short, descriptive commit subject, such as `Fix sleeve weights in the wave pose`. In the pull request, describe the change, list the poses or clips you checked, and link any related issue. Include a before-and-after render or preview for visible changes.
