// recipe_builder.js
// Client-side equivalent of build_bbmodel.py + texture_gen.py, so anyone can turn a
// recipe.json (see RECIPE_SCHEMA.md) into a previewable, downloadable mob directly in
// the browser -- no Python install required. Mirrors the Python box-UV packing/shading
// logic closely so a recipe generates the same result either way.

const RB_FACE_SHADE = { up: 1.25, down: 0.55, south: 1.0, north: 0.85, east: 0.78, west: 0.78 };
const RB_DEFAULT_COLOR = '#8A7A68';

function rbHexToRgb(hex) {
  hex = (hex || RB_DEFAULT_COLOR).replace('#', '');
  return [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)];
}

function rbUid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function rbFaceRects(u, v, w, h, d) {
  return {
    east: [u, v + d, u + d, v + d + h],
    south: [u + d, v + d, u + d + w, v + d + h],
    west: [u + d + w, v + d, u + 2 * d + w, v + d + h],
    north: [u + 2 * d + w, v + d, u + 2 * d + 2 * w, v + d + h],
    up: [u + d, v, u + d + w, v + d],
    down: [u + d + w, v, u + d + 2 * w, v + d],
  };
}

function rbFootprint(w, h, d) {
  return [2 * d + 2 * w, d + h];
}

function rbPackCubes(dims, atlasWidth, padding = 1) {
  // Mirrors texture_gen.py's pack_cubes exactly: primary sort by tallest footprint
  // first, secondary sort by exact (w,h,d) so left/right mirror pairs (identical
  // dimensions) land next to each other in the atlas; `padding` keeps neighboring
  // cube footprints from bleeding into each other under texture filtering.
  const order = dims.map((_, i) => i).sort((a, b) => {
    const [, fhA] = rbFootprint(...dims[a]);
    const [, fhB] = rbFootprint(...dims[b]);
    if (fhB !== fhA) return fhB - fhA;
    for (let k = 0; k < 3; k++) { if (dims[a][k] !== dims[b][k]) return dims[a][k] - dims[b][k]; }
    return 0;
  });
  let x = 0, y = 0, rowH = 0;
  const placements = new Array(dims.length);
  for (const i of order) {
    const [w, h, d] = dims[i];
    let [fw, fh] = rbFootprint(w, h, d);
    fw = Math.round(fw) + padding; fh = Math.round(fh) + padding;
    if (x + fw > atlasWidth && x > 0) { x = 0; y += rowH; rowH = 0; }
    placements[i] = [x, y];
    x += fw;
    rowH = Math.max(rowH, fh);
  }
  return [placements, y + rowH];
}

// cubes: [{w,h,d,color}]. Returns {canvas, uvByIndex: [{face:[x1,y1,x2,y2]}]}.
function rbPaintAtlas(cubes, atlasWidth = 128) {
  const dims = cubes.map((c) => [c.w, c.h, c.d]);
  const [placements, atlasHeightRaw] = rbPackCubes(dims, atlasWidth);
  const atlasHeight = Math.max(atlasHeightRaw, 1);

  const canvas = document.createElement('canvas');
  canvas.width = atlasWidth;
  canvas.height = atlasHeight;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgb(30,30,34)';
  ctx.fillRect(0, 0, atlasWidth, atlasHeight);

  const uvByIndex = [];
  cubes.forEach((cube, i) => {
    const [u, v] = placements[i];
    const [w, h, d] = [Math.round(dims[i][0]), Math.round(dims[i][1]), Math.round(dims[i][2])];
    const rects = rbFaceRects(u, v, w, h, d);
    uvByIndex.push(rects);
    const base = rbHexToRgb(cube.color);
    Object.entries(rects).forEach(([face, [x1, y1, x2, y2]]) => {
      const shade = RB_FACE_SHADE[face];
      for (let px = x1; px < x2; px++) {
        for (let py = y1; py < y2; py++) {
          if (px < 0 || py < 0 || px >= atlasWidth || py >= atlasHeight) continue;
          const noise = Math.floor(Math.random() * 19) - 9;
          const r = Math.max(0, Math.min(255, Math.round(base[0] * shade) + noise));
          const g = Math.max(0, Math.min(255, Math.round(base[1] * shade) + noise));
          const b = Math.max(0, Math.min(255, Math.round(base[2] * shade) + noise));
          ctx.fillStyle = `rgb(${r},${g},${b})`;
          ctx.fillRect(px, py, 1, 1);
        }
      }
    });
  });
  return { canvas, uvByIndex };
}

// Walk the recipe's `parts` tree, collect every leaf cube (for packing) in the same
// depth-first order buildSkeletonWithUV will use to re-attach uv_faces afterwards.
function rbCollectLeafCubes(parts) {
  const leaves = [];
  function walk(part) {
    (part.cubes || []).forEach((cube) => {
      const [fx, fy, fz] = cube.from, [tx, ty, tz] = cube.to;
      leaves.push({
        w: Math.abs(tx - fx), h: Math.abs(ty - fy), d: Math.abs(tz - fz),
        color: cube.color || RB_DEFAULT_COLOR, id: cube.id,
      });
    });
    (part.children || []).forEach(walk);
  }
  (parts || []).forEach(walk);
  return leaves;
}

// Rebuilds the parts tree with each cube's resolved color + computed uv_faces attached
// -- i.e. exactly the "skeleton" shape index.html's buildBone() already knows how to render.
// Also returns a flat cube list (name/from/to/uv_faces) in the same shape the rest of the
// viewer expects for `data.cubes` (stats count, the paint editor's UV mask).
function rbBuildSkeleton(parts, uvByIndex, leaves) {
  let idx = 0;
  const flatCubes = [];
  function walk(part) {
    const cubes = (part.cubes || []).map((cube) => {
      const leaf = leaves[idx];
      const entry = { from: cube.from, to: cube.to, color: leaf.color, uv_faces: uvByIndex[idx] };
      const flatEntry = { name: part.name, from: cube.from, to: cube.to, uv_faces: uvByIndex[idx] };
      // Preserve "id" (e.g. "brow_left"/"brow_right") so the viewer's mirror tool can
      // pair cubes sharing one bone -- matches build_bbmodel.py's export exactly.
      if (leaf.id) { entry.id = leaf.id; flatEntry.id = leaf.id; }
      flatCubes.push(flatEntry);
      idx++;
      return entry;
    });
    const children = (part.children || []).map(walk);
    return { name: part.name, origin: part.origin, rotation: part.rotation || [0, 0, 0], cubes, children };
  }
  const skeleton = (parts || []).map(walk);
  return { skeleton, flatCubes };
}

// recipe.animations (keyframes, deltas) -> the viewer's {loop,length,tracks} shape.
// The recipe format already stores keyframes as {time, rotation?, position?} objects
// per bone, which is exactly what "tracks" needs -- this is just a key rename.
function rbAnimationsToTracks(animations) {
  const out = {};
  Object.entries(animations || {}).forEach(([name, anim]) => {
    out[name] = { loop: !!anim.loop, length: anim.length, tracks: anim.keyframes || {} };
  });
  return out;
}

// Validates + converts a recipe into everything the viewer and the .bbmodel exporter need.
// Throws with a human-readable message on anything invalid (bad JSON is caught by the caller).
function rbProcessRecipe(recipe) {
  if (!recipe.name) throw new Error('Falta "name" en la receta.');
  if (!recipe.parts || !Array.isArray(recipe.parts) || !recipe.parts.length) {
    throw new Error('Falta "parts" (o está vacío) en la receta.');
  }
  const leaves = rbCollectLeafCubes(recipe.parts);
  if (!leaves.length) throw new Error('El modelo no tiene ningún cubo (revisá "cubes" en cada parte).');

  const { canvas, uvByIndex } = rbPaintAtlas(leaves, 128);
  const { skeleton, flatCubes } = rbBuildSkeleton(recipe.parts, uvByIndex, leaves);
  const animations = rbAnimationsToTracks(recipe.animations);
  // viewerData is shaped exactly like a fetched *_cubes.json -- pass it straight to the
  // viewer's own buildModel(data), so texture painting / saving to the library / the part
  // tree panel / everything else just works without any recipe-specific code for them.
  const viewerData = {
    name: recipe.name,
    texture: canvas.toDataURL('image/png'),
    texture_size: [canvas.width, canvas.height],
    cubes: flatCubes,
    skeleton,
    animations,
  };
  return { name: recipe.name, skeleton, animations, atlasCanvas: canvas, cubeCount: leaves.length, viewerData };
}

// Assembles the full Blockbench .bbmodel JSON (elements + outliner + embedded texture +
// animations), mirroring build_bbmodel.py's build_group()/build_bbmodel_animations().
// Returns a Promise<object> because reading the canvas as a data URL is async.
function rbBuildBBModelJSON(recipeName, skeleton, atlasCanvas, animationsRaw) {
  const elements = [];
  const boneUuidByName = {};

  function buildGroup(node) {
    const n = (node.cubes || []).length;
    const cubeUuids = (node.cubes || []).map((c, i) => {
      const cu = rbUid();
      elements.push({
        name: n > 1 ? `${node.name}_${i}` : node.name,
        from: c.from, to: c.to, autouv: 0, color: 0, origin: node.origin, uv_offset: [0, 0],
        faces: Object.fromEntries(Object.entries(c.uv_faces).map(([f, r]) => [f, { uv: r, texture: 0 }])),
        type: 'cube', uuid: cu,
      });
      return cu;
    });
    const childGroups = (node.children || []).map(buildGroup);
    const grp = {
      name: node.name, origin: node.origin, rotation: node.rotation || [0, 0, 0], color: 0,
      uuid: rbUid(), export: true, isOpen: true, locked: false, visibility: true,
      children: [...cubeUuids, ...childGroups],
    };
    boneUuidByName[node.name] = grp.uuid;
    return grp;
  }
  const outliner = skeleton.map(buildGroup);

  const animations = [];
  Object.entries(animationsRaw || {}).forEach(([name, anim]) => {
    const animators = {};
    Object.entries(anim.keyframes || {}).forEach(([boneName, kfs]) => {
      const bu = boneUuidByName[boneName];
      if (!bu) return;
      const keyframes = [];
      (kfs || []).forEach((kf) => {
        ['rotation', 'position'].forEach((ch) => {
          if (kf[ch]) {
            const [x, y, z] = kf[ch];
            keyframes.push({
              channel: ch, data_points: [{ x: String(x), y: String(y), z: String(z) }],
              uuid: rbUid(), time: kf.time, color: -1, interpolation: 'linear',
            });
          }
        });
      });
      animators[bu] = { name: boneName, type: 'bone', keyframes };
    });
    animations.push({
      uuid: rbUid(), name, loop: anim.loop ? 'loop' : 'once', override: false, length: anim.length,
      snapping: 24, selected: false, anim_time_update: '', blend_weight: '', start_delay: '',
      loop_delay: '', animators,
    });
  });

  return new Promise((resolve, reject) => {
    atlasCanvas.toBlob((blob) => {
      if (!blob) { reject(new Error('No se pudo generar la textura')); return; }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result;
        resolve({
          meta: { format_version: '4.5', model_format: 'free', box_uv: false },
          name: recipeName, model_identifier: '', visible_box: [1, 1, 0], variable_placeholders: '',
          resolution: { width: atlasCanvas.width, height: atlasCanvas.height },
          elements, outliner, animations,
          textures: [{
            path: '', name: `${recipeName}_texture.png`, folder: '', namespace: '', id: '0',
            width: atlasCanvas.width, height: atlasCanvas.height,
            uv_width: atlasCanvas.width, uv_height: atlasCanvas.height,
            particle: false, layers_enabled: false, use_as_default: true, render_mode: 'default',
            frame_time: 1, frame_order_type: 'loop', frame_order: '', frame_interpolate: false,
            visible: true, internal: true, saved: true, uuid: rbUid(), relative_path: '',
            source: dataUrl,
          }],
        });
      };
      reader.readAsDataURL(blob);
    }, 'image/png');
  });
}
