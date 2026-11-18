# Rig the character built by make_character.py (run after it, in the same Blender, via bl.py).
# Skeleton: root > spine > chest > neck > head; chest > upper_arm > forearm > hand > (thumb, fingers); root > foot.
# Every mesh gets an Armature modifier (first in the stack) with vertex groups:
#   rigid parts -> one bone at weight 1; sleeves -> blended along shoulder/elbow/wrist; robe -> spine/chest blend.
import bpy, math
from mathutils import Vector

OUT = "/home/chardiwall/Documents/Programs/3D Avatar/character/3d"
scene = bpy.context.scene
root = bpy.data.objects["Character"]
root.rotation_euler = (0, 0, 0)

# joint positions, must match make_character.py
J = {}
for sx, s in ((1, "L"), (-1, "R")):
    J[f"sh.{s}"] = Vector((sx * 0.33, 0.0, 1.24))
    J[f"el.{s}"] = Vector((sx * 0.415, 0.0, 0.99))
    J[f"wr.{s}"] = Vector((sx * 0.40, -0.13, 0.77))

# ---------------------------------------------------------------- armature
for o in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    bpy.data.objects.remove(o, do_unlink=True)
arm_data = bpy.data.armatures.new("Rig")
rig = bpy.data.objects.new("Rig", arm_data)
scene.collection.objects.link(rig)
rig.parent = root
rig.show_in_front = True
bpy.context.view_layer.objects.active = rig
for o in bpy.context.selected_objects:
    o.select_set(False)
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones


def bone(name, head, tail, parent=None, connect=False, roll=0.0):
    b = eb.new(name)
    b.head, b.tail, b.roll = Vector(head), Vector(tail), roll
    if parent:
        b.parent = eb[parent]
        b.use_connect = connect
    return b

bone("root", (0, 0, 0), (0, 0, 0.3))
bone("spine", (0, 0, 0.75), (0, 0, 1.15), "root")
bone("chest", (0, 0, 1.15), (0, 0, 1.38), "spine", True)
bone("neck", (0, 0, 1.38), (0, 0, 1.56), "chest", True)
bone("head", (0, 0, 1.56), (0, 0, 2.30), "neck", True)
for sx, s in ((1, "L"), (-1, "R")):
    sh, el, wr = J[f"sh.{s}"], J[f"el.{s}"], J[f"wr.{s}"]
    bone(f"upper_arm.{s}", sh, el, "chest")
    bone(f"forearm.{s}", el, wr, f"upper_arm.{s}", True)
    hand_tip = wr + (wr - el).normalized() * 0.11
    bone(f"hand.{s}", wr, hand_tip, f"forearm.{s}", True)
    bone(f"thumb.{s}", (sx * 0.38, -0.20, 0.69), (sx * 0.34, -0.24, 0.60), f"hand.{s}")
    bone(f"fingers.{s}", (sx * 0.40, -0.13, 0.60), (sx * 0.36, -0.13, 0.50), f"hand.{s}")
    bone(f"foot.{s}", (sx * 0.15, 0.02, 0.10), (sx * 0.15, -0.22, 0.05), "root")
# tasbih: follows the right fingers' position but not their rotation, so the beads always hang down
tb = bone("tasbih", (-0.37, -0.16, 0.535), (-0.37, -0.16, 0.20), "fingers.R")
tb.use_inherit_rotation = False
bpy.ops.object.mode_set(mode="OBJECT")
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"


# ---------------------------------------------------------------- binding helpers
def realize(obj):
    """Bake the skin modifier into real geometry (vertex groups need real vertices); keep the subdivision."""
    if "Skin" not in obj.modifiers:
        return
    sub = obj.modifiers.get("Smooth")
    if sub:
        sub.show_viewport = sub.show_render = False
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.data = me
    bpy.data.meshes.remove(old)
    obj.modifiers.remove(obj.modifiers["Skin"])
    if sub:
        sub.show_viewport = sub.show_render = True


def armature_mod(obj):
    m = obj.modifiers.get("Armature") or obj.modifiers.new("Armature", "ARMATURE")
    m.object = rig
    obj.modifiers.move(list(obj.modifiers).index(m), 0)       # deform before smoothing/solidify


def rigid(obj, bone_name):
    obj.vertex_groups.clear()
    g = obj.vertex_groups.new(name=bone_name)
    g.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    armature_mod(obj)


def seg_t(p, a, b):
    ab = b - a
    return max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))


def sleeve(obj, s):
    """Blend weights around the elbow so it bends softly; shoulder end follows the chest a little."""
    realize(obj)
    obj.vertex_groups.clear()
    up, fo, ch = (obj.vertex_groups.new(name=n) for n in (f"upper_arm.{s}", f"forearm.{s}", "chest"))
    sh, el, wr = J[f"sh.{s}"], J[f"el.{s}"], J[f"wr.{s}"]
    mw = obj.matrix_world
    for v in obj.data.vertices:
        p = mw @ v.co
        d1 = (p - (sh + (el - sh) * seg_t(p, sh, el))).length
        d2 = (p - (el + (wr - el) * seg_t(p, el, wr))).length
        w_fore = 1 / (1 + math.exp(-(d1 - d2) / 0.025))          # smooth switch across the elbow
        t_sh = seg_t(p, sh, el)
        w_chest = max(0.0, 0.35 - t_sh) / 0.35 * 0.6 if w_fore < 0.5 else 0.0
        up.add([v.index], (1 - w_fore) * (1 - w_chest), "REPLACE")
        fo.add([v.index], w_fore, "REPLACE")
        if w_chest:
            ch.add([v.index], w_chest, "REPLACE")
    armature_mod(obj)


def robe(obj):
    obj.vertex_groups.clear()
    sp, ch = obj.vertex_groups.new(name="spine"), obj.vertex_groups.new(name="chest")
    for v in obj.data.vertices:
        z = (obj.matrix_world @ v.co).z
        w = max(0.0, min(1.0, (z - 1.0) / 0.25))                 # chest above 1.25, spine below 1.0
        sp.add([v.index], 1 - w, "REPLACE")
        ch.add([v.index], w, "REPLACE")
    armature_mod(obj)


# ---------------------------------------------------------------- bind every part
for o in list(bpy.data.objects):
    if o.type != "MESH" or o.name == "ShadowCatcher":
        continue
    n = o.name
    base, side = (n.split(".")[0], n.split(".")[-1] if "." in n else "")
    if base == "Sleeve":
        sleeve(o, side)
    elif base == "Dishdasha":
        robe(o)
    elif base in ("Head", "Ear", "Hair", "Kumma", "KummaTop"):
        rigid(o, "head")
    elif base == "Neck":
        rigid(o, "neck")
    elif base in ("Neckline", "Slit", "TasselCord", "TasselCord1", "Tassel"):
        rigid(o, "chest")
    elif base == "Palm":
        rigid(o, f"hand.{side}")
    elif base.startswith("Finger"):
        realize(o); rigid(o, f"fingers.{side}")
    elif base == "Thumb":
        realize(o); rigid(o, f"thumb.{side}")
    elif base in ("Shoe", "Sole"):
        rigid(o, f"foot.{side}")
    elif base in ("Bead", "TasbihCord", "ImamBead", "BeadTassel"):
        rigid(o, "tasbih")                                     # own bone: hangs with gravity
    else:
        print("unbound:", n)

bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/character_rigged.blend")
print("bones:", len(rig.pose.bones), "| bound meshes:", sum(1 for o in bpy.data.objects if o.modifiers.get("Armature")))
