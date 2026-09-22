"""
Generic .bbmodel builder with:
  - articulated bone hierarchies (nested parts -> nested Blockbench outliner groups)
  - a real generated texture atlas (box-UV packed, shaded, painted with Pillow)

Each "part" is a dict:
{
    "name": str,
    "origin": [x, y, z],           # pivot point for this bone (for rotation/animation)
    "cubes": [ {"from":[..], "to":[..], "color": "#RRGGBB"}, ... ],
    "children": [ part, part, ... ]               # nested bones (e.g. forearm under upper arm)
}

`color` on a cube is optional; if omitted it falls back to PART_COLORS[part name],
then to DEFAULT_COLOR.
"""
import base64
import json
import uuid
from io import BytesIO

import numpy as np

from texture_gen import paint_atlas, paint_face_detail, hex_to_rgb

def uid():
    return str(uuid.uuid4())


def euler_matrix(deg):
    """Rotation matrix for [rx,ry,rz] in degrees (Blockbench-style, applied Z*Y*X)."""
    rx, ry, rz = np.radians(deg)
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


DEFAULT_COLOR = "#8A7A68"
PART_COLORS = {
    "torso": "#8A7A68",
    "head": "#8A7A68",
    "left_shoulder": "#5B5B5E", "right_shoulder": "#5B5B5E",
    "left_upper_arm": "#8A7A68", "right_upper_arm": "#8A7A68",
    "left_forearm": "#83725F", "right_forearm": "#83725F",
    "left_hand": "#4A3C30", "right_hand": "#4A3C30",
    "left_leg": "#83725F", "right_leg": "#83725F",
    "body": "#8A7A68",
    "left_arm": "#8A7A68", "right_arm": "#8A7A68",
}


def build_bbmodel_animations(animations, bone_uuid_by_name):
    """
    Convert our authoring format:
        {"idle": {"loop": True, "length": 2.0,
                   "keyframes": {"torso": [(0, {"position":[0,0,0]}), (1.0, {"position":[0,0.35,0]})]}}}
    into Blockbench's `.bbmodel` "animations" array format (per-bone animators keyed by bone uuid,
    each channel's keyframes as separate entries). Rotation/position values are DELTAS on top of the
    bone's own rest-pose `rotation`/`origin` -- exactly how Blockbench/ModelEngine interpret them.
    """
    result = []
    for anim_name, anim in animations.items():
        animators = {}
        for bone_name, kfs in anim["keyframes"].items():
            b_uuid = bone_uuid_by_name.get(bone_name)
            if not b_uuid:
                continue
            keyframes = []
            for time, data in kfs:
                for channel in ("rotation", "position"):
                    if channel in data:
                        x, y, z = data[channel]
                        keyframes.append({
                            "channel": channel,
                            "data_points": [{"x": str(x), "y": str(y), "z": str(z)}],
                            "uuid": uid(),
                            "time": time,
                            "color": -1,
                            "interpolation": "linear",
                        })
            animators[b_uuid] = {"name": bone_name, "type": "bone", "keyframes": keyframes}
        result.append({
            "uuid": uid(),
            "name": anim_name,
            "loop": "loop" if anim.get("loop") else "once",
            "override": False,
            "length": anim["length"],
            "snapping": 24,
            "selected": False,
            "anim_time_update": "",
            "blend_weight": "",
            "start_delay": "",
            "loop_delay": "",
            "animators": animators,
        })
    return result


def export_animations_for_viewer(animations):
    """Simplified JSON for index.html: {name: {loop, length, tracks: {bone_name: [{time,rotation?,position?}]}}}"""
    out = {}
    for anim_name, anim in animations.items():
        tracks = {}
        for bone_name, kfs in anim["keyframes"].items():
            tracks[bone_name] = [
                {"time": t, **{k: v for k, v in data.items() if k in ("rotation", "position")}}
                for t, data in kfs
            ]
        out[anim_name] = {"loop": bool(anim.get("loop")), "length": anim["length"], "tracks": tracks}
    return out


def build_bbmodel(model_name, root_parts, out_file, animations=None):
    # --- Pass 1: walk the tree, collect leaf cubes (geometry + color + owning part)      ---
    # Also compute each cube's WORLD center + WORLD rotation matrix by composing bone-level
    # `rotation` (degrees, pivoting around that bone's own `origin`) down the hierarchy.
    # This lets a static pose (e.g. a forward hunch on the torso) be authored once, at the
    # bone level -- the same mechanism an animation would use -- and have every cube under
    # it (including nested children like the head/arms) follow it automatically.
    leaf_cubes = []  # each: {part_name, origin, from, to, w,h,d, color, world_center, world_R}

    def walk(part, parent_origin_rest=np.zeros(3), parent_world_origin=np.zeros(3), parent_world_R=np.eye(3)):
        own_origin_rest = np.array(part["origin"], dtype=float)
        own_local_R = euler_matrix(part.get("rotation", [0, 0, 0]))
        world_R = parent_world_R @ own_local_R
        world_origin = parent_world_origin + parent_world_R @ (own_origin_rest - parent_origin_rest)

        for cube in part.get("cubes", []):
            fx, fy, fz = cube["from"]
            tx, ty, tz = cube["to"]
            color = cube.get("color") or PART_COLORS.get(part["name"], DEFAULT_COLOR)
            local_center = np.array([(fx + tx) / 2, (fy + ty) / 2, (fz + tz) / 2])
            world_center = world_origin + world_R @ (local_center - own_origin_rest)
            leaf_cubes.append({
                "part_name": part["name"],
                "id": cube.get("id"),
                "origin": part["origin"],
                "from": cube["from"],
                "to": cube["to"],
                "w": abs(tx - fx), "h": abs(ty - fy), "d": abs(tz - fz),
                "color": color,
                "world_center": world_center.tolist(),
                "world_R": world_R.tolist(),
            })
        for child in part.get("children", []):
            walk(child, own_origin_rest, world_origin, world_R)

    for p in root_parts:
        walk(p)

    # --- Pass 2: pack + paint the texture atlas ---
    # Kept at native resolution (no supersampling) -- the earlier scale bump made the file
    # heavier for no real benefit; the eyes just needed correct placement, not more pixels.
    atlas_img, uv_by_index = paint_atlas(leaf_cubes, atlas_width=128)
    atlas_w, atlas_h = atlas_img.size

    # Paint eyes on the jaw's front (south) face, if this model has one tagged "id": "jaw".
    # rel_box is (x1,y1,x2,y2) as a fraction of the face rect, y growing downward in image
    # space -- so a LOW y (near 0) is near the jaw's bottom/chin, and a HIGH y (near 1) is
    # near the jaw's top/brow. The eyes must sit in the upper part of the jaw, clear of the
    # muzzle cube (which already occupies roughly the bottom 60% of the jaw's height) --
    # putting them low, as before, placed them right where the mouth is.
    jaw_idx = next((i for i, c in enumerate(leaf_cubes) if c.get("id") == "jaw"), None)
    if jaw_idx is not None:
        rect = uv_by_index[jaw_idx]["south"]
        skin_color = hex_to_rgb(leaf_cubes[jaw_idx]["color"])
        # Exact pixel layout for a 6x3px face: two 2x2 black eyes with a 2px-wide gap of
        # skin color between them, filling the full width (2+2+2=6), sitting in the upper
        # two rows (near the brow, clear of the muzzle in the bottom row).
        paint_face_detail(atlas_img, rect, (0.0, 1 / 3, 1 / 3, 1.0), (0, 0, 0))
        paint_face_detail(atlas_img, rect, (1 / 3, 1 / 3, 2 / 3, 1.0), skin_color)
        paint_face_detail(atlas_img, rect, (2 / 3, 1 / 3, 1.0, 1.0), (0, 0, 0))

    buf = BytesIO()
    atlas_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    b64 = base64.b64encode(png_bytes).decode("ascii")

    texture_file = out_file.replace(".bbmodel", "_texture.png")
    with open(texture_file, "wb") as f:
        f.write(png_bytes)

    # --- Pass 3: build bbmodel elements (consuming leaf_cubes / uv_by_index in order) ---
    elements = []
    flat_cubes = []  # for the matplotlib renderer + web viewer
    cube_cursor = [0]  # index into leaf_cubes / uv_by_index, shared via closure
    bone_uuid_by_name = {}  # part name -> outliner group uuid, needed to wire up animations

    def make_faces(uv_rects):
        return {face: {"uv": rect, "texture": 0} for face, rect in uv_rects.items()}

    def build_group(part):
        cube_uuids = []
        skeleton_cubes = []
        n = len(part.get("cubes", []))
        for i, cube in enumerate(part.get("cubes", [])):
            idx = cube_cursor[0]
            cube_cursor[0] += 1
            leaf = leaf_cubes[idx]
            uv_rects = uv_by_index[idx]

            cube_uuid = uid()
            elements.append({
                "name": f'{part["name"]}_{i}' if n > 1 else part["name"],
                "from": cube["from"],
                "to": cube["to"],
                "autouv": 0,
                "color": 0,
                "origin": part["origin"],
                "uv_offset": [0, 0],
                "faces": make_faces(uv_rects),
                "type": "cube",
                "uuid": cube_uuid,
            })
            cube_uuids.append(cube_uuid)
            flat_cubes.append({
                "name": part["name"],
                "from": cube["from"],
                "to": cube["to"],
                "origin": part["origin"],
                "uv_faces": uv_rects,
                "world_center": leaf["world_center"],
                "world_R": leaf["world_R"],
            })
            skeleton_cubes.append({
                "from": cube["from"],
                "to": cube["to"],
                "color": leaf["color"],
                "uv_faces": uv_rects,
            })

        child_groups = []
        child_skeletons = []
        for child in part.get("children", []):
            g, s = build_group(child)
            child_groups.append(g)
            child_skeletons.append(s)

        outliner_group = {
            "name": part["name"],
            "origin": part["origin"],
            "rotation": part.get("rotation", [0, 0, 0]),
            "color": 0,
            "uuid": uid(),
            "export": True,
            "isOpen": True,
            "locked": False,
            "visibility": True,
            "children": cube_uuids + child_groups,
        }
        bone_uuid_by_name[part["name"]] = outliner_group["uuid"]
        skeleton_node = {
            "name": part["name"],
            "origin": part["origin"],
            "rotation": part.get("rotation", [0, 0, 0]),
            "cubes": skeleton_cubes,
            "children": child_skeletons,
        }
        return outliner_group, skeleton_node

    outliner = []
    skeleton = []
    for p in root_parts:
        g, s = build_group(p)
        outliner.append(g)
        skeleton.append(s)

    bbmodel_animations = build_bbmodel_animations(animations, bone_uuid_by_name) if animations else []

    texture_uuid = uid()
    bbmodel = {
        "meta": {
            "format_version": "4.5",
            "model_format": "free",
            "box_uv": False,
        },
        "name": model_name,
        "model_identifier": "",
        "visible_box": [1, 1, 0],
        "variable_placeholders": "",
        "resolution": {"width": atlas_w, "height": atlas_h},
        "elements": elements,
        "outliner": outliner,
        "animations": bbmodel_animations,
        "textures": [{
            "path": "",
            "name": texture_file.split("/")[-1],
            "folder": "",
            "namespace": "",
            "id": "0",
            "width": atlas_w,
            "height": atlas_h,
            "uv_width": atlas_w,
            "uv_height": atlas_h,
            "particle": False,
            "layers_enabled": False,
            "use_as_default": True,
            "render_mode": "default",
            "frame_time": 1,
            "frame_order_type": "loop",
            "frame_order": "",
            "frame_interpolate": False,
            "visible": True,
            "internal": True,
            "saved": True,
            "uuid": texture_uuid,
            "relative_path": "",
            "source": f"data:image/png;base64,{b64}",
        }],
    }

    with open(out_file, "w") as f:
        json.dump(bbmodel, f, indent=2)

    cubes_file = out_file.replace(".bbmodel", "_cubes.json")
    with open(cubes_file, "w") as f:
        json.dump({
            "texture": texture_file.split("/")[-1],
            "texture_size": [atlas_w, atlas_h],
            "cubes": flat_cubes,
            "skeleton": skeleton,
            "animations": export_animations_for_viewer(animations) if animations else {},
        }, f)

    print(f"Wrote {out_file} ({len(elements)} cubes), {texture_file} ({atlas_w}x{atlas_h}), {cubes_file}")
    return cubes_file


# ---------------------------------------------------------------------------
# Model 1: demo_mob - simple humanoid (kept for reference / comparison)
# ---------------------------------------------------------------------------
demo_mob = [
    {"name": "body", "origin": [0, 10, 0], "cubes": [{"from": [-3, 6, -2], "to": [3, 14, 2]}]},
    {"name": "head", "origin": [0, 14, 0], "cubes": [{"from": [-2.5, 14, -2.5], "to": [2.5, 19, 2.5], "color": "#C9A882"}]},
    {"name": "left_arm", "origin": [3, 14, 0], "cubes": [{"from": [3, 8, -1.5], "to": [4.5, 14, 1.5]}]},
    {"name": "right_arm", "origin": [-3, 14, 0], "cubes": [{"from": [-4.5, 8, -1.5], "to": [-3, 14, 1.5]}]},
    {"name": "left_leg", "origin": [1.75, 6, 0], "cubes": [{"from": [0.5, 0, -1.5], "to": [3, 6, 1.5], "color": "#4A5A7A"}]},
    {"name": "right_leg", "origin": [-1.75, 6, 0], "cubes": [{"from": [-3, 0, -1.5], "to": [-0.5, 6, 1.5], "color": "#4A5A7A"}]},
]

# ---------------------------------------------------------------------------
# Model 2: golem_boss - tanque musculoso, brazos largos y articulados, gorila
# ---------------------------------------------------------------------------
HUNCH_DEG = 22  # forward lean of the torso (and, rigidly, head) around the hips

def arm_chain(side):
    """side = 1 (left, +x) or -1 (right, -x). Builds shoulder -> upper_arm -> forearm -> fist.
    Total span (top of shoulder to bottom of fist) = 29 units, kept under the body's
    total height (32 units) so the arms read as long/ape-like without exceeding the torso+legs+head.

    The shoulder counter-rotates by -HUNCH_DEG: since it's nested under the torso (which leans
    forward by HUNCH_DEG), without this the whole arm would inherit that tilt rigidly and swing
    backward instead of hanging down. Canceling it here keeps the arm hanging straight down (as
    originally designed) from the new, forward-shifted shoulder attachment point.
    """
    s = side
    tag = "left" if s > 0 else "right"
    return {
        "name": f"{tag}_shoulder",
        "origin": [s * 10.5, 25, 0],
        "rotation": [-HUNCH_DEG, 0, 0],
        "cubes": [{"from": [s * 7, 22, -5], "to": [s * 14, 28, 5]}],  # wide gorilla shoulder pad
        "children": [{
            "name": f"{tag}_upper_arm",
            "origin": [s * 10.5, 22, 0],
            "cubes": [
                {"from": [s * 8.5, 12, -3], "to": [s * 12.5, 22, 3]},          # bicep (slimmer than forearm)
                {"from": [s * 8, 12, -3.3], "to": [s * 13, 14.5, 3.3], "color": "#9C8873"},  # bicep bulge
            ],
            "children": [{
                "name": f"{tag}_forearm",
                "origin": [s * 10.5, 12, 0],
                "cubes": [
                    {"from": [s * 7, 5, -3.5], "to": [s * 13, 12, 3.5]},         # forearm (thicker than bicep)
                    {"from": [s * 6.5, 9.5, -4], "to": [s * 13.5, 12, 4], "color": "#55555A"},  # bracer/cuff
                ],
                "children": [{
                    "name": f"{tag}_hand",
                    "origin": [s * 10, 3, 0],
                    "cubes": [
                        {"from": [s * 6, 1.5, -5], "to": [s * 13, 4.2, 5]},                       # palm
                        {"from": [s * 6.5, 4.2, 1], "to": [s * 12.5, 5, 5], "color": "#3E3228"},  # knuckle ridge
                        {"from": [s * 4.5, 1.8, -1], "to": [s * 6.5, 3.6, 3], "color": "#4A3C30"},  # thumb
                    ],
                    "children": [],
                }],
            }],
        }],
    }


golem_boss = [
    {
        "name": "torso",
        "origin": [0, 10, 0],
        "rotation": [HUNCH_DEG, 0, 0],  # forward hunch, pivoting at the hips/waist (this part's origin)
        "cubes": [
            # Torso built as stacked segments of varying width for a gorilla hourglass-ish
            # silhouette: broad chest/shoulders -> tapered waist -> hips flare back out.
            {"from": [-7, 22, -4], "to": [7, 26, 4], "color": "#8A7A68"},        # chest (broadest point)
            {"from": [1, 22, 4], "to": [6.5, 26, 5.3], "color": "#9C8873"},      # left pectoral
            {"from": [-6.5, 22, 4], "to": [-1, 26, 5.3], "color": "#9C8873"},    # right pectoral
            {"from": [-5.5, 18, -3.5], "to": [5.5, 22, 3.5], "color": "#83725F"},  # ribs / upper abs
            {"from": [-4, 18, 3.5], "to": [4, 21, 5], "color": "#97846D"},       # abdomen muscle detail
            {"from": [-4, 14, -3], "to": [4, 18, 3], "color": "#6E5F4F"},        # waist (narrowest point)
            {"from": [-5, 10, -3.5], "to": [5, 14, 3.5], "color": "#7C6C59"},    # hips (flare for pelvis)
            {"from": [-2.5, 25.5, -2], "to": [2.5, 29, 2], "color": "#7A6A57"},  # trapezius / thick neck
        ],
        # head + both arm chains are nested here so they hunch forward together with the
        # torso (rigidly, around the torso's own origin/pivot) instead of staying upright.
        "children": [
            {
                "name": "head",
                "origin": [0, 27.5, 0],
                "cubes": [
                    # Cranium's front (south, +z) face is flush with the jaw's front face at z=2.8
                    # -- the two head pieces read as one continuous silhouette from the front.
                    # Sides (x) are untouched; at the back (north, -z) the cranium still overhangs
                    # the jaw a bit (-3 vs -2.8), which is intentional (sloped-skull look).
                    {"from": [-3, 29, -3], "to": [3, 32.5, 2.8], "color": "#8A7A68"},     # cranium
                    {"from": [-2.8, 26, -2.8], "to": [2.8, 29, 2.8], "color": "#6E5C4C", "id": "jaw"},  # jaw block (eyes get painted on its front face)
                    {"from": [-2.8, 26.3, 2.5], "to": [2.8, 27.8, 4.0], "color": "#5C4B3D"},  # muzzle/snout (same width as the jaw)
                    # Brow ridge split into independent left/right halves (touching at x=0, same
                    # overall footprint as the old single cube) so each side can be driven by its
                    # own keyframes later (raise/furrow) without touching the other.
                    {"from": [0, 30.3, 2.3], "to": [3, 31.1, 3.3], "color": "#4A3C30", "id": "brow_left"},
                    {"from": [-3, 30.3, 2.3], "to": [0, 31.1, 3.3], "color": "#4A3C30", "id": "brow_right"},
                    {"from": [3, 28, -1], "to": [4, 30, 1], "color": "#7A6A57"},         # left ear
                    {"from": [-4, 28, -1], "to": [-3, 30, 1], "color": "#7A6A57"},       # right ear
                ],
            },
            arm_chain(1),   # left arm chain (shoulder/upper/forearm/fist)
            arm_chain(-1),  # right arm chain
        ],
    },
    # Legs stay top-level (planted on the ground) -- they should NOT inherit the torso's lean.
    # Origin is at hip height (y=10, matching the torso's own origin), not the leg's midpoint --
    # a leg has to pivot from the hip, not its geometric center, or it visibly detaches from the
    # torso whenever it rotates by more than a few degrees (very noticeable in `death`).
    {
        "name": "left_leg",
        "origin": [3.5, 10, 0],
        "cubes": [
            {"from": [1, 0, -4], "to": [6, 10, 4], "color": "#83725F"},         # main leg
            {"from": [0.5, 5, 4], "to": [6.5, 8, 5.5], "color": "#55555A"},     # knee guard
        ],
    },
    {
        "name": "right_leg",
        "origin": [-3.5, 10, 0],
        "cubes": [
            {"from": [-6, 0, -4], "to": [-1, 10, 4], "color": "#83725F"},       # main leg
            {"from": [-6.5, 5, 4], "to": [-0.5, 8, 5.5], "color": "#55555A"},   # knee guard
        ],
    },
]

# ---------------------------------------------------------------------------
# Animations (golem_boss). Rotation/position values are DELTAS on top of each
# bone's own rest-pose rotation/origin (e.g. torso's HUNCH_DEG stays as the
# base; "idle" adds 0 rotation delta to it, "death" adds +73 to reach ~95 total).
# ---------------------------------------------------------------------------
golem_boss_animations = {
    "idle": {
        "loop": True, "length": 2.0,
        "keyframes": {
            "torso": [
                (0.0, {"position": [0, 0, 0]}),
                (1.0, {"position": [0, 0.35, 0]}),
                (2.0, {"position": [0, 0, 0]}),
            ],
            "left_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (1.0, {"rotation": [2.5, 0, 0]}),
                (2.0, {"rotation": [0, 0, 0]}),
            ],
            "right_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (1.0, {"rotation": [-2.5, 0, 0]}),
                (2.0, {"rotation": [0, 0, 0]}),
            ],
        },
    },
    "walk": {
        "loop": True, "length": 1.0,
        "keyframes": {
            "torso": [
                (0.0, {"position": [0, 0, 0]}),
                (0.25, {"position": [0, 0.6, 0]}),
                (0.5, {"position": [0, 0, 0]}),
                (0.75, {"position": [0, 0.6, 0]}),
                (1.0, {"position": [0, 0, 0]}),
            ],
            # Legs share the torso's `position` bob so the hip stays attached (same fix as run/death).
            "left_leg": [
                (0.0, {"rotation": [-25, 0, 0], "position": [0, 0, 0]}),
                (0.25, {"rotation": [0, 0, 0], "position": [0, 0.6, 0]}),
                (0.5, {"rotation": [25, 0, 0], "position": [0, 0, 0]}),
                (0.75, {"rotation": [0, 0, 0], "position": [0, 0.6, 0]}),
                (1.0, {"rotation": [-25, 0, 0], "position": [0, 0, 0]}),
            ],
            "right_leg": [
                (0.0, {"rotation": [25, 0, 0], "position": [0, 0, 0]}),
                (0.25, {"rotation": [0, 0, 0], "position": [0, 0.6, 0]}),
                (0.5, {"rotation": [-25, 0, 0], "position": [0, 0, 0]}),
                (0.75, {"rotation": [0, 0, 0], "position": [0, 0.6, 0]}),
                (1.0, {"rotation": [25, 0, 0], "position": [0, 0, 0]}),
            ],
            # arms counter-swing opposite their same-side leg, knuckle-walk style
            "left_upper_arm": [
                (0.0, {"rotation": [20, 0, 0]}),
                (0.5, {"rotation": [-20, 0, 0]}),
                (1.0, {"rotation": [20, 0, 0]}),
            ],
            "right_upper_arm": [
                (0.0, {"rotation": [-20, 0, 0]}),
                (0.5, {"rotation": [20, 0, 0]}),
                (1.0, {"rotation": [-20, 0, 0]}),
            ],
        },
    },
    "attack": {
        "loop": False, "length": 0.9,
        "keyframes": {
            # big windup (both arms raised high overhead) then a hard two-fisted ground
            # smash -- "aplastar con los puños" -- with a fast down-swing and a short
            # settle/rebound instead of a single punch-forward motion.
            "torso": [
                (0.0, {"rotation": [0, 0, 0], "position": [0, 0, 0]}),
                (0.30, {"rotation": [-15, 0, 0], "position": [0, 0.6, 0]}),   # lean back on windup
                (0.45, {"rotation": [28, 0, 0], "position": [0, -1.6, 0]}),  # slam impact
                (0.60, {"rotation": [16, 0, 0], "position": [0, -0.6, 0]}),  # settle
                (0.90, {"rotation": [0, 0, 0], "position": [0, 0, 0]}),
            ],
            "left_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (0.30, {"rotation": [-155, 0, 18]}),   # raised high overhead
                (0.45, {"rotation": [110, 0, -8]}),    # smashed down hard (fast: only 0.15s)
                (0.60, {"rotation": [85, 0, 0]}),       # rebound
                (0.90, {"rotation": [0, 0, 0]}),
            ],
            "right_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (0.30, {"rotation": [-155, 0, -18]}),
                (0.45, {"rotation": [110, 0, 8]}),
                (0.60, {"rotation": [85, 0, 0]}),
                (0.90, {"rotation": [0, 0, 0]}),
            ],
        },
    },
    "death": {
        "loop": False, "length": 1.4,
        "keyframes": {
            # Torso and legs pivot at (roughly) the same hip point and share the exact
            # same `position` delta at every keyframe, so the hip stays visually attached
            # throughout the collapse instead of the legs floating away from the torso.
            "torso": [
                (0.0, {"rotation": [0, 0, 0], "position": [0, 0, 0]}),
                (1.4, {"rotation": [70, 0, 8], "position": [0, -3, 2]}),
            ],
            "left_leg": [
                (0.0, {"rotation": [0, 0, 0], "position": [0, 0, 0]}),
                (1.4, {"rotation": [-15, 0, 10], "position": [0, -3, 2]}),
            ],
            "right_leg": [
                (0.0, {"rotation": [0, 0, 0], "position": [0, 0, 0]}),
                (1.4, {"rotation": [15, 0, -10], "position": [0, -3, 2]}),
            ],
            "left_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (1.4, {"rotation": [-30, 0, 25]}),
            ],
            "right_upper_arm": [
                (0.0, {"rotation": [0, 0, 0]}),
                (1.4, {"rotation": [-30, 0, -25]}),
            ],
        },
    },
    "run": {
        "loop": True, "length": 0.8,
        "keyframes": {
            # A 2-beat "bound" gait, not an alternating walk: BOTH arms plant forward together,
            # the torso swings/swoops forward and down over them, then BOTH legs land together
            # further forward while the arms release and swing through the air to reach for the
            # next plant -- the loping gait of orangutans/gorillas moving on the ground, not a
            # sped-up bipedal jog.
            "torso": [
                (0.00, {"rotation": [35, 0, 0], "position": [0, -1.6, 1.6]}),   # low, arms just planted
                (0.23, {"rotation": [14, 0, 0], "position": [0, 1.0, 0.6]}),    # swinging up/forward over the arms
                (0.46, {"rotation": [4, 0, 0], "position": [0, 1.9, -0.6]}),    # peak: most upright, legs land
                (0.63, {"rotation": [20, 0, 0], "position": [0, 0.2, 0.6]}),    # pitching forward again
                (0.80, {"rotation": [35, 0, 0], "position": [0, -1.6, 1.6]}),   # planted again (loops to 0.00)
            ],
            # Both arms move together (support side), not mirrored/alternating.
            "left_upper_arm": [
                (0.00, {"rotation": [95, 0, 8]}),     # planted forward, near max reach
                (0.23, {"rotation": [55, 0, 6]}),      # trailing as the body swings past
                (0.46, {"rotation": [-75, 0, 4]}),     # released, swinging back-and-up (recovery)
                (0.63, {"rotation": [15, 0, 6]}),       # swinging forward for the next plant
                (0.80, {"rotation": [95, 0, 8]}),
            ],
            "right_upper_arm": [
                (0.00, {"rotation": [95, 0, -8]}),
                (0.23, {"rotation": [55, 0, -6]}),
                (0.46, {"rotation": [-75, 0, -4]}),
                (0.63, {"rotation": [15, 0, -6]}),
                (0.80, {"rotation": [95, 0, -8]}),
            ],
            # Both legs also move together, roughly opposite phase to the arms: trailing while
            # the arms are planted, swinging forward together to land around the torso's peak.
            # They share the torso's exact `position` delta at every keyframe (same technique as
            # the `death` fix) so the hip point stays coincident with the torso instead of the
            # legs staying rooted while the torso swoops up/down and forward/back above them.
            "left_leg": [
                (0.00, {"rotation": [-32, 0, 4], "position": [0, -1.6, 1.6]}),
                (0.23, {"rotation": [8, 0, 3], "position": [0, 1.0, 0.6]}),
                (0.46, {"rotation": [42, 0, 2], "position": [0, 1.9, -0.6]}),
                (0.63, {"rotation": [10, 0, 3], "position": [0, 0.2, 0.6]}),
                (0.80, {"rotation": [-32, 0, 4], "position": [0, -1.6, 1.6]}),
            ],
            "right_leg": [
                (0.00, {"rotation": [-32, 0, -4], "position": [0, -1.6, 1.6]}),
                (0.23, {"rotation": [8, 0, -3], "position": [0, 1.0, 0.6]}),
                (0.46, {"rotation": [42, 0, -2], "position": [0, 1.9, -0.6]}),
                (0.63, {"rotation": [10, 0, -3], "position": [0, 0.2, 0.6]}),
                (0.80, {"rotation": [-32, 0, -4], "position": [0, -1.6, 1.6]}),
            ],
        },
    },
}


if __name__ == "__main__":
    build_bbmodel("demo_mob", demo_mob, "demo_mob.bbmodel")
    build_bbmodel("golem_boss", golem_boss, "golem_boss.bbmodel", animations=golem_boss_animations)
