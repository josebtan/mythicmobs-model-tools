import json, uuid

def uid():
    return str(uuid.uuid4())

# --- 1. Define the mob as a list of simple cuboids ---
# Each cuboid: name, from [x,y,z], to [x,y,z], origin [x,y,z] (pivot for rotation)
# Coordinates are in Minecraft "model units" (16 units = 1 block)
cubes_def = [
    {"name": "body",      "from": [-3, 6, -2], "to": [3, 14, 2],   "origin": [0, 10, 0]},
    {"name": "head",      "from": [-2.5, 14, -2.5], "to": [2.5, 19, 2.5], "origin": [0, 14, 0]},
    {"name": "left_arm",  "from": [3, 8, -1.5],  "to": [4.5, 14, 1.5],  "origin": [3, 14, 0]},
    {"name": "right_arm", "from": [-4.5, 8, -1.5], "to": [-3, 14, 1.5], "origin": [-3, 14, 0]},
    {"name": "left_leg",  "from": [0.5, 0, -1.5], "to": [3, 6, 1.5],   "origin": [1.75, 6, 0]},
    {"name": "right_leg", "from": [-3, 0, -1.5], "to": [-0.5, 6, 1.5], "origin": [-1.75, 6, 0]},
]

def make_faces():
    return {
        f: {"uv": [0, 0, 16, 16], "texture": 0}
        for f in ["north", "east", "south", "west", "up", "down"]
    }

elements = []
outliner_children = []

for c in cubes_def:
    cube_uuid = uid()
    elements.append({
        "name": c["name"],
        "from": c["from"],
        "to": c["to"],
        "autouv": 1,
        "color": 0,
        "origin": c["origin"],
        "uv_offset": [0, 0],
        "faces": make_faces(),
        "type": "cube",
        "uuid": cube_uuid,
    })
    outliner_children.append(cube_uuid)

bbmodel = {
    "meta": {
        "format_version": "4.5",
        "model_format": "free",
        "box_uv": False,
    },
    "name": "demo_mob",
    "model_identifier": "",
    "visible_box": [1, 1, 0],
    "variable_placeholders": "",
    "resolution": {"width": 16, "height": 16},
    "elements": elements,
    "outliner": [
        {
            "name": "root",
            "origin": [0, 0, 0],
            "color": 0,
            "uuid": uid(),
            "export": True,
            "isOpen": True,
            "locked": False,
            "visibility": True,
            "children": outliner_children,
        }
    ],
    "textures": [],
}

with open("demo_mob.bbmodel", "w") as f:
    json.dump(bbmodel, f, indent=2)

print("Wrote demo_mob.bbmodel with", len(cubes_def), "cubes")

# Also dump the raw cube list for the renderer to reuse (avoids re-parsing bbmodel format)
with open("cubes.json", "w") as f:
    json.dump(cubes_def, f)
