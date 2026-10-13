#!/usr/bin/env python3
"""
Make a .bbmodel loadable by BetterModel when Blockbench's glTF import left it with duplicate bone names.

    [BetterModel] java.lang.IllegalStateException: Duplicate key: cube and cube

BetterModel keys every bone (= Blockbench group) by its name, so names must be unique. Importing a glTF in
Blockbench turns every rotated cube into its own group, all of them called "cube".

    python3 fix_bbmodel_names.py model.bbmodel                 # -> model_fixed.bbmodel, names made unique
    python3 fix_bbmodel_names.py model.bbmodel --fold          # also merge the helper groups (see below)
    python3 fix_bbmodel_names.py model.bbmodel -o out.bbmodel

Unique names: the first group keeps its name, later ones become name_2, name_3, ... (case-insensitive). Animator
entries that point at a renamed group are updated too.

--fold (recommended): every group in BetterModel/ModelEngine becomes a separate display entity, so one helper
group per rotated cube (what Blockbench's importer makes) is expensive -- the Succubus goes from 58 to ~130 bones.
A group is folded into its parent when it is NOT animated, only holds cubes, and those cubes have no rotation of
their own: its rotation/pivot move onto the cubes (Blockbench "element rotation"), which looks exactly the same.
"""
import argparse
import json
import os
from collections import Counter


def is_zero(v, eps=1e-6):
    return all(abs(x) < eps for x in (v or [0, 0, 0]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bbmodel")
    ap.add_argument("-o", "--output")
    ap.add_argument("--fold", action="store_true", help="merge static single-purpose helper groups into their parent")
    args = ap.parse_args()

    with open(args.bbmodel) as f:
        bb = json.load(f)
    elements = {e["uuid"]: e for e in bb.get("elements", [])}

    # groups that some animation moves can never be folded away
    animated = set()
    for a in bb.get("animations", []):
        for gid, an in (a.get("animators") or {}).items():
            if an.get("keyframes"):
                animated.add(gid)

    folded = 0

    def foldable(g):
        if g["uuid"] in animated or not g.get("children"):
            return False
        if not all(isinstance(c, str) for c in g["children"]):
            return False
        return all(is_zero(elements[c].get("rotation")) for c in g["children"] if c in elements)

    def fold(group):
        nonlocal folded
        out = []
        for c in group["children"]:
            if isinstance(c, str):
                out.append(c)
                continue
            fold(c)
            if foldable(c):
                for uid in c["children"]:
                    el = elements.get(uid)
                    if el is not None:
                        # the group's rotation about its pivot == the same rotation on the element about that pivot
                        el["origin"] = list(c["origin"])
                        if not is_zero(c.get("rotation")):
                            el["rotation"] = list(c["rotation"])
                    out.append(uid)
                folded += 1
            else:
                out.append(c)
        group["children"] = out

    if args.fold:
        for top in bb["outliner"]:
            if isinstance(top, dict):
                fold(top)

    # ---- unique names ----------------------------------------------------------------------------
    seen = set()
    renamed = {}
    counts = Counter()

    def walk(nodes):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            name = n.get("name") or "bone"
            new = name
            while new.lower() in seen:
                counts[name] += 1
                new = f"{name}_{counts[name] + 1}"
            seen.add(new.lower())
            if new != n.get("name"):
                renamed[n["uuid"]] = (n.get("name"), new)
                n["name"] = new
            walk(n.get("children", []))

    walk(bb["outliner"])

    for a in bb.get("animations", []):
        for gid, an in (a.get("animators") or {}).items():
            if gid in renamed:
                an["name"] = renamed[gid][1]

    out = args.output or os.path.splitext(args.bbmodel)[0] + "_fixed.bbmodel"
    with open(out, "w") as f:
        json.dump(bb, f, separators=(",", ":"))

    total = len(seen)
    print(f"{args.bbmodel}: {total} bones after fixing" + (f" ({folded} helper groups folded)" if args.fold else ""))
    print(f"renamed {len(renamed)} duplicate bone names, e.g. " +
          ", ".join(f"{o}->{n}" for o, n in list(renamed.values())[:4]))
    print("wrote", out)


if __name__ == "__main__":
    main()
