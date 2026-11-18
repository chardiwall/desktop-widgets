# Pose tests for the rigged character (run via bl.py after rig.py). Renders one image per pose.
# Measured bone axes (character faces -Y): forearm X- bends the elbow forward; upper_arm X- swings the arm forward;
# upper_arm.R Z+ / upper_arm.L Z- lift the arm out to the side; head/spine X+ nod/lean forward; foot location Y+ = step forward.
import bpy, math

OUT = "/home/chardiwall/Documents/Programs/3D Avatar/character/3d"
scene = bpy.context.scene
rig = bpy.data.objects["Rig"]
root = bpy.data.objects["Character"]
rig.hide_render = True

POSES = {
    "salam_wave": {"upper_arm.R": (-5, 0, 98), "forearm.R": (-72, 0, 0), "hand.R": (0, 0, 15),
                   "head": (0, 0, 6), "upper_arm.L": (0, 0, -6)},
    "counting_tasbih": {"upper_arm.R": (-18, 0, -16), "forearm.R": (-112, 0, 0), "fingers.R": (25, 0, 0),
                        "head": (14, 0, -4), "upper_arm.L": (0, 0, -4)},
    "dua": {"upper_arm.L": (-32, 0, 12), "forearm.L": (-78, 0, 0), "hand.L": (25, -70, 0),
            "upper_arm.R": (-32, 0, -12), "forearm.R": (-78, 0, 0), "hand.R": (25, 70, 0), "head": (14, 0, 0)},
    "walking": {"foot.L": {"loc": (0, 0.07, 0), "rot": (-12, 0, 0)}, "foot.R": {"loc": (0, -0.06, 0), "rot": (10, 0, 0)},
                "upper_arm.L": (18, 0, -4), "upper_arm.R": (-18, 0, 4), "spine": (0, 0, 2), "head": (-4, 0, 0)},
    "thinking": {"upper_arm.R": (-42, 0, -4), "forearm.R": (-122, 0, 0), "hand.R": (-20, 0, 0),
                 "head": (-6, 0, -10), "upper_arm.L": (-10, 0, -2), "forearm.L": (-30, 0, 0)},
    "sleepy": {"head": (20, 0, 10), "spine": (5, 0, 0), "upper_arm.L": (4, 0, 2), "upper_arm.R": (4, 0, -2)},
}


def reset():
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)


def apply(pose):
    reset()
    for name, v in pose.items():
        pb = rig.pose.bones[name]
        rot, loc = (v.get("rot", (0, 0, 0)), v.get("loc", (0, 0, 0))) if isinstance(v, dict) else (v, (0, 0, 0))
        pb.rotation_euler = tuple(math.radians(a) for a in rot)
        pb.location = loc


cam = scene.camera
root.rotation_euler = (0, 0, math.radians(-20))
cam.location = (0, -7.4, 2.35)
cam.rotation_euler = (math.radians(82), 0, 0)
scene.render.resolution_x, scene.render.resolution_y = 600, 830
scene.cycles.samples = 48
done = []
for name, pose in POSES.items():
    apply(pose)
    bpy.context.view_layer.update()
    scene.render.filepath = f"{OUT}/pose_{name}.png"
    bpy.ops.render.render(write_still=True)
    done.append(name)
reset()
root.rotation_euler = (0, 0, 0)
scene.render.resolution_x, scene.render.resolution_y = 720, 1000
scene.cycles.samples = 96
print("posed:", ", ".join(done))
