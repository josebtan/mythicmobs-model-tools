# MythicMobs Model Tools

Herramientas para generar modelos `.bbmodel` (compatibles con [Blockbench](https://www.blockbench.net/)
y [ModelEngine](https://wiki.mythiccraft.io/modelengine)) de forma programática, más una vista previa
renderizada para validar proporciones antes de abrirlos en Blockbench.

## Contenido

- `build_bbmodel.py` — genera un archivo `.bbmodel` (JSON válido de Blockbench) a partir de una
  lista simple de cubos (`from`, `to`, `origin`).
- `render_preview.py` — renderiza esos mismos cubos con matplotlib en 3 ángulos (isométrico,
  frente, lateral) para chequear visualmente el modelo sin necesidad de abrir Blockbench.
- `cubes.json` — definición intermedia de los cubos, generada por `build_bbmodel.py` y consumida
  por `render_preview.py`.
- `demo_mob.bbmodel` — modelo de ejemplo (humanoide básico: cabeza, torso, brazos, piernas).

## Uso

```bash
pip install matplotlib numpy --break-system-packages

python3 build_bbmodel.py     # genera demo_mob.bbmodel + cubes.json
python3 render_preview.py    # genera preview_iso.png, preview_front.png, preview_side.png
```

Editá la lista `cubes_def` en `build_bbmodel.py` para definir tu propio mob, volvé a correr ambos
scripts, revisá las imágenes de preview, y cuando el modelo se vea bien abrí el `.bbmodel`
resultante en Blockbench para texturizar y animar.

## Por qué existe esto

Blockbench es una app de escritorio con interfaz gráfica; un asistente de IA sin pantalla no puede
operarla directamente. Este repo genera el mismo formato de archivo que usa Blockbench (JSON) y
agrega un loop de verificación visual (renders con matplotlib) para poder iterar sobre las
proporciones y la ubicación de las piezas sin trabajar completamente a ciegas.

## Roadmap / ideas pendientes

- Soporte para animaciones (keyframes) en `build_bbmodel.py`.
- Definición de bones/rotaciones jerárquicas en vez de un único `outliner` plano.
- Exportar directamente la config `.yml` de MythicMobs + ModelEngine junto al modelo.
