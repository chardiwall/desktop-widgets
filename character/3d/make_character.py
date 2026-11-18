# Faceless Omani-style 3D character, built procedurally in Blender (sent via bl.py).
# Parts are separate objects parented to a root empty so they can be rigged later.
# Units: the character is ~2.45 tall, facing -Y (towards the front camera).
import bpy, bmesh, math
import numpy as np
from mathutils import Vector

OUT = "/home/chardiwall/Documents/Programs/3D Avatar/character/3d"

# ---------------------------------------------------------------- reset scene
# (not read_factory_settings: that would also unload the MCP add-on and drop this connection)
scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
    for block in list(coll):
        if block.users == 0:
            coll.remove(block)


def mat(name, color, rough=0.5, sss=0.0, sheen=0.0, image=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if sss:
        b.inputs["Subsurface Weight"].default_value = sss
        b.inputs["Subsurface Radius"].default_value = (0.9, 0.45, 0.3)
        b.inputs["Subsurface Scale"].default_value = 0.08
    if sheen:
        b.inputs["Sheen Weight"].default_value = sheen
    if image is not None:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = image
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
    return m


def srgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def finish(obj, material, subsurf=2, parent=None):
    obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    if subsurf:
        obj.modifiers.new("Smooth", "SUBSURF").levels = subsurf
        obj.modifiers["Smooth"].render_levels = subsurf
    if parent:
        obj.parent = parent
    return obj


def lathe(name, profile, segments=48, depth=1.0, uv=True, ripple=None):
    """Spin a (radius, z) profile around Z. depth < 1 flattens front-to-back. UV: u=angle, v=height.
    ripple(angle, z) -> radius factor, used for fabric folds."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segments):
            a = 2 * math.pi * i / segments
            rr = r * (ripple(a, z) if ripple else 1.0)
            ring.append(bm.verts.new((rr * math.sin(a), -rr * depth * math.cos(a), z)))
        rings.append(ring)
    faces = []
    for k in range(len(rings) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            faces.append(bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i])))
    if uv:
        layer = bm.loops.layers.uv.new()
        zs = [z for _, z in profile]
        z0, z1 = min(zs), max(zs)
        for f in faces:
            for loop in f.loops:
                v = loop.vert
                a = (math.atan2(v.co.x, -v.co.y / depth) + math.pi) % (2 * math.pi)   # seam at the back
                loop[layer].uv = (a / (2 * math.pi), (v.co.z - z0) / (z1 - z0))
            us = [loop[layer].uv.x for loop in f.loops]
            if max(us) - min(us) > 0.5:            # fix the seam wrap
                for loop in f.loops:
                    if loop[layer].uv.x < 0.5:
                        loop[layer].uv.x += 1.0
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    return obj


def sphere(name, loc, scale, segs=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    return o


def tube(name, a, b, r1, r2, verts=24):
    """Tapered cylinder from point a to b."""
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=d.length,
                                    location=(a + b) / 2)
    o = bpy.context.active_object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return o


def limb(name, points, radii, material):
    """One smooth sleeve along a joint chain (skin modifier + subdivision): bends cleanly when rigged."""
    me = bpy.data.meshes.new(name)
    me.from_pydata(points, [(i, i + 1) for i in range(len(points) - 1)], [])
    obj = bpy.data.objects.new(name, me)
    scene.collection.objects.link(obj)
    skin = obj.modifiers.new("Skin", "SKIN")
    skin.use_smooth_shade = True
    for v, r in zip(obj.data.skin_vertices[0].data, radii):
        v.radius = (r, r * 0.95)
    obj.data.skin_vertices[0].data[0].use_root = True
    obj.modifiers.new("Smooth", "SUBSURF").levels = 2
    obj.modifiers["Smooth"].render_levels = 2
    obj.data.materials.append(material)
    obj.parent = root
    return obj


# ---------------------------------------------------------------- kumma embroidery texture
def _image(name, img):
    rgba = np.concatenate([img, np.ones((*img.shape[:2], 1))], axis=2)
    im = bpy.data.images.new(name, img.shape[1], img.shape[0])
    im.colorspace_settings.name = "Linear Rec.709"   # values are already linear
    im.pixels = rgba[::-1].ravel()
    im.pack()
    return im


CREAM, BLUE, BROWN, LINE = (np.array(srgb(h)) for h in ("#EAE2D4", "#3E62A0", "#5E412F", "#8C7B66"))


def kumma_texture(w=1536, h=384):
    """Dense Omani-style embroidery: four rows of motifs between fine rules, alternating blue/brown."""
    img = np.ones((h, w, 3)) * CREAM
    y, x = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    for yy in (0.03, 0.26, 0.5, 0.74, 0.97):
        img[np.abs(y - yy) < 0.010] = LINE
    img[np.abs(y - 0.5) < 0.022] = BROWN
    # motif count chosen so each motif cell is roughly square on the cap (circumference ~2.9x the band height)
    rows = ((0.145, BLUE, BROWN, 26), (0.38, BROWN, BLUE, 26), (0.62, BLUE, BROWN, 26), (0.855, BROWN, BLUE, 26))
    for yy, col_a, col_b, n in rows:
        cx = (x * n) % 1 - 0.5
        cy = (y - yy) / 0.17
        dia = np.abs(cx) * 1.15 + np.abs(cy) * 0.85
        img[dia < 0.52] = col_a                                         # bold filled diamond
        img[(dia < 0.36) & (dia > 0.24)] = CREAM                         # cream ring inside
        img[((np.abs(cx) < 0.05) | (np.abs(cy) < 0.06)) & (dia < 0.2)] = col_b   # inner cross
        img[dia < 0.07] = CREAM
        between = (np.abs(cx) > 0.44) & (np.abs(cy) < 0.28)            # small hourglass between motifs
        img[between & (np.abs(cy) * 1.4 > 0.5 - np.abs(cx) - 0.06)] = col_b
    return _image("kumma_pattern", img)


def crown_texture(w=1024, h=256):
    """Top of the kumma: u = angle, v = 0 at the rim -> 1 at the centre. Rings and an 8-petal rosette."""
    img = np.ones((h, w, 3)) * CREAM
    v, u = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    v = 1 - v                                                          # image row 0 is the centre
    for vv in (0.08, 0.30, 0.86):
        img[np.abs(v - vv) < 0.018] = LINE
    petal = np.abs(np.sin(np.pi * 8 * u))
    img[(v > 0.36) & (v < 0.80) & (petal > 0.25 + (v - 0.36) * 1.4)] = BLUE
    img[(v > 0.12) & (v < 0.26) & (np.abs(np.sin(np.pi * 24 * u)) > 0.6)] = BROWN
    img[v > 0.92] = BROWN
    return _image("kumma_crown", img)


# ---------------------------------------------------------------- materials
SKIN = mat("Skin", srgb("#F2C7A5"), rough=0.45, sss=0.25)
ROBE = mat("Dishdasha", srgb("#ECE8E1"), rough=0.7, sheen=0.25)   # warm white, so folds and shading read
HAIR = mat("Hair", srgb("#3A2A22"), rough=0.55)
SHOE = mat("Leather", srgb("#8A522E"), rough=0.35)
SOLE = mat("Sole", srgb("#3F2617"), rough=0.6)
BEAD = mat("Beads", srgb("#7A4524"), rough=0.25)
TASSEL = mat("Tassel", srgb("#E9E4DA"), rough=0.8, sheen=0.2)
KUMMA = mat("Kumma", (1, 1, 1), rough=0.85, sheen=0.05, image=kumma_texture())
KUMMA_TOP = mat("KummaTop", (1, 1, 1), rough=0.85, sheen=0.05, image=crown_texture())

root = bpy.data.objects.new("Character", None)
scene.collection.objects.link(root)

# ---------------------------------------------------------------- dishdasha (full length)
robe_profile = [(0.04, 1.40), (0.12, 1.39), (0.24, 1.36), (0.33, 1.30), (0.37, 1.18), (0.37, 1.00),
                (0.38, 0.80), (0.40, 0.55), (0.43, 0.30), (0.46, 0.14), (0.465, 0.11), (0.40, 0.105)]
def folds(a, z):
    depth = max(0.0, min(1.0, (1.0 - z) / 0.85))           # 0 at the chest, 1 at the hem
    wave = 0.65 * math.sin(5 * a + 0.4) + 0.35 * math.sin(9 * a + 1.3)
    return 1.0 + 0.06 * depth ** 1.2 * wave
finish(lathe("Dishdasha", robe_profile, segments=96, depth=0.78, uv=False, ripple=folds), ROBE, parent=root)
THREAD = mat("Thread", srgb("#D9D1C3"), rough=0.6)
rim = lathe("Neckline", [(0.118, 1.392), (0.128, 1.398), (0.124, 1.404)], depth=0.92, uv=False)
finish(rim, THREAD, subsurf=1, parent=root)
for side in (-1, 1):                                       # the slit's two embroidered edges
    finish(tube(f"Slit.{side}", (side * 0.008, -0.118, 1.392), (side * 0.008, -0.255, 1.27), 0.005, 0.005, 6),
           THREAD, subsurf=0, parent=root)
# furakha tassel hanging from the collar
# cord follows the robe's real front surface (the chest bulges forward to y ~ -0.29)
finish(tube("TasselCord1", (-0.05, -0.15, 1.385), (-0.06, -0.278, 1.28), 0.011, 0.011, 8), TASSEL, subsurf=0, parent=root)
cord = tube("TasselCord", (-0.06, -0.278, 1.28), (-0.065, -0.302, 1.10), 0.011, 0.011, 8)
finish(cord, TASSEL, subsurf=0, parent=root)
tas = tube("Tassel", (-0.065, -0.305, 1.11), (-0.066, -0.312, 0.98), 0.016, 0.042, 16)
finish(tas, TASSEL, subsurf=1, parent=root)

# ---------------------------------------------------------------- head (faceless), ears, hair
head = sphere("Head", (0, 0, 1.86), (0.47, 0.44, 0.45), 48)
for v in head.data.vertices:                               # local unit-sphere coords, front is -Y
    if v.co.z < 0.1:
        k = (0.1 - v.co.z) / 1.1
        v.co.x *= 1 + 0.10 * k                             # fuller cheeks
        v.co.y *= 1 + 0.06 * k
    if v.co.z > 0.5:
        v.co.x *= 1 - 0.04 * (v.co.z - 0.5)                # slightly softer crown
finish(head, SKIN, parent=root)
for sx in (-1, 1):
    ear = sphere(f"Ear.{'L' if sx > 0 else 'R'}", (sx * 0.455, 0.0, 1.84), (0.07, 0.04, 0.095), 16)
    finish(ear, SKIN, subsurf=1, parent=root)
neck = finish(tube("Neck", (0, 0, 1.36), (0, 0, 1.56), 0.105, 0.11), SKIN, subsurf=1, parent=root)
def hair_cap(segments=64, rows=10):
    """Hair as its own surface just outside the head, with a smooth curved hairline:
    hidden under the kumma at the front, just above the ears at the sides, down to the nape at the back."""
    cx, cy, cz, rx, ry, rz = 0, 0, 1.86, 0.482, 0.452, 0.462
    top = 2.02
    me = bpy.data.meshes.new("Hair")
    verts, faces = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments                       # 0 = front (-Y)
        bottom = 1.995 - 0.16 * (1 - math.cos(a)) / 2
        for k in range(rows):
            z = bottom + (top - bottom) * k / (rows - 1)
            h = math.sqrt(max(0.0, 1 - ((z - cz) / rz) ** 2))
            verts.append((cx + rx * h * math.sin(a), cy - ry * h * math.cos(a), z))
    for i in range(segments):
        j = (i + 1) % segments
        for k in range(rows - 1):
            faces.append((i * rows + k, j * rows + k, j * rows + k + 1, i * rows + k + 1))
    me.from_pydata(verts, [], faces)
    obj = bpy.data.objects.new("Hair", me)
    scene.collection.objects.link(obj)
    obj.modifiers.new("Thick", "SOLIDIFY").thickness = 0.01
    return obj


hair = hair_cap()
finish(hair, HAIR, subsurf=1, parent=root)

# ---------------------------------------------------------------- kumma
k_profile = [(0.465, 1.97), (0.474, 2.03), (0.471, 2.24), (0.458, 2.33), (0.435, 2.365)]
finish(lathe("Kumma", k_profile, depth=0.96), KUMMA, subsurf=1, parent=root)
top = lathe("KummaTop", [(0.435, 2.365), (0.33, 2.382), (0.16, 2.392), (0.002, 2.395)], depth=0.96)
finish(top, KUMMA_TOP, subsurf=1, parent=root)

# lift everything above the neck so a short neck shows above the collar
HEAD_LIFT = 0.06
for o in bpy.data.objects:
    if o.name.split(".")[0] in ("Head", "Ear", "Hair", "Kumma", "KummaTop"):
        o.location.z += HEAD_LIFT

# ---------------------------------------------------------------- arms (sleeves) + hands
for sx, name in ((1, "L"), (-1, "R")):
    sh, el, wr = (sx * 0.33, 0.0, 1.24), (sx * 0.415, 0.0, 0.99), (sx * 0.40, -0.13, 0.77)   # soft elbow bend
    limb(f"Sleeve.{name}", [sh, el, wr], [0.12, 0.112, 0.135], ROBE)
    wx, wy, wz = wr
    HS = 1.35                                             # chibi hands are big
    palm = sphere(f"Palm.{name}", (wx, wy - 0.005, wz - 0.075 * HS), (0.045 * HS, 0.065 * HS, 0.075 * HS), 24)
    finish(palm, SKIN, parent=root)
    for f, fy in enumerate((-0.042, -0.014, 0.014, 0.04)):  # front to back
        fy *= HS
        L = (0.055, 0.062, 0.058, 0.048)[f] * HS
        k0 = (wx, wy + fy, wz - 0.13 * HS)
        k1 = (wx - sx * 0.012 * HS, wy + fy * 1.05, wz - 0.13 * HS - L * 0.6)
        k2 = (wx - sx * 0.035 * HS, wy + fy * 1.05, wz - 0.13 * HS - L)    # tip curls towards the body
        limb(f"Finger{f}.{name}", [k0, k1, k2], [0.019 * HS, 0.017 * HS, 0.015 * HS], SKIN)
    limb(f"Thumb.{name}", [(wx - sx * 0.015 * HS, wy - 0.05 * HS, wz - 0.06 * HS), (wx - sx * 0.035 * HS, wy - 0.075 * HS, wz - 0.1 * HS),
                           (wx - sx * 0.045 * HS, wy - 0.08 * HS, wz - 0.13 * HS)], [0.021 * HS, 0.019 * HS, 0.016 * HS], SKIN)

# ---------------------------------------------------------------- shoes
for sx, name in ((1, "L"), (-1, "R")):
    shoe = sphere(f"Shoe.{name}", (sx * 0.15, -0.075, 0.072), (0.115, 0.2, 0.07), 32)
    finish(shoe, SHOE, parent=root)
    sole = sphere(f"Sole.{name}", (sx * 0.15, -0.075, 0.022), (0.122, 0.208, 0.024), 32)
    finish(sole, SOLE, parent=root)

# ---------------------------------------------------------------- tasbih in the right hand (-X)
hx, hy, hz = -0.37, -0.14, 0.53
for i in range(17):
    a = 2 * math.pi * i / 17
    p = (hx + 0.07 * math.sin(a), hy - 0.02 * math.cos(a), hz - 0.09 - 0.085 * math.cos(a))
    finish(sphere(f"Bead.{i:02d}", p, (0.018, 0.018, 0.018), 12), BEAD, subsurf=0, parent=root)
finish(tube("TasbihCord", (hx, hy - 0.02, hz - 0.26), (hx, hy - 0.02, hz - 0.31), 0.004, 0.004, 6), BEAD, subsurf=0, parent=root)
finish(sphere("ImamBead", (hx, hy - 0.02, hz - 0.32), (0.026, 0.026, 0.03), 12), BEAD, subsurf=1, parent=root)
finish(tube("BeadTassel", (hx, hy - 0.02, hz - 0.345), (hx, hy - 0.02, hz - 0.40), 0.004, 0.018, 12), TASSEL, subsurf=1, parent=root)

# ---------------------------------------------------------------- lights, camera, render
world = bpy.data.worlds.new("World"); scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.85, 0.86, 0.9, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35


def light(name, kind, loc, energy, size, color=(1, 1, 1)):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = energy, color
    if kind == "AREA":
        d.size = size
    o = bpy.data.objects.new(name, d)
    o.location = loc
    scene.collection.objects.link(o)
    o.rotation_euler = (Vector((0, 0, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o

light("Key", "AREA", (-2.4, -3.0, 3.4), 1300, 2.2, (1.0, 0.95, 0.88))
light("Fill", "AREA", (3.0, -2.4, 1.6), 220, 3.5, (0.88, 0.92, 1.0))
light("Rim", "AREA", (1.2, 3.2, 3.2), 900, 1.6, (0.95, 0.95, 1.0))

floor_me = bpy.data.meshes.new("Floor")
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40); bm.to_mesh(floor_me); bm.free()
floor = bpy.data.objects.new("ShadowCatcher", floor_me); scene.collection.objects.link(floor)
floor.is_shadow_catcher = True

cam_data = bpy.data.cameras.new("Cam"); cam_data.lens = 70
cam = bpy.data.objects.new("Camera", cam_data); scene.collection.objects.link(cam); scene.camera = cam

scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"; prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene.cycles.device = "GPU"
scene.cycles.samples = 96
scene.cycles.use_denoising = True
scene.render.film_transparent = True
scene.render.resolution_x, scene.render.resolution_y = 720, 1000
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -0.5          # keeps the white robe from blowing out, so folds read
try:
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = True
except Exception:
    pass

renders = []
for label, angle in (("front", 0), ("three_quarter", -35), ("side", -90)):
    root.rotation_euler = (0, 0, math.radians(angle))
    cam.location = (0, -7.4, 2.35)
    cam.rotation_euler = (math.radians(82), 0, 0)
    scene.render.filepath = f"{OUT}/render_{label}.png"
    bpy.ops.render.render(write_still=True)
    renders.append(scene.render.filepath)
root.rotation_euler = (0, 0, 0)
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/character.blend")
print("rendered:", ", ".join(r.rsplit("/", 1)[1] for r in renders))
