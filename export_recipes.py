"""Dump the Python-authored example models (demo_mob, golem_boss) as recipe JSON
files under recipes/, so they double as worked examples of RECIPE_SCHEMA.md.
Re-run this after editing demo_mob/golem_boss/golem_boss_animations in build_bbmodel.py
to keep the example recipes in sync."""
import json
import os

import build_bbmodel as bb


def animations_to_recipe_format(animations):
    if not animations:
        return None
    out = {}
    for anim_name, anim in animations.items():
        keyframes = {}
        for bone_name, kfs in anim["keyframes"].items():
            keyframes[bone_name] = [
                {"time": t, **data} for t, data in (bb._normalize_keyframe(kf) for kf in kfs)
            ]
        out[anim_name] = {"loop": anim.get("loop", False), "length": anim["length"], "keyframes": keyframes}
    return out


def dump(name, parts, animations, out_dir="recipes"):
    os.makedirs(out_dir, exist_ok=True)
    recipe = {"name": name, "parts": parts}
    anims = animations_to_recipe_format(animations)
    if anims:
        recipe["animations"] = anims
    path = os.path.join(out_dir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(recipe, f, indent=2)
    print(f"Wrote {path}")


if __name__ == "__main__":
    dump("demo_mob", bb.demo_mob, None)
    dump("golem_boss", bb.golem_boss, bb.golem_boss_animations)
