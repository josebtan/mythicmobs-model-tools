#!/usr/bin/env python3
"""Translate an ASCII FBX written by the Blockbench FBX exporter into a Blockbench-style .gltf
(embedded buffers/texture) that gltf_to_model.py can import.

    python3 fbx_to_gltf.py model.fbx texture.png out.gltf [--curves absolute|delta]

FBX units are cm (100 per block) -> glTF meters = value / 100. Models of class "Null" are bones,
"Mesh" models are cubes (8 verts, 6 quads -> expanded to 24 verts with normals and UVs).
Rotation order enum 0 (XYZ) is the matrix Rz*Ry*Rx, i.e. Blockbench's / three.js 'ZYX'.
--curves: whether animation values are absolute local TRS (default, auto-detected) or deltas.
"""
import argparse, base64, json, math, re, struct
import numpy as np

TICKS = 46186158000.0


def block(txt, start):
    """text of the {...} block opening at/after `start` (brace matching)."""
    i = txt.index('{', start)
    depth, j = 0, i
    while True:
        c = txt[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return txt[i:j + 1]
        j += 1


def arr(blk, key):
    m = re.search(key + r': \*\d+ \{\s*a: ([^}]*)\}', blk)
    return np.array([float(x) for x in m.group(1).replace('\n', '').split(',') if x.strip()]) if m else None


def prop(blk, name, n=3):
    m = re.search(r'P: "%s",[^\n]*?,\s*"[A-Z]*",((?:-?[\d.eE+-]+,?){%d})' % (re.escape(name), n), blk)
    return np.array([float(x) for x in m.group(1).strip(',').split(',')]) if m else np.zeros(n)


def euler_xyz_to_quat(deg):  # FBX order XYZ == matrix Rz*Ry*Rx
    x, y, z = np.radians(deg) / 2
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    # q = qz * qy * qx
    return [sx * cy * cz - cx * sy * sz, cx * sy * cz + sx * cy * sz,
            cx * cy * sz - sx * sy * cz, cx * cy * cz + sx * sy * sz]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fbx'); ap.add_argument('png'); ap.add_argument('out')
    ap.add_argument('--curves', choices=['auto', 'absolute', 'delta'], default='auto')
    a = ap.parse_args()
    txt = open(a.fbx, encoding='latin1').read()

    models = {}
    for m in re.finditer(r'\tModel: (\d+), "Model::([^"]*)", "([^"]*)"', txt):
        b = block(txt, m.end())
        models[int(m.group(1))] = dict(name=m.group(2), cls=m.group(3),
                                       T=prop(b, 'Lcl Translation'), R=prop(b, 'Lcl Rotation'),
                                       S=prop(b, 'Lcl Scaling') if 'Lcl Scaling' in b else np.ones(3))
    geoms = {}
    for m in re.finditer(r'\tGeometry: (\d+), "Geometry::[^"]*", "Mesh"', txt):
        b = block(txt, m.end())
        geoms[int(m.group(1))] = dict(V=arr(b, 'Vertices').reshape(-1, 3), I=arr(b, 'PolygonVertexIndex').astype(int),
                                      N=arr(b, 'Normals').reshape(-1, 3), UV=arr(b, 'UV').reshape(-1, 2))
    curves = {}
    for m in re.finditer(r'\tAnimationCurve: (\d+), "AnimCurve::[^"]*", ""', txt):
        b = block(txt, m.end())
        curves[int(m.group(1))] = (arr(b, 'KeyTime') / TICKS, arr(b, 'KeyValueFloat'))
    cnodes = {int(m.group(1)): m.group(2) for m in re.finditer(r'\tAnimationCurveNode: (\d+), "AnimCurveNode::([^"]*)"', txt)}

    parent, geom_of, cn_model, curve_cn = {}, {}, {}, {}
    for m in re.finditer(r'C: "(OO|OP)",(\d+),(\d+)(?:,\s*"([^"]*)")?', txt):
        kind, s, d, p = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        if s in models and (d in models or d == 0):
            parent[s] = d
        elif s in geoms and d in models:
            geom_of[d] = s
        elif s in cnodes and d in models:
            cn_model[s] = (d, p)
        elif s in curves and d in cnodes:
            curve_cn.setdefault(d, {})[p[-1]] = s

    # ---- nodes / meshes
    ids = list(models)
    idx = {mid: i for i, mid in enumerate(ids)}
    bin_ = bytearray(); views = []; accs = []

    def add(data, typ, count, comp=5126, minmax=None):
        off = len(bin_); bin_.extend(np.asarray(data, dtype='<f4').tobytes())
        views.append({'buffer': 0, 'byteOffset': off, 'byteLength': len(bin_) - off})
        acc = {'bufferView': len(views) - 1, 'componentType': comp, 'count': count, 'type': typ}
        if minmax:
            acc['min'], acc['max'] = minmax
        accs.append(acc); return len(accs) - 1

    nodes, meshes = [], []
    for mid in ids:
        md = models[mid]
        n = {'name': md['name']}
        if np.any(md['T']): n['translation'] = [float(v) / 100 for v in md['T']]
        if np.any(md['R']): n['rotation'] = euler_xyz_to_quat(md['R'])
        if not np.allclose(md['S'], 1): n['scale'] = [float(v) for v in md['S']]
        if md['cls'] == 'Mesh' and mid in geom_of:
            g = geoms[geom_of[mid]]
            P, N, U = [], [], []
            poly, start = 0, 0
            for k, vi in enumerate(g['I']):
                if vi < 0:
                    ids4 = [g['I'][start + j] if j < k - start else ~vi for j in range(k - start + 1)]
                    for j, vv in enumerate(ids4):
                        P.append(g['V'][vv] / 100); N.append(g['N'][poly]); u = g['UV'][start + j]; U.append([u[0], 1 - u[1]])
                    poly += 1; start = k + 1
            P, N, U = np.array(P), np.array(N), np.array(U)
            prim = {'attributes': {'POSITION': add(P, 'VEC3', len(P), minmax=[P.min(0).tolist(), P.max(0).tolist()]),
                                   'NORMAL': add(N, 'VEC3', len(N)), 'TEXCOORD_0': add(U, 'VEC2', len(U))}, 'material': 0}
            meshes.append({'primitives': [prim]}); n['mesh'] = len(meshes) - 1
        nodes.append(n)
    for mid, p in parent.items():
        if p:
            nodes[idx[p]].setdefault('children', []).append(idx[mid])
    roots = [idx[m] for m in ids if not parent.get(m)]

    # ---- animations (union of X/Y/Z key times per channel, absolute local TRS in glTF)
    byanim = {}
    for cn, (mid, p) in cn_model.items():
        path = {'Lcl Translation': 'translation', 'Lcl Rotation': 'rotation', 'Lcl Scaling': 'scale'}.get(p)
        if not path or cn not in curve_cn:
            continue
        aname = cnodes[cn].rsplit('.', 1)[0]
        byanim.setdefault(aname, []).append((mid, path, curve_cn[cn]))

    def sample(cdict, t, default):
        out = []
        for ax, d in zip('XYZ', default):
            if ax in cdict:
                kt, kv = curves[cdict[ax]]; out.append(float(np.interp(t, kt, kv)))
            else:
                out.append(d)
        return np.array(out)

    mode = a.curves
    if mode == 'auto':  # absolute curves start near the node's rest value; deltas start near 0
        err_abs = err_del = 0
        for lst in byanim.values():
            for mid, path, cd in lst:
                if path == 'translation' and 'X' in cd:
                    v0 = sample(cd, 0, models[mid]['T']); err_abs += np.abs(v0 - models[mid]['T']).sum(); err_del += np.abs(v0).sum()
        mode = 'absolute' if err_abs <= err_del else 'delta'
        print('curves detected as', mode, f'(err_abs={err_abs:.1f}, err_delta={err_del:.1f})')

    anims = []
    for aname, lst in byanim.items():
        channels, samplers = [], []
        for mid, path, cd in lst:
            md = models[mid]
            times = sorted({round(float(t), 6) for ax in cd.values() for t in curves[ax][0]})
            rest = {'translation': md['T'], 'rotation': md['R'], 'scale': md['S']}[path]
            vals = []
            for t in times:
                v = sample(cd, t, rest if mode == 'absolute' else np.zeros(3) if path != 'scale' else np.ones(3))
                if mode == 'delta':
                    v = rest + v if path != 'scale' else rest * v
                vals.append(euler_xyz_to_quat(v) if path == 'rotation' else (v / 100 if path == 'translation' else v))
            ti = add(times, 'SCALAR', len(times), minmax=[[min(times)], [max(times)]])
            vi = add(np.array(vals), 'VEC4' if path == 'rotation' else 'VEC3', len(vals))
            samplers.append({'input': ti, 'output': vi, 'interpolation': 'LINEAR'})
            channels.append({'sampler': len(samplers) - 1, 'target': {'node': idx[mid], 'path': path}})
        anims.append({'name': aname.split('.')[-1], 'channels': channels, 'samplers': samplers})

    png = base64.b64encode(open(a.png, 'rb').read()).decode()
    g = {'asset': {'version': '2.0', 'generator': 'fbx_to_gltf.py'}, 'scene': 0, 'scenes': [{'nodes': roots}],
         'nodes': nodes, 'meshes': meshes, 'animations': anims, 'accessors': accs, 'bufferViews': views,
         'buffers': [{'byteLength': len(bin_), 'uri': 'data:application/octet-stream;base64,' + base64.b64encode(bytes(bin_)).decode()}],
         'materials': [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}, 'alphaMode': 'MASK', 'doubleSided': True}],
         'textures': [{'source': 0, 'name': 'texture.png'}], 'images': [{'uri': 'data:image/png;base64,' + png}]}
    json.dump(g, open(a.out, 'w'))
    print(f'{len(nodes)} nodes, {len(meshes)} cubes, {len(anims)} animations -> {a.out}')


if __name__ == '__main__':
    main()
