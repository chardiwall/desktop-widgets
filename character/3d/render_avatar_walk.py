"""Render the Ubuntu pilot's out-and-back walk from the assembled character."""

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


FPS = 30
TURN = 8
STEP = 12
TRAVEL = 3 * STEP
LAST_FRAME = TURN + TRAVEL + TURN + TRAVEL + TURN
STEP_LENGTH = 0.48
REST_ANGLE = -15


def ease(progress):
    return progress * progress * (3 - 2 * progress)


def walk(frame):
    segment = min(frame // STEP, 2)
    phase = min(1, (frame - segment * STEP) / STEP)
    swing = ease(phase)
    lift = 0.13 * math.sin(math.pi * phase) ** 2
    if segment == 0:
        return STEP_LENGTH * phase ** 2 / 2, (0, 0), (STEP_LENGTH * swing, lift)
    if segment == 1:
        return STEP_LENGTH * (0.5 + phase), (2 * STEP_LENGTH * swing, lift), (STEP_LENGTH, 0)
    return STEP_LENGTH * (1.5 + phase - phase ** 2 / 2), (2 * STEP_LENGTH, 0), (STEP_LENGTH * (1 + swing), lift)


def pose(frame):
    if frame < TURN:
        return REST_ANGLE + (90 - REST_ANGLE) * ease(frame / TURN), 0, None
    if frame < TURN + TRAVEL:
        state = walk(frame - TURN)
        return 90, state[0], state
    frame -= TURN + TRAVEL
    if frame < TURN:
        return 90 - 180 * ease(frame / TURN), 2 * STEP_LENGTH, None
    if frame < TURN + TRAVEL:
        state = walk(frame - TURN)
        return -90, 2 * STEP_LENGTH - state[0], state
    frame -= TURN + TRAVEL
    return -90 + (REST_ANGLE + 90) * ease(frame / TURN), 0, None


def setup_scene(fps):
    scene = bpy.context.scene
    rig = bpy.data.objects["Rig"]
    root = bpy.data.objects["Character"]
    camera = scene.camera
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 4
    scene.render.resolution_x, scene.render.resolution_y = 160, 220
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.fps = fps
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.35
    camera.location = (0, -7.4, 1.16)
    camera.rotation_euler = (math.pi / 2, 0, 0)
    scene.view_layers[0].use_pass_z = False
    rig.animation_data_clear()
    bpy.data.objects["ShadowCatcher"].hide_render = True

    for bone in rig.pose.bones:
        bone.rotation_euler = (0, 0, 0)
        bone.location = (0, 0, 0)
    root.rotation_euler.z = math.radians(REST_ANGLE)
    bpy.context.view_layer.update()
    width, height = scene.render.resolution_x, scene.render.resolution_y
    ground = min((sole.matrix_world @ Vector(corner)).z
                 for sole in (bpy.data.objects["Sole.L"], bpy.data.objects["Sole.R"])
                 for corner in sole.bound_box)
    pivot = world_to_camera_view(scene, camera, Vector((0, 0, ground)))
    offset = world_to_camera_view(scene, camera, Vector((1, 0, ground)))
    pixels_per_unit = (offset.x - pivot.x) * width
    assert pixels_per_unit > 0 and 0 < pivot.y < 1
    return scene, rig, root, [pivot.x * width, (1 - pivot.y) * height], pixels_per_unit


def main(output, resume):
    scene, rig, root, pivot, pixels_per_unit = setup_scene(FPS)
    feet = [rig.pose.bones[f"foot.{side}"] for side in ("L", "R")]
    arms = [rig.pose.bones[f"upper_arm.{side}"] for side in ("L", "R")]
    inverse_bind = [foot.bone.matrix_local.to_3x3().inverted() for foot in feet]
    output.mkdir(parents=True, exist_ok=True)
    travel = []
    for frame in range(LAST_FRAME + 1):
        direction, distance, state = pose(frame)
        root.rotation_euler.z = math.radians(direction)
        pelvis, left, right = state or (0, (0, 0), (0, 0))
        for side, foot, arm, bind, (step, lift) in zip(
            (1, -1), feet, arms, inverse_bind, (left, right)
        ):
            foot.location = bind @ Vector((0, pelvis - step, lift))
            arm.rotation_euler.x = math.radians(side * 18 * (left[0] - right[0]) / STEP_LENGTH)
        travel.append(round(distance * pixels_per_unit, 4))
        scene.render.filepath = str(output / f"{frame + 1:04}.png")
        if not (resume and Path(scene.render.filepath).is_file()):
            bpy.ops.render.render(write_still=True)

    (output / "walk.json").write_text(json.dumps({
        "fps": FPS,
        "pivot": pivot,
        "travel": travel,
    }) + "\n")


if __name__ == "__main__":
    output, *options = sys.argv[sys.argv.index("--") + 1:]
    assert options in ([], ["--resume"])
    main(Path(output).resolve(), bool(options))
