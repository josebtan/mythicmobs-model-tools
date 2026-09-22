"""
Minimal 'box UV' packer + procedural texture painter.

Given a list of cuboids (w,h,d in the same units as the model, which already
match Minecraft's 16-units-per-block = 16px-per-block texture convention),
this assigns each cube a non-overlapping region in a texture atlas laid out
the same way Minecraft/Blockbench box-UV works (unwrap the 6 faces of a box
into a cross-like strip), then paints that atlas with a base color per cube,
simple per-face shading (fake AO) and light noise for texture.
"""
import random
from PIL import Image

FACE_SHADE = {
    "up": 1.25,
    "down": 0.55,
    "south": 1.0,   # +z, treated as the "front" of the model
    "north": 0.85,  # -z, back
    "east": 0.78,   # +x, side
    "west": 0.78,   # -x, side
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def face_rects(u, v, w, h, d):
    """Box-UV layout (u,v = top-left of this cube's footprint in the atlas)."""
    return {
        "east":  (u, v + d, u + d, v + d + h),
        "south": (u + d, v + d, u + d + w, v + d + h),
        "west":  (u + d + w, v + d, u + 2 * d + w, v + d + h),
        "north": (u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h),
        "up":    (u + d, v, u + d + w, v + d),
        "down":  (u + d + w, v, u + d + 2 * w, v + d),
    }


def footprint(w, h, d):
    return (2 * d + 2 * w, d + h)


def pack_cubes(cube_dims, atlas_width=128):
    """cube_dims: list of (w,h,d). Returns (list of (u,v) top-left placements, atlas_height)."""
    x = 0
    y = 0
    row_h = 0
    placements = []
    for (w, h, d) in cube_dims:
        fw, fh = footprint(w, h, d)
        fw, fh = int(round(fw)), int(round(fh))
        if x + fw > atlas_width and x > 0:
            x = 0
            y += row_h
            row_h = 0
        placements.append((x, y))
        x += fw
        row_h = max(row_h, fh)
    atlas_height = y + row_h
    return placements, atlas_height


def paint_face_detail(img, rect, rel_box, color):
    """Paint a small flat-color rectangle on top of an already-painted face.
    rect: (x1,y1,x2,y2) absolute pixel coords of the face (as returned in uv_by_index).
    rel_box: (x1,y1,x2,y2) in 0..1, relative to that face's own width/height.
    Used for cheap texture details (eyes, etc.) that don't need their own geometry.
    """
    x1, y1, x2, y2 = rect
    w, h = x2 - x1, y2 - y1
    rx1, ry1, rx2, ry2 = rel_box
    px1, py1 = x1 + rx1 * w, y1 + ry1 * h
    px2, py2 = x1 + rx2 * w, y1 + ry2 * h
    pixels = img.load()
    for px in range(int(round(px1)), max(int(round(px1)) + 1, int(round(px2)))):
        for py in range(int(round(py1)), max(int(round(py1)) + 1, int(round(py2)))):
            if 0 <= px < img.width and 0 <= py < img.height:
                pixels[px, py] = color


def paint_atlas(cubes, atlas_width=128, seed=42, scale=1):
    """
    cubes: list of dicts with keys w,h,d (ints/floats) and color (#RRGGBB).
    scale: supersamples every cube's texture footprint by this factor (geometry is
    unaffected -- this only gives small faces, like the jaw, more pixels to work with
    for painted details such as eyes).
    Returns (image: PIL.Image, uv_by_index: list of {face: [x1,y1,x2,y2]}).
    """
    rng = random.Random(seed)
    dims = [(c["w"] * scale, c["h"] * scale, c["d"] * scale) for c in cubes]
    placements, atlas_height = pack_cubes(dims, atlas_width)
    atlas_height = max(atlas_height, 1)

    img = Image.new("RGB", (atlas_width, atlas_height), (30, 30, 34))
    pixels = img.load()

    uv_by_index = []
    for cube, (u, v), (w, h, d) in zip(cubes, placements, dims):
        w, h, d = int(round(w)), int(round(h)), int(round(d))
        base = hex_to_rgb(cube["color"])
        rects = face_rects(u, v, w, h, d)
        uv_by_index.append({face: list(r) for face, r in rects.items()})

        for face, (x1, y1, x2, y2) in rects.items():
            shade = FACE_SHADE[face]
            for px in range(int(x1), int(x2)):
                for py in range(int(y1), int(y2)):
                    if px < 0 or py < 0 or px >= atlas_width or py >= atlas_height:
                        continue
                    noise = rng.randint(-9, 9)
                    r = max(0, min(255, int(base[0] * shade) + noise))
                    g = max(0, min(255, int(base[1] * shade) + noise))
                    b = max(0, min(255, int(base[2] * shade) + noise))
                    pixels[px, py] = (r, g, b)

    return img, uv_by_index
