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

Página estática con Three.js: rotar con el mouse, zoom con scroll, selector para cambiar entre
modelos y botón para descargar el `.bbmodel` del modelo activo.

## Por qué existe esto

Blockbench es una app de escritorio con interfaz gráfica; un asistente de IA sin pantalla no puede
operarla directamente. Este repo genera el mismo formato de archivo que usa Blockbench (JSON) y
agrega un loop de verificación visual (renders con matplotlib) para poder iterar sobre las
proporciones y la ubicación de las piezas sin trabajar completamente a ciegas.

## Roadmap / ideas pendientes

- Soporte para animaciones (keyframes) en `build_bbmodel.py`.
- Texturas más elaboradas: patrones (rayas, manchas, pelaje), no solo color plano + ruido.
- Revisar orientación exacta del UV por cara en el visor (`applyBoxUV` en `index.html`) — puede haber
  alguna cara reflejada/rotada respecto al eje esperado; se corrige a ojo comparando contra Blockbench.
- Exportar directamente la config `.yml` de MythicMobs + ModelEngine junto al modelo.
