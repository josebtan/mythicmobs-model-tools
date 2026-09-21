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

from texture_gen import paint_atlas

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
    "left_fist": "#4A3C30", "right_fist": "#4A3C30",
    "left_leg": "#83725F", "right_leg": "#83725F",
    "body": "#8A7A68",
    "left_arm": "#8A7A68", "right_arm": "#8A7A68",
}


def build_bbmodel(model_name, root_parts, out_file):
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
    atlas_img, uv_by_index = paint_atlas(leaf_cubes, atlas_width=128)
    atlas_w, atlas_h = atlas_img.size

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

    def make_faces(uv_rects):
        return {face: {"uv": rect, "texture": 0} for face, rect in uv_rects.items()}

    def build_group(part):
        cube_uuids = []
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

        child_groups = [build_group(child) for child in part.get("children", [])]

        return {
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

    outliner = [build_group(p) for p in root_parts]

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
def arm_chain(side):
    """side = 1 (left, +x) or -1 (right, -x). Builds shoulder -> upper_arm -> forearm -> fist.
    Total span (top of shoulder to bottom of fist) = 29 units, kept under the body's
    total height (32 units) so the arms read as long/ape-like without exceeding the torso+legs+head.
    """
    s = side
    tag = "left" if s > 0 else "right"
    return {
        "name": f"{tag}_shoulder",
        "origin": [s * 10.5, 25, 0],
        "cubes": [{"from": [s * 7, 22, -5], "to": [s * 14, 28, 5]}],  # wide gorilla shoulder pad
        "children": [{
            "name": f"{tag}_upper_arm",
            "origin": [s * 10.5, 22, 0],
            "cubes": [
                {"from": [s * 8, 12, -3.5], "to": [s * 13, 22, 3.5]},        # bicep block
                {"from": [s * 7.5, 12, -3.7], "to": [s * 13.5, 14.5, 3.7], "color": "#9C8873"},  # bicep bulge
            ],
            "children": [{
                "name": f"{tag}_forearm",
                "origin": [s * 10.5, 12, 0],
                "cubes": [
                    {"from": [s * 7, 4, -3.5], "to": [s * 13, 12, 3.5]},         # forearm (thick, gorilla-like)
                    {"from": [s * 6.5, 9.5, -4], "to": [s * 13.5, 12, 4], "color": "#55555A"},  # bracer/cuff
                ],
                "children": [{
                    "name": f"{tag}_fist",
                    "origin": [s * 10, 1.5, 0],
                    "cubes": [{"from": [s * 6, -1, -5.5], "to": [s * 14, 4, 5.5]}],  # big knuckle-dragging fist
                    "children": [],
                }],
            }],
        }],
    }


golem_boss = [
    {
        "name": "torso",
        "origin": [0, 10, 0],
        "rotation": [22, 0, 0],  # forward hunch, pivoting at the hips/waist (this part's origin)
        "cubes": [
            # Torso built as stacked segments of varying width for a gorilla hourglass-ish
            # silhouette: broad chest/shoulders -> tapered waist -> hips flare back out.
            {"from": [-7, 22, -4], "to": [7, 26, 4], "color": "#8A7A68"},        # chest (broadest point)
            {"from": [1, 22, 4], "to": [6.5, 26, 6.5], "color": "#9C8873"},      # left pectoral
            {"from": [-6.5, 22, 4], "to": [-1, 26, 6.5], "color": "#9C8873"},    # right pectoral
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
                    {"from": [-3, 29, -3], "to": [3, 32.5, 2.5], "color": "#8A7A68"},     # cranium
                    {"from": [-2.8, 26, -2.8], "to": [2.8, 29, 2.8], "color": "#6E5C4C"},  # jaw block
                    {"from": [-2, 26.3, 2.5], "to": [2, 28, 5.2], "color": "#5C4B3D"},    # muzzle/snout
                    {"from": [-3, 29.8, 2.3], "to": [3, 30.6, 3.3], "color": "#4A3C30"},  # brow ridge
                    {"from": [3, 28, -1], "to": [4, 30, 1], "color": "#7A6A57"},         # left ear
                    {"from": [-4, 28, -1], "to": [-3, 30, 1], "color": "#7A6A57"},       # right ear
                ],
            },
            arm_chain(1),   # left arm chain (shoulder/upper/forearm/fist)
            arm_chain(-1),  # right arm chain
        ],
    },
    # Legs stay top-level (planted on the ground) -- they should NOT inherit the torso's lean.
    {
        "name": "left_leg",
        "origin": [3.5, 5, 0],
        "cubes": [
            {"from": [1, 0, -4], "to": [6, 10, 4], "color": "#83725F"},         # main leg
            {"from": [0.5, 5, 4], "to": [6.5, 8, 5.5], "color": "#55555A"},     # knee guard
        ],
    },
    {
        "name": "right_leg",
        "origin": [-3.5, 5, 0],
        "cubes": [
            {"from": [-6, 0, -4], "to": [-1, 10, 4], "color": "#83725F"},       # main leg
            {"from": [-6.5, 5, 4], "to": [-0.5, 8, 5.5], "color": "#55555A"},   # knee guard
        ],
    },
]


if __name__ == "__main__":
    build_bbmodel("demo_mob", demo_mob, "demo_mob.bbmodel")
    build_bbmodel("golem_boss", golem_boss, "golem_boss.bbmodel")
