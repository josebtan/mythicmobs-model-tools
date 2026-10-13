#!/usr/bin/env python3
"""Make every group (bone) name in a .bbmodel unique.

BetterModel / ModelEngine key bones by name, so two groups called "cube" make the model fail to load
("IllegalStateException: Duplicate key: cube and cube"). Blockbench's glTF import produces exactly that.
Duplicates get a numeric suffix (cube, cube_2, cube_3 ...); animator names are kept in sync.

    python3 bbmodel_unique_names.py model.bbmodel [-o out.bbmodel] [--lower]
"""
import argparse
import json
import re
from collections import Counter


def fix(project, lower=False):
    groups = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, dict):
                groups.append(n)
                walk(n.get("children", []))

    walk(project.get("outliner", []))
    seen = Counter()
    renamed = {}
    for g in groups:
        base = g.get("name") or "bone"
        if lower:
            base = re.sub(r"[^a-z0-9_]", "_", base.lower())
        seen[base] += 1
        name = base if seen[base] == 1 else f"{base}_{seen[base]}"
        while name != base and any(o is not g and o.get("name") == name for o in groups):
            seen[base] += 1
            name = f"{base}_{seen[base]}"
        if name != g.get("name"):
            renamed[g["uuid"]] = (g.get("name"), name)
        g["name"] = name
    by_uuid = {g["uuid"]: g["name"] for g in groups}
    for anim in project.get("animations", []):
        for uuid, animator in anim.get("animators", {}).items():
            if uuid in by_uuid:
                animator["name"] = by_uuid[uuid]   # animators carry a copy of the bone name; keep it in sync
    return renamed, len(groups)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bbmodel")
    ap.add_argument("-o", "--output")
    ap.add_argument("--lower", action="store_true", help="also lowercase names / replace odd characters")
    args = ap.parse_args()
    with open(args.bbmodel) as f:
        project = json.load(f)
    renamed, total = fix(project, args.lower)
    out = args.output or re.sub(r"(\.bbmodel)?$", ".fixed.bbmodel", args.bbmodel, count=1)
    with open(out, "w") as f:
        json.dump(project, f, separators=(",", ":"))
    print(f"{total} groups, {len(renamed)} renamed -> {out}")
    for old, new in list(renamed.values())[:15]:
        print(f"  {old!r} -> {new!r}")
    if len(renamed) > 15:
        print(f"  ... and {len(renamed) - 15} more")


if __name__ == "__main__":
    main()
