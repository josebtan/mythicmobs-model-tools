# MythicMobs Model Tools

Herramientas para generar modelos `.bbmodel` (compatibles con [Blockbench](https://www.blockbench.net/)
y [ModelEngine](https://wiki.mythiccraft.io/modelengine)) de forma programática, más una vista previa
renderizada para validar proporciones antes de abrirlos en Blockbench.

## Contenido

- `build_bbmodel.py` — genera archivos `.bbmodel` (JSON válido de Blockbench) a partir de una
  definición jerárquica de **partes/huesos** (`name`, `origin`, `cubes`, `children`). Los `children`
  permiten armar cadenas articuladas reales (ej. hombro → antebrazo → puño), cada una como bone
  independiente y rotable en Blockbench/ModelEngine — no solo cubos sueltos. También genera y
  empaqueta la **textura** de cada modelo (ver `texture_gen.py`). Se puede usar como CLI con una
  **receta JSON** (ver sección de abajo) además de los modelos definidos en Python.
- `RECIPE_SCHEMA.md` — el formato de receta JSON, documentado para que cualquier persona o agente
  de IA pueda crear un mob nuevo sin tocar código ni tener el contexto de este repo.
- `recipes/*.json` — recetas de ejemplo (`demo_mob.json`, `golem_boss.json`), exportadas 1:1 desde
  las definiciones en Python con `export_recipes.py`.
- `models.json` — lista de modelos que muestra el visor web. Agregar un mob acá alcanza para que
  aparezca en el selector, sin tocar `index.html`.
- `texture_gen.py` — empaqueta cada cubo en un atlas de textura usando el mismo esquema de **box UV**
  que Minecraft (unwrap en cruz de las 6 caras), y lo pinta con Pillow: color base por cubo, sombreado
  simple por cara (más clara arriba, más oscura abajo, como un AO falso) y ruido para textura de piel/roca.
- `render_preview.py` — toma el `*_cubes.json` de un modelo y lo renderiza con matplotlib en 3
  ángulos (isométrico, frente, lateral) para chequear proporciones sin abrir Blockbench (colores
  planos, no usa la textura real).
  Uso: `python3 render_preview.py <nombre>_cubes.json`
- `index.html` — visor 3D interactivo (Three.js) publicado vía GitHub Pages, con selector de
  modelo, textura real aplicada por UV, selector de **animaciones** (keyframes reales), **editor de
  textura** integrado (pincel, borrador, cuentagotas, balde, degradado — pintable directo sobre el
  modelo 3D o sobre el atlas plano), y botón de descarga del `.bbmodel`.

### Modelos incluidos

| Modelo | Archivo | Descripción |
|---|---|---|
| `demo_mob` | `demo_mob.bbmodel` | Humanoide básico de referencia (cabeza, torso, brazos, piernas). Sin animaciones. |
| `golem_boss` | `golem_boss.bbmodel` | Boss tipo tanque/gorila: torso ancho y musculoso, cabeza pequeña, hombreras, brazos largos y articulados (hombro→antebrazo→puño), encorvado hacia adelante. Animaciones: `idle`, `walk`, `run`, `attack`, `death`. |

## Crear tu propio mob (para otras personas / otros agentes)

Esta herramienta no está atada a Claude ni a esta conversación — la interfaz es un archivo JSON
(una "receta"), documentado en **[`RECIPE_SCHEMA.md`](RECIPE_SCHEMA.md)**. Cualquier agente de IA
(Claude, ChatGPT, lo que sea) puede leer ese documento y generar una receta válida sin más
contexto que ese archivo.

Flujo para alguien nuevo (persona o agente) — **sin instalar nada**:

1. Escribir un `recipe.json` siguiendo `RECIPE_SCHEMA.md` (o pedirle a un agente que lo haga).
2. Abrir el visor, panel **"🧩 Crear mob (JSON)"**, pegar la receta, "Generar / Previsualizar".
3. Guardarlo en la biblioteca (login con Google) para compartirlo, o descargar el `.bbmodel` y la
   textura directo desde el panel.

O, si preferís la línea de comandos:

1. Escribir el `recipe.json` (mismo formato).
2. `python3 build_bbmodel.py recipe.json` → genera `.bbmodel` + textura + `*_cubes.json`.
3. Abrir el `.bbmodel` en Blockbench para texturizar/ajustar a mano, o revisar el resultado con
   `render_preview.py`.
4. Agregar una entrada en `models.json` → el mob aparece en el selector "de fábrica" del visor
   (distinto de la biblioteca) sin tocar `index.html`.
5. Commit + push (o un PR, si es un repo compartido con más gente).

No hace falta pedirle nada a un asistente en particular: el generador (`build_bbmodel.py` /
`recipe_builder.js`, su equivalente en el navegador) y el visor (`index.html`) son genéricos — no
tienen ningún nombre de hueso ni de modelo hardcodeado. Todo lo que hoy es específico del golem
(proporciones, animaciones, colores) vive únicamente en `recipes/golem_boss.json` / la función
`golem_boss` de `build_bbmodel.py`.

## Uso

```bash
pip install matplotlib numpy Pillow --break-system-packages

python3 build_bbmodel.py                        # genera *.bbmodel + *_cubes.json para los modelos de ejemplo (Python)
python3 build_bbmodel.py recipes/mi_mob.json     # o generá un mob nuevo desde una receta JSON
python3 render_preview.py golem_boss_cubes.json  # genera golem_boss_preview_{iso,front,side}.png
```

Para crear o modificar un modelo tenés dos caminos: escribir una **receta JSON** (recomendado,
ver sección de arriba — no requiere tocar código) o, si preferís Python, editar las listas al
final de `build_bbmodel.py` (`demo_mob`, `golem_boss`, o agregar una nueva función) usando la
misma estructura de partes con `origin`/`cubes`/`children`. En ambos casos: volvé a correr los
scripts, revisá las imágenes de preview o la página web, y cuando el modelo se vea bien abrí el
`.bbmodel` resultante en Blockbench para texturizar y animar del todo.

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

- Validación formal de recetas (JSON Schema) para dar errores claros si un agente genera un
  `recipe.json` inválido, en vez de un traceback de Python.
- Interpolación con easing (no solo lineal) para animaciones más "pesadas"/orgánicas.
- Blending entre animaciones (ej. transición suave `idle` → `walk` en vez de corte seco).
- Texturas más elaboradas: patrones (rayas, manchas, pelaje), no solo color plano + ruido.
- Revisar orientación exacta del UV por cara en el visor (`applyBoxUV` en `index.html`) — puede haber
  alguna cara reflejada/rotada respecto al eje esperado; se corrige a ojo comparando contra Blockbench.
- Exportar directamente la config `.yml` de MythicMobs + ModelEngine junto al modelo.
