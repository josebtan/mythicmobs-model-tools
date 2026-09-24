# Formato de receta (recipe.json)

Una **receta** es el único archivo que hace falta escribir para generar un mob nuevo con esta
herramienta. No hace falta tocar Python ni JavaScript. Cualquier agente de IA (Claude, GPT, el que
sea) puede generar uno siguiendo este documento.

## Uso

**Opción A — desde el navegador, sin instalar nada:** abrí el visor
(https://josebtan.github.io/mythicmobs-model-tools/), abrí el panel "🧩 Crear mob (JSON)", pegá tu
receta y tocá "Generar / Previsualizar". Se ve en 3D al toque, con textura, y desde ahí podés:
descargar el `.bbmodel` y la textura directamente, o usar "💾 Guardar modelo actual…" para subirlo
a la biblioteca (login con Google) y compartirlo. Todo corre en el navegador — el generador de
texturas (box-UV) está portado a JavaScript en `recipe_builder.js`.

**Opción B — con Python (CLI):**

```bash
pip install Pillow numpy --break-system-packages
python3 build_bbmodel.py recipes/mi_mob.json
```

Esto genera, junto al script: `mi_mob.bbmodel` (abrí esto en Blockbench), `mi_mob_texture.png`
y `mi_mob_cubes.json` (para el visor web). Para que aparezca en el selector de modelos "de fábrica"
del visor (no la biblioteca), agregalo a `models.json` (ver abajo) y hacé commit.

Las dos opciones generan exactamente lo mismo — `recipe_builder.js` es un port directo de
`build_bbmodel.py`/`texture_gen.py`, no una reimplementación distinta.

## Unidades

1 bloque de Minecraft = 16 unidades. Todas las coordenadas (`from`, `to`, `origin`, tamaños de
cubo) están en esas unidades — un personaje "humano" típico mide unas 32 unidades de alto (2
bloques). El eje Y es "arriba". Convención de ejes: `+x`/`-x` = este/oeste, `+z` = frente
("south"), `-z` = atrás ("north").

## Estructura general

```json
{
  "name": "mi_mob",
  "parts": [ /* huesos raíz, ver abajo */ ],
  "animations": { /* opcional, ver abajo */ }
}
```

## `parts`: la jerarquía de huesos

Cada **parte** (hueso) es un objeto:

```json
{
  "name": "torso",
  "origin": [0, 10, 0],
  "rotation": [0, 0, 0],
  "cubes": [
    { "from": [-6, 10, -4], "to": [6, 26, 4], "color": "#8A7A68" }
  ],
  "children": [ /* huesos anidados, misma estructura, recursiva */ ]
}
```

- **`name`** (string, obligatorio): identificador único del hueso. Se usa para referenciarlo
  desde `animations`, así que elegí nombres claros (`torso`, `left_arm`, `head`, `tail`, etc.).
- **`origin`** (`[x,y,z]`, obligatorio): el **pivote** de este hueso. Todo lo que cuelga de este
  hueso (sus cubos y sus `children`) rota alrededor de este punto.
- **`rotation`** (`[x,y,z]` en grados, opcional, default `[0,0,0]`): rotación de este hueso **en
  la pose de reposo**. Por ejemplo, si querés que el mob esté parado encorvado por defecto (no
  animado), rotás el torso acá. Los hijos anidados heredan esta rotación automáticamente — no
  hace falta repetirla en cada hueso hijo.
- **`cubes`** (lista, opcional): los cuboides visibles de este hueso.
  - **`from`/`to`** (`[x,y,z]`, obligatorios): esquinas opuestas del cubo, en coordenadas
    absolutas (no relativas al `origin`).
  - **`color`** (hex string, opcional): color base del cubo en la textura generada. Si se omite,
    usa un color por defecto gris/marrón.
  - **`id`** (string, opcional): etiqueta libre para referenciar este cubo específico desde
    Python más adelante (por ejemplo, para pintar detalles extra en su textura, como los ojos del
    golem). No es necesario para un mob nuevo.
- **`children`** (lista, opcional): huesos anidados con esta misma estructura. Un brazo
  articulado, por ejemplo, se arma como una cadena: `hombro` → `children: [antebrazo]` →
  `children: [mano]`, cada uno con su propio `origin` en el punto donde debería doblarse.

### Reglas importantes

- **Un hueso que no debe seguir el movimiento de otro va en la lista raíz de `parts`, no
  anidado.** Ejemplo: las piernas de un mob bípedo casi siempre van en la raíz (no dentro del
  torso), porque tienen que quedarse plantadas en el piso aunque el torso se incline o se mueva.
  La cabeza y los brazos, en cambio, sí suelen ir anidados dentro del torso, para que lo
  acompañen si se inclina.
- **El `origin` de un hueso articulado (brazo, pierna, cola) va en la articulación, no en el
  centro geométrico del cubo.** Si el `origin` de una pierna queda en el medio del muslo en vez
  de en la cadera, al rotarla se va a "separar" visiblemente del cuerpo. Poné el `origin` donde
  ese hueso se dobla o se conecta con su padre.

## `animations` (opcional)

```json
{
  "idle": {
    "loop": true,
    "length": 2.0,
    "keyframes": {
      "torso": [
        { "time": 0.0, "position": [0, 0, 0] },
        { "time": 1.0, "position": [0, 0.35, 0] },
        { "time": 2.0, "position": [0, 0, 0] }
      ]
    }
  },
  "attack": {
    "loop": false,
    "length": 0.8,
    "keyframes": { "...": "..." }
  }
}
```

- Cada animación tiene `loop` (bool — `true` para idle/walk/run, `false` para acciones puntuales
  como un ataque o la muerte), `length` en segundos, y `keyframes` por nombre de hueso.
- **Los valores de `rotation`/`position` en un keyframe son DELTAS sobre la pose de reposo del
  hueso** (el `rotation`/`origin` que definiste en `parts`), no valores absolutos. Si un hueso
  tiene `"rotation": [22,0,0]` en `parts` (encorvado en reposo) y su animación de muerte le suma
  `"rotation": [70,0,8]` en el último keyframe, el resultado final es aproximadamente 92° de
  inclinación total — no 70°.
- Un hueso solo se mueve en los canales (`rotation`/`position`) que aparecen en sus keyframes; si
  no lo mencionás en una animación, se queda quieto en su pose de reposo.
- **Si un hueso raíz (no anidado) se mueve con `position` en una animación, y tiene otro hueso
  raíz "hermano" que debería quedarse pegado a él (como el torso y las piernas), dale a ambos
  exactamente el mismo delta de `position` en cada keyframe.** Si no, se ve como si el cuerpo se
  separara — es el bug más común al animar.

## `models.json`: publicar el mob en el visor

Para que tu mob aparezca en el selector del visor web (`index.html`), agregá una entrada a
`models.json` en la raíz del repo:

```json
{
  "id": "mi_mob",
  "label": "Mi Mob",
  "cubes": "mi_mob_cubes.json",
  "bbmodel": "mi_mob.bbmodel"
}
```

No hace falta tocar `index.html` — el visor lee esta lista dinámicamente.

## Ejemplos completos

`recipes/demo_mob.json` (humanoide simple, sin animaciones) y `recipes/golem_boss.json` (boss
articulado con textura, ojos pintados y 5 animaciones) son las recetas reales de los mobs de este
repo — generadas automáticamente desde sus definiciones en Python con `export_recipes.py`, así
que son 100% equivalentes a lo que hay hoy. Son el mejor punto de partida para copiar y adaptar.
