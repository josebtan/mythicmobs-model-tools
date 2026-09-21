import json
import sys
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

cubes_file = sys.argv[1] if len(sys.argv) > 1 else "demo_mob_cubes.json"
prefix = cubes_file.replace("_cubes.json", "")

with open(cubes_file) as f:
    data = json.load(f)
cubes = data["cubes"] if isinstance(data, dict) else data

def cube_faces(c):
    # Minecraft coords are (x, y_up, z). matplotlib's default vertical axis
    # is its own Z, so remap: mpl_x = mc_x, mpl_y = mc_z, mpl_z = mc_y (up).
    fx, fy, fz = c["from"]
    tx, ty, tz = c["to"]
    local_center = np.array([(fx + tx) / 2, (fy + ty) / 2, (fz + tz) / 2])
    half = np.array([abs(tx - fx) / 2, abs(ty - fy) / 2, abs(tz - fz) / 2])
    world_center = np.array(c.get("world_center", local_center.tolist()))
    R = np.array(c.get("world_R", np.eye(3).tolist()))

    signs = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
             (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    corners_mc = [world_center + R @ (half * np.array(s)) for s in signs]
    pts = np.array([[p[0], p[2], p[1]] for p in corners_mc])  # mc(x,y,z) -> mpl(x,z,y)

    faces = [
        [pts[0], pts[1], pts[2], pts[3]],
        [pts[4], pts[5], pts[6], pts[7]],
        [pts[0], pts[1], pts[5], pts[4]],
        [pts[2], pts[3], pts[7], pts[6]],
        [pts[1], pts[2], pts[6], pts[5]],
        [pts[0], pts[3], pts[7], pts[4]],
    ]
    return faces, pts

colors = plt.cm.tab10.colors

def render(elev, azim, title, outfile):
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    all_pts = []
    for i, c in enumerate(cubes):
        faces, pts = cube_faces(c)
        poly = Poly3DCollection(faces, facecolor=colors[i % 10], edgecolor="black", linewidths=0.6, alpha=0.9)
        ax.add_collection3d(poly)
        all_pts.extend(pts.tolist())

    all_pts = np.array(all_pts)
    all_x, all_z_up, all_y = all_pts[:, 0], all_pts[:, 1], all_pts[:, 2]  # mpl axes: x, y(=mc z), z(=mc y/up)
    lim = max(np.abs(all_x).max(), np.abs(all_z_up).max()) + 1
    y_min, y_max = min(0, all_y.min()) - 1, all_y.max() + 1
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
