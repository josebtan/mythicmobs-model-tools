#!/usr/bin/env python3
"""
Convert a Blockbench-exported glTF (.gltf with embedded buffers/textures, as found in
"ModelEngine" model packs) into this repo's model format:

    <name>_cubes.json     skeleton + per-face UVs + animations, for the web viewer (index.html)
    <name>_texture.png    all of the glTF's textures merged into ONE atlas (the viewer / .bbmodel
                          pipeline here use a single texture per model)
    <name>.bbmodel        Blockbench project (generic "free" format, what ModelEngine consumes),
                          with the rest pose, per-face UVs, rotated cubes and animations

Usage:
    python3 gltf_to_model.py path/to/model.gltf succubus [--out-dir .] [--label "..."]

How the mapping works (Blockbench -> glTF -> back):
  * every glTF node without a mesh is a Blockbench group (= bone). Its translation is relative to
    the parent (in the parent's UNrotated frame), so the absolute pivot of a bone is just the sum of
    translations down the chain, x16 (Blockbench exports 1 px = 1/16 unit).
  * every mesh node is one cube. The mesh is an axis-aligned box in the node's local space and the
    node's own rotation is the cube's rotation about its own pivot. Cubes without rotation are
    folded into their parent bone; rotated ones keep their rotation (Blockbench element rotation in
    the .bbmodel; a tiny extra child bone in the viewer JSON, since viewer cubes can't rotate).
  * rotations are Euler 'ZYX' degrees, exactly what Blockbench stores (and what the viewer applies).
  * animation keyframes in glTF are the ABSOLUTE local rotation/translation/scale of each bone;
    this repo (and Blockbench) store them as DELTAS on top of the rest pose, so rest is subtracted.
"""
import argparse
import base64
import io
import json
import math
import os
import struct
import uuid
from collections import Counter

import numpy as np
from PIL import Image

PX = 16.0  # glTF unit -> Blockbench pixel
# A Blockbench/three.js box mesh has 4 vertices per face, in this order of faces:
FACES = ["east", "west", "up", "down", "south", "north"]  # +x, -x, +y, -y, +z, -z

# Where each of a box's 4 UV "slots" sits on each face (sign of the vertex relative to the box centre).
# Blockbench/three.js lay a face's UVs out as [TL, TR, BL, BR] in exactly this slot order.
SLOT_SIGNS = {
    "east": [(1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1)],
    "west": [(-1, 1, -1), (-1, 1, 1), (-1, -1, -1), (-1, -1, 1)],
    "up": [(-1, 1, -1), (1, 1, -1), (-1, 1, 1), (1, 1, 1)],
    "down": [(-1, -1, 1), (1, -1, 1), (-1, -1, -1), (1, -1, -1)],
    "south": [(-1, 1, 1), (1, 1, 1), (-1, -1, 1), (1, -1, 1)],
    "north": [(1, 1, -1), (-1, 1, -1), (1, -1, -1), (-1, -1, -1)],
}
FACE_NORMAL = {"east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0),
               "south": (0, 0, 1), "north": (0, 0, -1)}
LOOP_PREFIXES = ("idle", "walk", "run", "fly", "hoe_play")
HOLD_NAMES = ("death",)
LOOP_EXACT = ("jump",)


def uid():
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------- math

def quat_to_matrix(q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def euler_zyx_matrix(deg):
    """Same as build_bbmodel.euler_matrix: Rz @ Ry @ Rx, degrees."""
    rx, ry, rz = np.radians(deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Rz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def matrix_to_euler_zyx(R):
    """three.js Euler.setFromRotationMatrix for order 'ZYX', returned in degrees as [x, y, z]."""
    m31 = R[2][0]
    y = math.asin(-max(-1.0, min(1.0, m31)))
    if abs(m31) < 0.9999999:
        x = math.atan2(R[2][1], R[2][2])
        z = math.atan2(R[1][0], R[0][0])
    else:
        x = 0.0
        z = math.atan2(-R[0][1], R[1][1])
    return np.degrees([x, y, z])


def nearest_euler(e, ref):
    """Euler triples e and (x+180, 180-y, z+180) describe the same ZYX rotation, and each angle can
    be shifted by 360. Pick the equivalent triple closest to `ref` so keyframes stay continuous."""
    best, best_d = None, None
    for cand in (np.array(e, float), np.array([e[0] + 180, 180 - e[1], e[2] + 180], float)):
        c = cand.copy()
        for i in range(3):
            c[i] += 360.0 * round((ref[i] - c[i]) / 360.0)
        d = float(np.abs(c - ref).sum())
        if best is None or d < best_d:
            best, best_d = c, d
    return best


def slerp(q0, q1, t):
    q0, q1 = np.array(q0, float), np.array(q1, float)
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        r = q0 + t * (q1 - q0)
        return r / np.linalg.norm(r)
    th0 = math.acos(d)
    th = th0 * t
    s0 = math.cos(th) - d * math.sin(th) / math.sin(th0)
    s1 = math.sin(th) / math.sin(th0)
    return s0 * q0 + s1 * q1


def snap(v, tol=0.1):
    r = round(v)
    return float(r) if abs(v - r) < tol else round(float(v), 3)


def r3(v):
    return [round(float(x), 3) for x in v]


# ----------------------------------------------------------------------------- glTF

class Gltf:
    COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
    NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def __init__(self, path):
        with open(path) as f:
            self.g = json.load(f)
        self.bufs = []
        base = os.path.dirname(path)
        for b in self.g["buffers"]:
            uri = b["uri"]
            if uri.startswith("data:"):
                self.bufs.append(base64.b64decode(uri.split(",", 1)[1]))
            else:
                with open(os.path.join(base, uri), "rb") as f:
                    self.bufs.append(f.read())

    def acc(self, i):
        a = self.g["accessors"][i]
        bv = self.g["bufferViews"][a["bufferView"]]
        fmt, sz = self.COMP[a["componentType"]]
        n = self.NCOMP[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or sz * n
        buf = self.bufs[bv["buffer"]]
        out = np.zeros((a["count"], n))
        for k in range(a["count"]):
            out[k] = struct.unpack_from("<" + fmt * n, buf, off + k * stride)
        return out

    def image(self, i):
        im = self.g["images"][i]
        if "uri" in im and im["uri"].startswith("data:"):
            return Image.open(io.BytesIO(base64.b64decode(im["uri"].split(",", 1)[1]))).convert("RGBA")
        bv = self.g["bufferViews"][im["bufferView"]]
        data = self.bufs[bv["buffer"]][bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        return Image.open(io.BytesIO(data)).convert("RGBA")


# ----------------------------------------------------------------------------- model tree

class Cube:
    def __init__(self):
        self.frm = self.to = self.pivot = None
        self.rot = np.zeros(3)
        self.uv = {}        # face -> [x1,y1,x2,y2] in Blockbench convention, or None (face has no texture)
        self.color = "#8A7A68"


class Bone:
    def __init__(self, name, origin, rot):
        self.name = name
        self.origin = np.array(origin, float)
        self.rot = np.array(rot, float)
        self.cubes = []
        self.children = []
        self.node = None
        self.rest_T = None   # rest translation (px) / quaternion, for animation deltas
        self.rest_Q = None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gltf")
    ap.add_argument("name", help="output prefix, e.g. 'succubus' -> succubus_cubes.json ...")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--rename", action="append", default=[], metavar="OLD=NEW",
                    help="rename an animation (repeatable), e.g. --rename general=idle")
    ap.add_argument("--front", choices=["+z", "-z"], default="-z",
                    help="direction the output model faces. Blockbench/ModelEngine glTFs face -Z (kept by default); "
                         "+z turns the model 180 deg around Y (positions, rotations, faces/UVs and animation deltas), "
                         "which is the convention of this repo's own generator ('+z = frente').")
    args = ap.parse_args()
    renames = dict(r.split("=", 1) for r in args.rename)

    gl = Gltf(args.gltf)
    g = gl.g
    nodes = g["nodes"]

    # ---- 1. textures -> one atlas (stacked vertically) -------------------------------------
    mat_tex = []
    for m in g["materials"]:
        tex_i = m["pbrMetallicRoughness"]["baseColorTexture"]["index"]
        mat_tex.append(g["textures"][tex_i]["source"])
    imgs = {}
    for src in sorted(set(mat_tex)):
        imgs[src] = gl.image(src)
    atlas_w = max(im.width for im in imgs.values())
    y = 0
    placement = {}
    for src, im in imgs.items():
        placement[src] = (0, y)
        y += im.height
    atlas_h = y
    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    for src, im in imgs.items():
        atlas.paste(im, placement[src])
    atl = np.array(atlas)

    # a fully transparent texel, used by faces that have no texture at all
    ys, xs = np.where(atl[:, :, 3] == 0)
    if len(ys) == 0:
        raise SystemExit("atlas has no transparent pixel to park untextured faces on")
    blank_px = (int(xs[0]), int(ys[0]))

    def mat_geom(mat_index):
        src = mat_tex[mat_index]
        return imgs[src].width, imgs[src].height, placement[src][0], placement[src][1]

    # ---- 2. node tree -> bones + cubes -------------------------------------------------------
    animated_nodes = set()
    for a in g.get("animations", []):
        for ch in a["channels"]:
            animated_nodes.add(ch["target"]["node"])

    child_of = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            child_of[c] = i
    scene_roots = g["scenes"][g.get("scene", 0)]["nodes"]

    used_names = Counter()

    def unique(name):
        base = name or "bone"
        used_names[base] += 1
        return base if used_names[base] == 1 else f"{base}_{used_names[base]}"

    bone_of_node = {}
    top_bones = []
    stats = Counter()
    faces_seen = []  # (cube, face, rect-by-hypothesis) for the orientation check

    def node_T(n):
        return np.array(n.get("translation", [0, 0, 0]), float) * PX

    def node_Q(n):
        return list(n.get("rotation", [0, 0, 0, 1]))

    def make_cube(node_i, parent_abs):
        n = nodes[node_i]
        prim = g["meshes"][n["mesh"]]["primitives"][0]
        P = gl.acc(prim["attributes"]["POSITION"]) * PX
        U = gl.acc(prim["attributes"]["TEXCOORD_0"])
        N = gl.acc(prim["attributes"]["NORMAL"]) if "NORMAL" in prim["attributes"] else None
        if "indices" in prim:  # indexed mesh: expand to one row per index
            idx = gl.acc(prim["indices"])[:, 0].astype(int)
            P, U = P[idx], U[idx]
            N = N[idx] if N is not None else None
        if N is None:
            raise SystemExit(f"node {node_i}: mesh has no NORMAL attribute")
        pivot = parent_abs + node_T(n)
        cube = Cube()
        cube.pivot = pivot
        cube.rot = matrix_to_euler_zyx(quat_to_matrix(node_Q(n)))
        cube.frm = pivot + P.min(axis=0)
        cube.to = pivot + P.max(axis=0)
        center = (P.min(axis=0) + P.max(axis=0)) / 2
        size = P.max(axis=0) - P.min(axis=0)
        w_, h_, xo, yo = mat_geom(prim.get("material", 0))
        cube._raw = []
        for face in FACES:
            fn = np.array(FACE_NORMAL[face])
            rows = np.where(N @ fn > 0.9)[0]
            axis = int(np.argmax(np.abs(fn)))
            in_plane = [a for a in range(3) if a != axis]
            slots = [None] * 4
            if len(rows) and all(size[a] > 1e-4 for a in in_plane):
                for r in rows:
                    sg = np.sign(np.round((P[r] - center) / max(size.max(), 1e-6) * 1000))
                    for k, ref in enumerate(SLOT_SIGNS[face]):
                        if all(sg[a] == ref[a] for a in in_plane):
                            slots[k] = U[r]
            if any(sl is None for sl in slots):
                cube.uv[face] = None   # no vertices / zero-area face: nothing to texture
                stats["untextured_faces"] += 1
                continue
            q = np.array(slots)
            if np.ptp(q[:, 0]) < 1e-6 or np.ptp(q[:, 1]) < 1e-6:
                cube.uv[face] = None   # all four corners share a UV coordinate: Blockbench "no texture"
                stats["untextured_faces"] += 1
                continue
            cube._raw.append((face, q.copy(), w_, h_, xo, yo))
        cube.size = size
        return cube

    def corners_from_raw(raw, flip_v):
        """The 4 slot UVs of a face as snapped pixel points in the merged atlas (top-down y)."""
        face, q, w_, h_, xo, yo = raw
        pts = []
        for u, v in q:
            if flip_v:
                v = 1 - v
            pts.append((snap(u * w_ + xo), snap(v * h_ + yo)))
        return pts

    def face_from_corners(pts):
        """Slots are [TL, TR, BL, BR] of the face rect (Blockbench), optionally rotated in 90 deg steps.
        rot 0:  s0=(x1,y1) s1=(x2,y1) s2=(x1,y2)       rot 90: s0=(x1,y2) s1=(x1,y1) s2=(x2,y2)
        (180/270 are the same as 0/90 with the rect's corners swapped, so only 0 and 90 are needed.)"""
        s0, s1, s2, s3 = pts
        if abs(s0[1] - s1[1]) < 0.25 and abs(s0[0] - s2[0]) < 0.25:
            return {"rot": 0, "rect": [s0[0], s0[1], s1[0], s2[1]], "pts": pts}
        if abs(s0[0] - s1[0]) < 0.25 and abs(s0[1] - s2[1]) < 0.25:
            return {"rot": 90, "rect": [s0[0], s1[1], s2[0], s0[1]], "pts": pts}
        stats["unsupported_uv_faces"] += 1
        return {"rot": 0, "rect": [s0[0], s0[1], s1[0], s2[1]], "pts": pts}

    def visit_group(node_i, parent_abs, parent_bone):
        n = nodes[node_i]
        abs_o = parent_abs + node_T(n)
        name = unique(n.get("name"))
        rot = matrix_to_euler_zyx(quat_to_matrix(node_Q(n)))
        bone = Bone(name, abs_o, rot)
        bone.node = node_i
        bone.rest_T = node_T(n)
        bone.rest_Q = node_Q(n)
        bone_of_node[node_i] = bone
        (parent_bone.children if parent_bone else top_bones).append(bone)
        for c in n.get("children", []):
            if "mesh" in nodes[c]:
                if c in animated_nodes:
                    raise SystemExit(f"animated mesh node {c} not supported")
                bone.cubes.append(make_cube(c, abs_o))
            else:
                visit_group(c, abs_o, bone)

    for r in scene_roots:
        n = nodes[r]
        identity = (not n.get("name") and "translation" not in n and "rotation" not in n and "scale" not in n)
        if "mesh" in n:
            raise SystemExit("mesh at scene root not supported")
        if identity:  # nameless wrapper node: its children are the real top-level bones
            for c in n.get("children", []):
                visit_group(c, np.zeros(3), None)
        else:
            visit_group(r, np.zeros(3), None)

    # ---- 3. UV orientation (glTF V is top-down, but verify against the texture content) -------
    def opaque_fraction(flip_v):
        tot, op = 0, 0
        def walk(b):
            nonlocal tot, op
            for c in b.cubes:
                for raw in c._raw:
                    pts = corners_from_raw(raw, flip_v)
                    xs_ = [p[0] for p in pts]
                    ys_ = [p[1] for p in pts]
                    xa, xb = int(max(0, min(xs_))), int(min(atlas_w, math.ceil(max(xs_))))
                    ya, yb = int(max(0, min(ys_))), int(min(atlas_h, math.ceil(max(ys_))))
                    if xb > xa and yb > ya:
                        reg = atl[ya:yb, xa:xb, 3]
                        tot += reg.size
                        op += int((reg > 12).sum())
            for ch in b.children:
                walk(ch)
        for b in top_bones:
            walk(b)
        return op / max(tot, 1)

    frac_a, frac_b = opaque_fraction(False), opaque_fraction(True)
    flip_v = frac_b > frac_a
    print(f"UV orientation check: top-down V -> {frac_a:.2f} opaque, flipped V -> {frac_b:.2f} opaque "
          f"=> using {'flipped' if flip_v else 'top-down'} V")

    def walk_fix(b):
        for c in b.cubes:
            for raw in c._raw:
                c.uv[raw[0]] = face_from_corners(corners_from_raw(raw, flip_v))
            for face in FACES:
                c.uv.setdefault(face, None)
        for ch in b.children:
            walk_fix(ch)
    for b in top_bones:
        walk_fix(b)

    # Sanity check on the slot/face mapping: a face's texture rect should be about as big as the face.
    expect_axes = {"east": (2, 1), "west": (2, 1), "up": (0, 2), "down": (0, 2), "south": (0, 1), "north": (0, 1)}
    mismatches = 0
    def walk_diag(b):
        nonlocal mismatches
        for c in b.cubes:
            for face, fc in c.uv.items():
                if not fc or fc["rot"]:
                    continue
                aw, ah = expect_axes[face]
                r = fc["rect"]
                if abs(abs(r[2] - r[0]) - c.size[aw]) > 0.6 or abs(abs(r[3] - r[1]) - c.size[ah]) > 0.6:
                    mismatches += 1
        for ch in b.children:
            walk_diag(ch)
    for b in top_bones:
        walk_diag(b)
    stats["face_rect_size_mismatch"] = mismatches

    # average colour per cube from its textured faces (used by the viewer's "Textura: off" mode)
    def cube_color(c):
        px = []
        for face, fc in c.uv.items():
            if not fc:
                continue
            r = fc["rect"]
            xa, xb = int(max(0, min(r[0], r[2]))), int(min(atlas_w, math.ceil(max(r[0], r[2]))))
            ya, yb = int(max(0, min(r[1], r[3]))), int(min(atlas_h, math.ceil(max(r[1], r[3]))))
            if xb > xa and yb > ya:
                reg = atl[ya:yb, xa:xb].reshape(-1, 4)
                reg = reg[reg[:, 3] > 12]
                if len(reg):
                    px.append(reg[:, :3])
        if not px:
            return "#8A7A68"
        m = np.concatenate(px).mean(axis=0)
        return "#%02X%02X%02X" % tuple(int(round(v)) for v in m)

    def walk_color(b):
        for c in b.cubes:
            c.color = cube_color(c)
        for ch in b.children:
            walk_color(ch)
    for b in top_bones:
        walk_color(b)

    # ---- 4. animations -------------------------------------------------------------------------
    animations = {}
    for a in g.get("animations", []):
        per_node = {}
        length = 0.0
        for ch in a["channels"]:
            s = a["samplers"][ch["sampler"]]
            t = gl.acc(s["input"])[:, 0]
            v = gl.acc(s["output"])
            length = max(length, float(t.max()))
            per_node.setdefault(ch["target"]["node"], {})[ch["target"]["path"]] = (t, v)

        tracks = {}
        for node_i, chans in per_node.items():
            bone = bone_of_node.get(node_i)
            if bone is None:
                continue
            rest_E = bone.rot
            frames = {}  # channel -> (times, deltas)
            if "rotation" in chans:
                t, q = chans["rotation"]
                prev = rest_E
                E = []
                for qi in q:
                    e = nearest_euler(matrix_to_euler_zyx(quat_to_matrix(qi)), prev)
                    E.append(e)
                    prev = e
                frames["rotation"] = (t, np.array(E) - rest_E, 0.05)
            if "translation" in chans:
                t, v = chans["translation"]
                frames["position"] = (t, v * PX - bone.rest_T, 0.01)
            if "scale" in chans:
                t, v = chans["scale"]
                frames["scale"] = (t, v, 0.002)

            kf = {}  # time -> dict
            for chan, (t, vals, tol) in frames.items():
                keep = simplify(t, vals, tol)
                for i in keep:
                    key = round(float(t[i]), 4)
                    kf.setdefault(key, {})[chan] = [round(float(x), 4 if chan == "scale" else 3) for x in vals[i]]
            tracks[bone.name] = [{"time": k, **kf[k]} for k in sorted(kf)]
        name = a["name"].split(".")[-1] or a["name"]
        name = renames.get(name, renames.get(a["name"], name))
        if all(abs(v) < 1e-3 for kfs in tracks.values() for kf in kfs
               for ch, vals in kf.items() if ch in ("rotation", "position") for v in vals) and \
           all(abs(v - 1) < 1e-3 for kfs in tracks.values() for kf in kfs for v in kf.get("scale", [1])):
            print(f"  (skipping animation '{name}': every keyframe is the rest pose, it does nothing)")
            continue
        k = 2
        base_name = name
        while name in animations:
            name, k = f"{base_name}_{k}", k + 1
        if name in HOLD_NAMES:
            mode = "hold"
        elif name.startswith(LOOP_PREFIXES) or name in LOOP_EXACT:
            mode = "loop"
        else:
            mode = "once"
        animations[name] = {"loop": mode == "loop", "loop_mode": mode, "length": round(length, 4), "tracks": tracks}

    # ---- 4b. orientation -------------------------------------------------------------------------
    if args.front == "+z":   # glTF from Blockbench faces -Z
        turn_model_around(top_bones, animations, face_from_corners)

    # ---- 5. output: viewer JSON ----------------------------------------------------------------
    prefix = args.name
    texture_file = f"{prefix}_texture.png"
    blank_rect = [blank_px[0] + 0.5, blank_px[1] + 0.5, blank_px[0] + 0.5, blank_px[1] + 0.5]

    def viewer_rects(c):
        """Viewer applyBoxUV puts the rect's BOTTOM row on a face's top-left vertex, i.e. it is the
        Blockbench rect with y swapped. Rotated faces (not expressible as a rect) are written as 8
        numbers = the 4 slot UVs in atlas pixels, which the viewer applies one-to-one. Faces without
        a texture park on a transparent texel."""
        out = {}
        for face in FACES:
            fc = c.uv[face]
            if not fc:
                out[face] = list(blank_rect)
            elif fc["rot"] == 0:
                r = fc["rect"]
                out[face] = [r[0], r[3], r[2], r[1]]
            else:
                out[face] = [v for p in fc["pts"] for v in p]
        return out

    flat = []

    def to_viewer(bone, parent_origin_rest, parent_world_origin, parent_world_R):
        world_R = parent_world_R @ euler_zyx_matrix(bone.rot)
        world_origin = parent_world_origin + parent_world_R @ (bone.origin - parent_origin_rest)
        node = {"name": bone.name, "origin": r3(bone.origin), "rotation": r3(bone.rot), "cubes": [], "children": []}
        extra_children = []
        for ci, c in enumerate(bone.cubes):
            uvf = viewer_rects(c)
            center = (c.frm + c.to) / 2
            if np.abs(c.rot).max() < 1e-6:
                holder = node
                holder_origin, holder_R, holder_wo = bone.origin, world_R, world_origin
                cube_R, pivot_rest = world_R, bone.origin
                pivot_world = world_origin
            else:
                # rotated cube: tiny child bone pivoting where Blockbench pivots the element
                sub = {"name": f"{bone.name}__cube{ci}", "origin": r3(c.pivot), "rotation": r3(c.rot),
                       "cubes": [], "children": []}
                extra_children.append(sub)
                holder = sub
                pivot_world = world_origin + world_R @ (c.pivot - bone.origin)
                cube_R = world_R @ euler_zyx_matrix(c.rot)
                pivot_rest = c.pivot
            wc = pivot_world + cube_R @ (center - pivot_rest)
            holder["cubes"].append({"from": r3(c.frm), "to": r3(c.to), "color": c.color, "uv_faces": uvf})
            flat.append({
                "name": bone.name, "from": r3(c.frm), "to": r3(c.to), "origin": r3(pivot_rest),
                "uv_faces": uvf, "world_center": r3(wc), "world_R": cube_R.tolist(),
            })
        for ch in bone.children:
            node["children"].append(to_viewer(ch, bone.origin, world_origin, world_R))
        node["children"].extend(extra_children)
        return node

    skeleton = [to_viewer(b, np.zeros(3), np.zeros(3), np.eye(3)) for b in top_bones]
    data = {
        "texture": texture_file,
        "texture_size": [atlas_w, atlas_h],
        # Blockbench / ModelEngine models face north (-Z); repo-generated ones face +Z. The viewer's
        # Frente/Atrás/Izq./Der. camera presets read this.
        "front": args.front,
        "cubes": flat,
        "skeleton": skeleton,
        "animations": animations,
    }
    os.makedirs(args.out_dir, exist_ok=True)
    out = lambda f: os.path.join(args.out_dir, f)
    with open(out(f"{prefix}_cubes.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    buf = io.BytesIO()
    atlas.save(buf, format="PNG")
    with open(out(texture_file), "wb") as f:
        f.write(buf.getvalue())

    # ---- 6. output: .bbmodel --------------------------------------------------------------------
    elements, bone_uuid = [], {}
    tex_uuid = uid()

    def to_group(bone):
        cube_ids = []
        for ci, c in enumerate(bone.cubes):
            el_uuid = uid()
            faces = {}
            for face in FACES:
                fc = c.uv[face]
                if not fc:
                    faces[face] = {"uv": [0, 0, 0, 0], "texture": None}
                else:
                    faces[face] = {"uv": fc["rect"], "texture": 0}
                    if fc["rot"]:
                        faces[face]["rotation"] = fc["rot"]
            el = {
                "name": f"{bone.name}_{ci}" if len(bone.cubes) > 1 else bone.name,
                "box_uv": False,
                "from": r3(c.frm), "to": r3(c.to),
                "autouv": 0, "color": 0,
                "origin": r3(c.pivot if np.abs(c.rot).max() >= 1e-6 else bone.origin),
                "uv_offset": [0, 0],
                "faces": faces, "type": "cube", "uuid": el_uuid,
            }
            if np.abs(c.rot).max() >= 1e-6:
                el["rotation"] = r3(c.rot)
            elements.append(el)
            cube_ids.append(el_uuid)
        grp = {
            "name": bone.name, "origin": r3(bone.origin), "rotation": r3(bone.rot), "color": 0,
            "uuid": uid(), "export": True, "isOpen": True, "locked": False, "visibility": True,
            "children": cube_ids + [to_group(ch) for ch in bone.children],
        }
        bone_uuid[bone.name] = grp["uuid"]
        return grp

    outliner = [to_group(b) for b in top_bones]

    bb_anims = []
    for aname, anim in animations.items():
        animators = {}
        for bname, kfs in anim["tracks"].items():
            keyframes = []
            for kf in kfs:
                for chan in ("rotation", "position", "scale"):
                    if chan in kf:
                        x, y_, z = kf[chan]
                        keyframes.append({
                            "channel": chan,
                            "data_points": [{"x": str(x), "y": str(y_), "z": str(z)}],
                            "uuid": uid(), "time": kf["time"], "color": -1, "interpolation": "linear",
                        })
            animators[bone_uuid[bname]] = {"name": bname, "type": "bone", "keyframes": keyframes}
        bb_anims.append({
            "uuid": uid(), "name": aname, "loop": anim["loop_mode"], "override": False,
            "length": anim["length"], "snapping": 24, "selected": False, "anim_time_update": "",
            "blend_weight": "", "start_delay": "", "loop_delay": "", "animators": animators,
        })

    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    bbmodel = {
        "meta": {"format_version": "4.5", "model_format": "free", "box_uv": False},
        "name": prefix, "model_identifier": "", "visible_box": [1, 1, 0], "variable_placeholders": "",
        "resolution": {"width": atlas_w, "height": atlas_h},
        "elements": elements, "outliner": outliner, "animations": bb_anims,
        "textures": [{
            "path": "", "name": texture_file, "folder": "", "namespace": "", "id": "0",
            "width": atlas_w, "height": atlas_h, "uv_width": atlas_w, "uv_height": atlas_h,
            "particle": False, "layers_enabled": False, "use_as_default": True, "render_mode": "default",
            "frame_time": 1, "frame_order_type": "loop", "frame_order": "", "frame_interpolate": False,
            "visible": True, "internal": True, "saved": True, "uuid": tex_uuid, "relative_path": "",
            "source": f"data:image/png;base64,{b64}",
        }],
    }
    with open(out(f"{prefix}.bbmodel"), "w") as f:
        json.dump(bbmodel, f, separators=(",", ":"))

    n_bones = sum(1 for _ in iter_bones(top_bones))
    print(f"{prefix}: {n_bones} bones, {len(elements)} cubes ({sum(1 for c in flat if True)} flat), "
          f"{len(animations)} animations, atlas {atlas_w}x{atlas_h}")
    print("stats:", dict(stats))
    for an, a in animations.items():
        kfs = sum(len(v) for v in a["tracks"].values())
        print(f"  anim {an:12s} {a['loop_mode']:5s} {a['length']:5.2f}s  {len(a['tracks']):2d} bones  {kfs:4d} keyframes")


def turn_model_around(top_bones, animations, face_from_corners):
    """Rotate the whole model 180 deg about Y (x,z -> -x,-z), in place.

    Conjugating every local transform by that rotation gives: bone/cube positions (-x, y, -z), ZYX Euler
    rotations (-rx, ry, -rz), and the same for animation deltas (scale is untouched). A box's faces trade
    places (east<->west, south<->north) keeping their UVs; top/bottom stay put but are turned 180 deg in
    their own plane, which reverses their 4 corner UVs."""
    F = np.array([-1.0, 1.0, -1.0])
    swap = {"east": "west", "west": "east", "south": "north", "north": "south", "up": "up", "down": "down"}

    def bone(b):
        b.origin = b.origin * F
        b.rot = b.rot * F
        for c in b.cubes:
            lo, hi = c.frm * F, c.to * F
            c.frm, c.to = np.minimum(lo, hi), np.maximum(lo, hi)
            c.pivot = c.pivot * F
            c.rot = c.rot * F
            turned = {}
            for face, fc in c.uv.items():
                if fc and face in ("up", "down"):
                    fc = face_from_corners(list(reversed(fc["pts"])))
                turned[swap[face]] = fc
            c.uv = turned
        for ch in b.children:
            bone(ch)

    for b in top_bones:
        bone(b)

    def neg(v):
        return [(0.0 - v[0]) + 0.0, v[1], (0.0 - v[2]) + 0.0]

    for anim in animations.values():
        for kfs in anim["tracks"].values():
            for kf in kfs:
                for chan in ("rotation", "position"):
                    if chan in kf:
                        kf[chan] = neg(kf[chan])


def iter_bones(bones):
    for b in bones:
        yield b
        yield from iter_bones(b.children)


def simplify(times, vals, tol):
    """Drop keyframes that linear interpolation between their neighbours reproduces within `tol`
    (Ramer-Douglas-Peucker over the time series). Returns the kept indices."""
    n = len(times)
    if n <= 2:
        return list(range(n))
    keep = {0, n - 1}
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        worst, wi = 0.0, None
        ta, tb = times[a], times[b]
        for i in range(a + 1, b):
            f = 0.0 if tb == ta else (times[i] - ta) / (tb - ta)
            interp = vals[a] + (vals[b] - vals[a]) * f
            err = float(np.abs(interp - vals[i]).max())
            if err > worst:
                worst, wi = err, i
        if worst > tol and wi is not None:
            keep.add(wi)
            stack.append((a, wi))
            stack.append((wi, b))
    return sorted(keep)


if __name__ == "__main__":
    main()
