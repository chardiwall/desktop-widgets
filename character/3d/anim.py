# Animation clips for the rigged character (run via bl.py after rig.py).
# Each clip is its own Action, starts and ends in the rest pose (so clips chain in any order),
# and renders to clips/<name>/0001.png ... as transparent frames for battery-light flipbook playback.
# Bone axes (character faces -Y): forearm X- bends the elbow forward; upper_arm X- swings forward;
# upper_arm.R Z+ / .L Z- raise sideways; head/spine X+ nod/lean forward, Z+ tilts towards -X.
import bpy, math, os

OUT = "/home/chardiwall/Documents/Programs/3D Avatar/character/3d/clips"
FPS = 12
scene = bpy.context.scene
rig = bpy.data.objects["Rig"]
root = bpy.data.objects["Character"]
rig.hide_render = True
REST = {}                                    # bones keyed in a clip always return to zero


def fcurves(act):
    """Blender 5 layered actions: curves live in layers -> strips -> channel bags."""
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                yield from bag.fcurves


def new_action(name):
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = act
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    return act


def key(frame, pose):
    """pose: {bone: (rx, ry, rz) degrees} or {bone: {"rot": (...), "loc": (...)}}; unlisted bones keep their values."""
    for name, v in pose.items():
        pb = rig.pose.bones[name]
        rot, loc = (v.get("rot"), v.get("loc")) if isinstance(v, dict) else (v, None)
        if rot is not None:
            pb.rotation_euler = tuple(math.radians(a) for a in rot)
            pb.keyframe_insert("rotation_euler", frame=frame)
        if loc is not None:
            pb.location = loc
            pb.keyframe_insert("location", frame=frame)


def rest(frame, bones):
    key(frame, {b: (0, 0, 0) for b in bones})


Z = (0, 0, 0)
CLIPS = {}


def clip(fn):
    CLIPS[fn.__name__] = fn
    return fn


@clip
def idle():                                   # 4 s loop: breathing, gentle sway, slow head drift
    b = ["chest", "spine", "head", "upper_arm.L", "upper_arm.R"]
    rest(1, b)
    key(13, {"chest": (-2.5, 0, 0), "spine": (0, 0, 1.2), "head": (-2, 0, 2.5), "upper_arm.L": (0, 0, -2), "upper_arm.R": (0, 0, 2)})
    key(25, {"chest": (0, 0, 0), "spine": (0, 0, 0), "head": (1, 0, 0), "upper_arm.L": Z, "upper_arm.R": Z})
    key(37, {"chest": (-2.5, 0, 0), "spine": (0, 0, -1.2), "head": (-2, 0, -2.5), "upper_arm.L": (0, 0, 2), "upper_arm.R": (0, 0, -2)})
    rest(49, b)
    return 48


@clip
def salam_wave():                             # 3 s: raise, three waves, lower
    b = ["upper_arm.R", "forearm.R", "hand.R", "head", "chest"]
    rest(1, b)
    up = {"upper_arm.R": (-5, 0, 98), "forearm.R": (-72, 0, 0), "head": (0, 0, 6), "chest": (0, 0, 3)}
    key(9, {**up, "hand.R": (0, 0, 0)})
    for i, f in enumerate((13, 17, 21, 25)):
        key(f, {"hand.R": (0, 0, 22 if i % 2 == 0 else -14), "forearm.R": (-72 + (6 if i % 2 == 0 else -6), 0, 0)})
    key(29, {**up, "hand.R": Z})
    rest(37, b)
    return 36


@clip
def counting_tasbih():                        # 4 s: bring beads up, four thumb counts, lower
    b = ["upper_arm.R", "forearm.R", "fingers.R", "thumb.R", "head"]
    rest(1, b)
    hold = {"upper_arm.R": (-18, 0, -16), "forearm.R": (-112, 0, 0), "fingers.R": (25, 0, 0), "head": (14, 0, -4)}
    key(9, {**hold, "thumb.R": Z})
    for f in (13, 21, 29, 37):
        key(f, {"thumb.R": (30, 0, 0), "head": (16, 0, -4)})        # thumb pulls a bead
        key(f + 4, {"thumb.R": (0, 0, 0), "head": (14, 0, -4)})
    key(41, hold)
    rest(49, b)
    return 48


@clip
def walk():                                   # 2 s loop in place: steps, arm swing, bob
    b = ["foot.L", "foot.R", "upper_arm.L", "upper_arm.R", "spine", "root", "head"]
    rest(1, b)
    for f, s in ((1, 1), (7, 0), (13, -1), (19, 0), (25, 1)):
        key(f, {"foot.L": {"rot": (-12 * s, 0, 0), "loc": (0, 0.07 * s, 0.02 * (s < 0))},
                "foot.R": {"rot": (12 * s, 0, 0), "loc": (0, -0.07 * s, 0.02 * (s > 0))},
                "upper_arm.L": (16 * s, 0, -3), "upper_arm.R": (16 * s, 0, 3),
                "spine": (0, 0, 2 * s), "root": {"rot": Z, "loc": (0, 0, 0.025 * (s == 0))}, "head": (-3, 0, -s)})
    return 24


@clip
def dua():                                    # 4 s: raise open hands, hold with a slight bow, lower
    b = ["upper_arm.L", "forearm.L", "hand.L", "upper_arm.R", "forearm.R", "hand.R", "head", "chest"]
    rest(1, b)
    hands = {"upper_arm.L": (-32, 0, 12), "forearm.L": (-78, 0, 0), "hand.L": (25, -70, 0),
             "upper_arm.R": (-32, 0, -12), "forearm.R": (-78, 0, 0), "hand.R": (25, 70, 0)}
    key(11, {**hands, "head": (10, 0, 0), "chest": Z})
    key(23, {**hands, "head": (16, 0, 0), "chest": (3, 0, 0)})
    key(33, {**hands, "head": (14, 0, 0), "chest": (2, 0, 0)})
    rest(49, b)
    return 48


@clip
def sleepy():                                 # 5 s: drifting off, a nod, waking back up
    b = ["head", "spine", "chest", "upper_arm.L", "upper_arm.R"]
    rest(1, b)
    key(19, {"head": (16, 0, 8), "spine": (4, 0, 0), "chest": (3, 0, 0), "upper_arm.L": (4, 0, 2), "upper_arm.R": (4, 0, -2)})
    key(31, {"head": (26, 0, 12), "spine": (6, 0, 0)})
    key(35, {"head": (6, 0, 2), "spine": (1, 0, 0)})                 # the nod: jerks awake
    key(45, {"head": (18, 0, 9), "spine": (4, 0, 0)})
    rest(61, b)
    return 60


def ease(act):
    for fc in fcurves(act):
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.easing = "AUTO"
            k.handle_left_type = k.handle_right_type = "AUTO_CLAMPED"


# ---------------------------------------------------------------- render setup: Eevee, transparent, desktop size
floor = bpy.data.objects.get("ShadowCatcher")
if floor:
    floor.hide_render = True                  # Eevee can't do shadow catchers; desktop frames have no floor
scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = True
scene.render.fps = FPS
scene.render.resolution_x, scene.render.resolution_y = 360, 500
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
cam = scene.camera
root.rotation_euler = (0, 0, math.radians(-15))
cam.location = (0, -7.4, 2.35)
cam.rotation_euler = (math.radians(82), 0, 0)

summary = []
for name, build in CLIPS.items():
    act = new_action(f"clip_{name}")
    last = build()
    ease(act)
    scene.frame_start, scene.frame_end = 1, last
    os.makedirs(f"{OUT}/{name}", exist_ok=True)
    scene.render.filepath = f"{OUT}/{name}/"
    bpy.ops.render.render(animation=True)
    summary.append(f"{name}:{last}f")

rig.animation_data.action = None
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
    pb.location = (0, 0, 0)
root.rotation_euler = (0, 0, 0)
if floor:
    floor.hide_render = False
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/../character_animated.blend")
print("clips:", ", ".join(summary))
