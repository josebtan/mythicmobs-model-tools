import json
import sys
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

cubes_file = sys.argv[1] if len(sys.argv) > 1 else "demo_mob_cubes.json"
prefix = cubes_file.replace("_cubes.json", "")

with open(cubes_file) as f:
    cubes = json.load(f)

def cube_faces(f, t):
    # Minecraft coords are (x, y_up, z). matplotlib's default vertical axis
    # is its own Z, so remap: mpl_x = mc_x, mpl_y = mc_z, mpl_z = mc_y (up).
    x0, y0, z0 = f
    x1, y1, z1 = t
    x0, y0, z0 = x0, z0, y0
    x1, y1, z1 = x1, z1, y1
    pts = np.array([
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ])
    faces = [
        [pts[0], pts[1], pts[2], pts[3]],
        [pts[4], pts[5], pts[6], pts[7]],
        [pts[0], pts[1], pts[5], pts[4]],
        [pts[2], pts[3], pts[7], pts[6]],
        [pts[1], pts[2], pts[6], pts[5]],
        [pts[0], pts[3], pts[7], pts[4]],
    ]
    return faces

colors = plt.cm.tab10.colors

def render(elev, azim, title, outfile):
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    all_pts = []
    for i, c in enumerate(cubes):
        faces = cube_faces(c["from"], c["to"])
        poly = Poly3DCollection(faces, facecolor=colors[i % 10], edgecolor="black", linewidths=0.6, alpha=0.9)
        ax.add_collection3d(poly)
        all_pts.extend(c["from"])
        all_pts.extend(c["to"])

    all_x = [c["from"][0] for c in cubes] + [c["to"][0] for c in cubes]
    all_y = [c["from"][1] for c in cubes] + [c["to"][1] for c in cubes]
    all_z = [c["from"][2] for c in cubes] + [c["to"][2] for c in cubes]
    lim = max(max(abs(v) for v in all_x), max(abs(v) for v in all_z)) + 1
    y_min, y_max = min(0, min(all_y)) - 1, max(all_y) + 1
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(y_min, y_max)
    ax.set_box_aspect([1, 1, (y_max - y_min) / (2 * lim)])
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(title)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y (up)")
    plt.tight_layout()
    plt.savefig(outfile, dpi=130)
    plt.close(fig)
    print("Saved", outfile)

render(elev=15, azim=-60, title="Isometric", outfile=f"{prefix}_preview_iso.png")
render(elev=0, azim=-90, title="Front", outfile=f"{prefix}_preview_front.png")
render(elev=0, azim=0, title="Side", outfile=f"{prefix}_preview_side.png")
