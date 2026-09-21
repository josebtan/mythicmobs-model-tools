"""
Generic .bbmodel builder with support for articulated bone hierarchies.

Each "part" is a dict:
{
    "name": str,
    "origin": [x, y, z],           # pivot point for this bone (for rotation/animation)
    "cubes": [ {"from":[..], "to":[..]}, ... ],   # 0+ cuboids attached to this bone
    "children": [ part, part, ... ]               # nested bones (e.g. forearm under upper arm)
}

This mirrors Blockbench's outliner group structure, so arms/legs built as a chain
of parts (shoulder -> upper_arm -> forearm -> fist) become real animatable bones,
not just floating cubes.
"""
import json
import uuid


def uid():
    return str(uuid.uuid4())


def make_faces():
    return {
        f: {"uv": [0, 0, 16, 16], "texture": 0}
        for f in ["north", "east", "south", "west", "up", "down"]
    }


def build_bbmodel(model_name, root_parts, out_file):
    elements = []
    flat_cubes = []  # for the simple renderer / web viewer

    def build_group(part):
        cube_uuids = []
        for i, cube in enumerate(part.get("cubes", [])):
            cube_uuid = uid()
            elements.append({
                "name": f'{part["name"]}_{i}' if len(part.get("cubes", [])) > 1 else part["name"],
                "from": cube["from"],
                "to": cube["to"],
                "autouv": 1,
                "color": 0,
                "origin": part["origin"],
                "uv_offset": [0, 0],
                "faces": make_faces(),
                "type": "cube",
                "uuid": cube_uuid,
            })
            cube_uuids.append(cube_uuid)
            flat_cubes.append({
                "name": part["name"],
                "from": cube["from"],
                "to": cube["to"],
                "origin": part["origin"],
            })

        child_groups = [build_group(child) for child in part.get("children", [])]

        return {
            "name": part["name"],
            "origin": part["origin"],
            "color": 0,
            "uuid": uid(),
            "export": True,
            "isOpen": True,
            "locked": False,
            "visibility": True,
            "children": cube_uuids + child_groups,
        }

    outliner = [build_group(p) for p in root_parts]

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
        "resolution": {"width": 32, "height": 32},
        "elements": elements,
        "outliner": outliner,
        "textures": [],
    }

    with open(out_file, "w") as f:
        json.dump(bbmodel, f, indent=2)

    cubes_file = out_file.replace(".bbmodel", "_cubes.json")
    with open(cubes_file, "w") as f:
        json.dump(flat_cubes, f)

    print(f"Wrote {out_file} ({len(elements)} cubes) and {cubes_file}")
    return cubes_file


# ---------------------------------------------------------------------------
# Model 1: demo_mob - simple humanoid (kept for reference / comparison)
# ---------------------------------------------------------------------------
demo_mob = [
    {"name": "body", "origin": [0, 10, 0], "cubes": [{"from": [-3, 6, -2], "to": [3, 14, 2]}]},
    {"name": "head", "origin": [0, 14, 0], "cubes": [{"from": [-2.5, 14, -2.5], "to": [2.5, 19, 2.5]}]},
    {"name": "left_arm", "origin": [3, 14, 0], "cubes": [{"from": [3, 8, -1.5], "to": [4.5, 14, 1.5]}]},
    {"name": "right_arm", "origin": [-3, 14, 0], "cubes": [{"from": [-4.5, 8, -1.5], "to": [-3, 14, 1.5]}]},
    {"name": "left_leg", "origin": [1.75, 6, 0], "cubes": [{"from": [0.5, 0, -1.5], "to": [3, 6, 1.5]}]},
    {"name": "right_leg", "origin": [-1.75, 6, 0], "cubes": [{"from": [-3, 0, -1.5], "to": [-0.5, 6, 1.5]}]},
]

# ---------------------------------------------------------------------------
# Model 2: golem_boss - tanque musculoso, brazos largos y articulados
# ---------------------------------------------------------------------------
def arm_chain(side):
    """side = 1 (left, +x) or -1 (right, -x). Builds shoulder -> upper_arm -> forearm -> fist.
    Total span (top of shoulder to bottom of fist) = 28 units, kept under the body's
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
                {"from": [s * 7.5, 12, -3.7], "to": [s * 13.5, 14.5, 3.7]},  # bicep bulge near elbow
            ],
            "children": [{
                "name": f"{tag}_forearm",
                "origin": [s * 10.5, 12, 0],
                "cubes": [
                    {"from": [s * 7, 4, -3.5], "to": [s * 13, 12, 3.5]},         # forearm (thick, gorilla-like)
                    {"from": [s * 6.5, 9.5, -4], "to": [s * 13.5, 12, 4]},       # armored bracer/cuff
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
        "cubes": [
            # Torso built as stacked segments of varying width for a gorilla hourglass-ish
            # silhouette: broad chest/shoulders -> tapered waist -> hips flare back out.
            {"from": [-7, 22, -4], "to": [7, 26, 4]},            # chest (broadest point)
            {"from": [1, 22, 4], "to": [6.5, 26, 6.5]},          # left pectoral
            {"from": [-6.5, 22, 4], "to": [-1, 26, 6.5]},        # right pectoral
            {"from": [-5.5, 18, -3.5], "to": [5.5, 22, 3.5]},    # ribs / upper abs (tapering in)
            {"from": [-4, 18, 3.5], "to": [4, 21, 5]},           # abdomen muscle detail
            {"from": [-4, 14, -3], "to": [4, 18, 3]},            # waist (narrowest point)
            {"from": [-5, 10, -3.5], "to": [5, 14, 3.5]},        # hips (wider than waist, flare for pelvis)
            {"from": [-2.5, 25.5, -2], "to": [2.5, 29, 2]},      # trapezius / thick neck
        ],
    },
    {
        "name": "head",
        "origin": [0, 27.5, 0],
        "cubes": [
            {"from": [-3, 29, -3], "to": [3, 32.5, 2.5]},        # cranium (upper/back skull)
            {"from": [-2.8, 26, -2.8], "to": [2.8, 29, 2.8]},    # lower head / jaw block
            {"from": [-2, 26.3, 2.5], "to": [2, 28, 5.2]},       # protruding muzzle/snout
            {"from": [-3, 29.8, 2.3], "to": [3, 30.6, 3.3]},     # brow ridge (front, above muzzle)
            {"from": [3, 28, -1], "to": [4, 30, 1]},             # left ear
            {"from": [-4, 28, -1], "to": [-3, 30, 1]},           # right ear
        ],
    },
    arm_chain(1),   # left arm chain (shoulder/upper/forearm/fist)
    arm_chain(-1),  # right arm chain
    {
        "name": "left_leg",
        "origin": [3.5, 5, 0],
        "cubes": [
            {"from": [1, 0, -4], "to": [6, 10, 4]},            # main leg
            {"from": [0.5, 5, 4], "to": [6.5, 8, 5.5]},        # knee guard
        ],
    },
    {
        "name": "right_leg",
        "origin": [-3.5, 5, 0],
        "cubes": [
            {"from": [-6, 0, -4], "to": [-1, 10, 4]},          # main leg
            {"from": [-6.5, 5, 4], "to": [-0.5, 8, 5.5]},      # knee guard
        ],
    },
]


if __name__ == "__main__":
    build_bbmodel("demo_mob", demo_mob, "demo_mob.bbmodel")
    build_bbmodel("golem_boss", golem_boss, "golem_boss.bbmodel")
