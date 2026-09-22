# MythicMobs Model Tools

Herramientas para generar modelos `.bbmodel` (compatibles con [Blockbench](https://www.blockbench.net/)
y [ModelEngine](https://wiki.mythiccraft.io/modelengine)) de forma programática, más una vista previa
renderizada para validar proporciones antes de abrirlos en Blockbench.

## Contenido

- `build_bbmodel.py` — genera archivos `.bbmodel` (JSON válido de Blockbench) a partir de una
  definición jerárquica de **partes/huesos** (`name`, `origin`, `cubes`, `children`). Los `children`
  permiten armar cadenas articuladas reales (ej. hombro → antebrazo → puño), cada una como bone
  independiente y rotable en Blockbench/ModelEngine — no solo cubos sueltos. También genera y
  empaqueta la **textura** de cada modelo (ver `texture_gen.py`).
- `texture_gen.py` — empaqueta cada cubo en un atlas de textura usando el mismo esquema de **box UV**
  que Minecraft (unwrap en cruz de las 6 caras), y lo pinta con Pillow: color base por cubo, sombreado
  simple por cara (más clara arriba, más oscura abajo, como un AO falso) y ruido para textura de piel/roca.
- `render_preview.py` — toma el `*_cubes.json` de un modelo y lo renderiza con matplotlib en 3
  ángulos (isométrico, frente, lateral) para chequear proporciones sin abrir Blockbench (colores
  planos, no usa la textura real).
  Uso: `python3 render_preview.py <nombre>_cubes.json`
- `index.html` — visor 3D interactivo (Three.js) publicado vía GitHub Pages, con selector de
  modelo, textura real aplicada por UV, selector de **animaciones** (keyframes reales), y botón de
  descarga del `.bbmodel`.

### Modelos incluidos

| Modelo | Archivo | Descripción |
|---|---|---|
| `demo_mob` | `demo_mob.bbmodel` | Humanoide básico de referencia (cabeza, torso, brazos, piernas). Sin animaciones. |
| `golem_boss` | `golem_boss.bbmodel` | Boss tipo tanque/gorila: torso ancho y musculoso, cabeza pequeña, hombreras, brazos largos y articulados (hombro→antebrazo→puño), encorvado hacia adelante. Animaciones: `idle`, `walk`, `run`, `attack`, `death`. |

## Uso

```bash
pip install matplotlib numpy --break-system-packages

python3 build_bbmodel.py                        # genera *.bbmodel + *_cubes.json para todos los modelos
python3 render_preview.py golem_boss_cubes.json  # genera golem_boss_preview_{iso,front,side}.png
```

Para crear o modificar un modelo, editá las listas al final de `build_bbmodel.py` (`demo_mob`,
`golem_boss`, o agregá una nueva) usando la estructura de partes con `origin`/`cubes`/`children`,
volvé a correr los scripts, revisá las imágenes de preview o la página web, y cuando el modelo se
vea bien abrí el `.bbmodel` resultante en Blockbench para texturizar y animar del todo.

## Visor 3D (GitHub Pages)

https://josebtan.github.io/mythicmobs-model-tools/

Página estática con Three.js. Controles:
- Arrastrar para rotar la cámara, scroll para zoom.
- Selector de modelo.
- **Textura on/off** — alterna entre la textura real y el color plano por cubo (útil para revisar
  proporciones/silueta sin que la textura distraiga).
- **Animación** (selector) — `idle`, `walk`, `run`, `attack`, `death` para el golem. Reproduce keyframes
  reales interpolados en vivo (ver sección Animaciones abajo).
- **Auto-rotar** — gira el modelo solo, para verlo desde todos los ángulos sin tocar el mouse.
- Botón de descarga del `.bbmodel` del modelo activo.
- Panel responsive: en pantallas angostas los paneles pasan a ocupar el ancho completo en vez de
  superponerse.

El modelo se construye en el visor como una **jerarquía real de huesos** (un `THREE.Group` por
hueso, anidado igual que en `build_bbmodel.py`), no como una lista plana de cubos — es lo que
permite tanto el encorvado del golem como la animación de abajo.

## Animaciones

Cada hueso tiene una `rotation` (y opcionalmente `position`) propia que pivota alrededor de su
`origin`, y los hijos (ej. brazo colgando del hombro) heredan la transformación de sus padres
automáticamente — así armamos la postura encorvada del golem. Una animación es exactamente lo
mismo, pero variando esos valores en el tiempo: por eso los clips se definen como **deltas** sobre
la pose de reposo de cada hueso (ej. el torso del golem tiene 22° de encorvado en reposo; la
animación `death` le suma +73° más, hasta ~95° total — nunca se pisan).

**Definir un clip** (en `build_bbmodel.py`, junto a `golem_boss_animations`):
```python
"idle": {
    "loop": True, "length": 2.0,
    "keyframes": {
        "torso": [(0.0, {"position": [0,0,0]}), (1.0, {"position": [0,0.35,0]}), (2.0, {"position": [0,0,0]})],
    },
},
```
`time` en segundos, `rotation`/`position` como deltas `[x,y,z]`. Un hueso puede tener ambos
canales si en algún keyframe define los dos (ver `death`, que combina `rotation` + `position` en
el torso).

**Dónde termina**: `build_bbmodel_animations()` convierte esto al campo `"animations"` del
`.bbmodel` (formato nativo de Blockbench — channels `rotation`/`position` por uuid de hueso), así
que el mismo clip se puede abrir, ver y retocar directamente en Blockbench, y ModelEngine lo
reproduce en el server tal cual. `export_animations_for_viewer()` exporta una versión más liviana
(por nombre de hueso, no uuid) al `*_cubes.json` para el visor web.

**En el visor**: `applyAnimationFrame()` en `index.html` interpola linealmente entre keyframes
(`sampleTrack`) y aplica el delta sobre la rotación/posición base de cada `THREE.Group` — sin
funciones seno a mano, lee los keyframes reales del JSON. El selector "Animación" del panel elige
el clip; las que tienen `loop: false` (`attack`, `death`) se reproducen una vez y quedan en el
último frame.

**Animaciones del golem:**
- `idle` — respiración: el torso sube/baja levemente (cabeza y brazos lo acompañan por estar
  anidados dentro), leve balanceo de brazos. Piernas fijas.
- `walk` — piernas alternan adelante/atrás, brazos contra-balancean estilo "knuckle-walk", torso
  rebota con cada paso.
- `run` — no es solo `walk` más rápido: es un "bound" de 2 tiempos tipo orangután/gorila. **Ambos
  brazos se apoyan juntos** (no alternados) bien adelante, el torso se **columpia** hacia
  adelante y abajo sobre ellos, y al llegar al punto más alto/vertical **ambas piernas** aterrizan
  juntas más adelante mientras los brazos se sueltan y vuelan hacia adelante para el próximo apoyo.
- `attack` — brazos se preparan hacia atrás y golpean hacia adelante/abajo juntos, torso acompaña
  el impulso. No repite (`loop: false`).
- `death` — el torso cae hacia adelante y se hunde, piernas ceden hacia los costados. No repite.

## Por qué existe esto

Blockbench es una app de escritorio con interfaz gráfica; un asistente de IA sin pantalla no puede
operarla directamente. Este repo genera el mismo formato de archivo que usa Blockbench (JSON) y
agrega un loop de verificación visual (renders con matplotlib, y ahora el visor 3D interactivo) para
poder iterar sobre las proporciones y la ubicación de las piezas sin trabajar completamente a ciegas.

## Roadmap / ideas pendientes

- Interpolación con easing (no solo lineal) para animaciones más "pesadas"/orgánicas.
- Blending entre animaciones (ej. transición suave `idle` → `walk` en vez de corte seco).
- Texturas más elaboradas: patrones (rayas, manchas, pelaje), no solo color plano + ruido.
- Revisar orientación exacta del UV por cara en el visor (`applyBoxUV` en `index.html`) — puede haber
  alguna cara reflejada/rotada respecto al eje esperado; se corrige a ojo comparando contra Blockbench.
- Exportar directamente la config `.yml` de MythicMobs + ModelEngine junto al modelo.
