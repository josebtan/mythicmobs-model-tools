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
  modelo, textura real aplicada por UV, y botón de descarga del `.bbmodel`.

### Modelos incluidos

| Modelo | Archivo | Descripción |
|---|---|---|
| `demo_mob` | `demo_mob.bbmodel` | Humanoide básico de referencia (cabeza, torso, brazos, piernas). |
| `golem_boss` | `golem_boss.bbmodel` | Boss tipo tanque: torso ancho y musculoso, cabeza pequeña, hombreras, brazos largos y articulados (hombro→antebrazo→puño) que cuelgan por debajo de las piernas, piernas gruesas. |

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
- **Wireframe** — ve la malla de cubos.
- **Animación idle** — demo de balanceo simple (ver sección Animaciones abajo).
- **Auto-rotar** — gira el modelo solo, para verlo desde todos los ángulos sin tocar el mouse.
- Botón de descarga del `.bbmodel` del modelo activo.

El modelo se construye en el visor como una **jerarquía real de huesos** (un `THREE.Group` por
hueso, anidado igual que en `build_bbmodel.py`), no como una lista plana de cubos — es lo que
permite tanto el encorvado del golem como la animación de abajo.

## Animaciones: cómo funcionan (y qué falta)

El mecanismo ya está: cada hueso tiene una `rotation` propia que pivota alrededor de su `origin`, y
los hijos (ej. brazo colgando del hombro) heredan la rotación de sus padres automáticamente — así
armamos la postura encorvada del golem. **Animar es lo mismo, pero variando esa rotación en el
tiempo en vez de dejarla fija.**

En el visor esto ya corre en vivo: `playIdleAnimation()` en `index.html` mueve `boneGroups['torso']`
y `boneGroups['left_upper_arm']` / `right_upper_arm` cuadro a cuadro con una función seno — activalo
con el botón "Animación idle". Es una prueba de concepto escrita a mano, todavía no un sistema de
keyframes real. Lo que falta para tener animaciones "de verdad" (editables, exportables a
Blockbench/ModelEngine):

1. **Definir clips en Python**: en `build_bbmodel.py`, algo como
   `animations = {"idle": {"length": 1.0, "loop": True, "keyframes": {"torso": [(0, [0,0,0]), (0.5, [0,0,3]), (1.0, [0,0,0])]}}}`
   por hueso, con tiempo → rotación.
2. **Exportar al `.bbmodel`**: Blockbench tiene un campo `"animations"` en el JSON con ese mismo
   formato (channels de `rotation`/`position` por nombre de hueso) — así el clip también se ve y se
   edita en Blockbench, y ModelEngine lo puede reproducir en el server.
3. **Interpolar en el visor**: en vez de una función seno a mano, leer los keyframes del JSON e
   interpolar (lineal o con easing) entre ellos según el tiempo — reemplaza a `playIdleAnimation`.

## Por qué existe esto

Blockbench es una app de escritorio con interfaz gráfica; un asistente de IA sin pantalla no puede
operarla directamente. Este repo genera el mismo formato de archivo que usa Blockbench (JSON) y
agrega un loop de verificación visual (renders con matplotlib, y ahora el visor 3D interactivo) para
poder iterar sobre las proporciones y la ubicación de las piezas sin trabajar completamente a ciegas.

## Roadmap / ideas pendientes

- Sistema de keyframes real (ver sección Animaciones arriba) en vez de la demo por seno.
- Texturas más elaboradas: patrones (rayas, manchas, pelaje), no solo color plano + ruido.
- Revisar orientación exacta del UV por cara en el visor (`applyBoxUV` en `index.html`) — puede haber
  alguna cara reflejada/rotada respecto al eje esperado; se corrige a ojo comparando contra Blockbench.
- Exportar directamente la config `.yml` de MythicMobs + ModelEngine junto al modelo.
