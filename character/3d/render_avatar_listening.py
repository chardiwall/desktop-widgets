"""Render the listening transition and a seated bead-turn cycle."""

import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_avatar_walk import ease, setup_scene


def render(output):
    fps, transition, loop = 18, 12, 12
    scene, rig, root, _, _ = setup_scene(fps)
    robe = bpy.data.objects["Dishdasha"]
    robe.shape_key_add(name="Basis")
    seat = robe.shape_key_add(name="Seated")
    for vertex in seat.data:
        lower = max(0, min(1, (0.78 - vertex.co.z) / 0.78))
        vertex.co.z += 0.39 * lower
        vertex.co.y -= 0.40 * lower + 0.24 * math.sin(math.pi * lower)

    def offset(name, x, y, z):
        bone = rig.pose.bones[name]
        bone.location = bone.bone.matrix_local.to_3x3().inverted() @ Vector((x, y, z))

    def lean(name, degrees):
        bone = rig.pose.bones[name]
        bind = bone.bone.matrix_local.to_quaternion()
        bone.rotation_mode = "QUATERNION"
        bone.rotation_quaternion = bind.inverted() @ Quaternion((0, 1, 0), math.radians(degrees)) @ bind

    def screen(point):
        projected = world_to_camera_view(scene, scene.camera, point)
        return [round(projected.x * scene.render.resolution_x, 2),
                round((1 - projected.y) * scene.render.resolution_y, 2)]

    output.mkdir(parents=True, exist_ok=True)
    anchors = []
    for frame in range(transition + loop):
        seated = ease(min(1, frame / transition))
        bead = 0 if frame <= transition else math.sin(math.pi * (frame - transition) / loop) ** 2
        root.rotation_euler.z = math.radians(-15 - 13 * seated)
        seat.value = seated
        offset("root", 0, 0, -0.39 * seated)
        for side in ("L", "R"):
            offset(f"foot.{side}", 0, -0.42 * seated, 0.39 * seated)
        lean("spine", 13 * seated)
        lean("neck", -4 * seated)
        rig.pose.bones["upper_arm.R"].rotation_euler = (
            math.radians(-16 * seated), 0, math.radians(-15 * seated))
        rig.pose.bones["forearm.R"].rotation_euler.x = math.radians(-102 * seated)
        rig.pose.bones["fingers.R"].rotation_euler.x = math.radians(22 * seated)
        rig.pose.bones["thumb.R"].rotation_euler.x = math.radians(32 * bead)
        rig.pose.bones["forearm.L"].rotation_euler.x = math.radians(-48 * seated)
        bpy.context.view_layer.update()
        head = rig.pose.bones["head"]
        cap = screen(rig.matrix_world @ head.matrix @ Vector((0, 0.47, 0)))
        hand = screen(rig.matrix_world @ rig.pose.bones["hand.L"].tail)
        anchors.append({"head": cap, "hand": hand})
        scene.render.filepath = str(output / f"{frame + 1:04}.png")
        bpy.ops.render.render(write_still=True)

    (output / "listening.json").write_text(json.dumps({
        "fps": fps, "seated": transition, "anchors": anchors,
    }) + "\n")


if __name__ == "__main__":
    render(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
