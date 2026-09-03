# SimLeón — mapa isométrico en pixel art de León, Gto.

Pipeline completo para dibujar León como un juego isométrico de los noventa, a partir de las
Photorealistic 3D Tiles de Google y Nano Banana Pro. Piloto: 15 cuadros (Centro – Zona Piel – Estadio).

```
grid.json              cuadrícula: origen, cámara (heading/pitch), cuadros (i, j)
.env                   GEMINI_API_KEY, MAPS_API_KEY   (no se incluye; créalo)
render/render.html     CesiumJS + cámara ortográfica inclinada
render/render.mjs      Playwright: renderiza cada cuadro a renders/sq_i_j.png (2048 px)
gen/prompt.txt         la instrucción de estilo (cada línea nació de una falla)
gen/pixelate.py        Nano Banana Pro + juez Gemini Flash + SSIM → pixels_pro/sq_i_j.png
gen/detect.py          detector: compara foto vs pixel art, devuelve cajas sospechosas → build/refine_queue.json
gen/refine.py          corrige UNA caja de un cuadro (solo cambian los píxeles de la caja); close-up 3D y fotos de referencia opcionales
gen/reports_to_queue.py convierte reportes del mapa (modo Reportar / db del artifact) en cola de correcciones
gen/fetch_refs.py      fotos reales de Google Places → data/refs/<poi>/ (requiere permitir lh3.googleusercontent.com)
build/geo.py           lon/lat ↔ píxel del mosaico
build/build_tiles.py   mosaico, paleta de 256 colores (k-means), pirámide DZI, tiles embebidos
build/build_site.py    visor OpenSeadragon (site/index.html) y versión de un solo archivo (artifact/)
build/build_story.py   la bitácora (site/story.html)
data/pois.json         lugares (coordenadas de Google Places + textos propios)
site/                  sitio estático listo para GitHub Pages / cualquier hosting
```

## Correr

```bash
npm install                          # cesium, playwright, openseadragon
pip install pillow numpy scikit-image scikit-learn
python3 -m http.server 8765 &        # sirve render.html y Cesium a Chromium
node render/render.mjs --grid grid.json --out renders
python3 gen/pixelate.py --in renders --out pixels_pro       # ~$0.27–0.54 por cuadro
python3 build/build_tiles.py --in pixels_pro --out site
python3 build/build_site.py && python3 build/build_story.py
```

Todos los pasos saltan lo que ya existe (`--force` para rehacer; `--only="i,j;i,j"` para cuadros puntuales).

## Expandir el mapa

1. Agrega cuadros a `grid.json` → `"squares": [{"i": 3, "j": 0, "u": 2100, "v": 0}, …]`
   con `u = i*W` y `v = j*Vh` (`Vh = W / sin(40°) = 1089 m`). Un cuadro = 700 m de ancho.
2. Corre los cuatro comandos de arriba: solo se renderizan y generan los cuadros nuevos.
3. `build_tiles.py` recalcula la paleta con todos los cuadros; el visor se regenera solo.

Costos de referencia del piloto: 15 cuadros, 51 min de render sin GPU, ~$5.75 USD en imágenes.

## Corregir errores

```bash
# 1. detectar automáticamente (≈ $0.002 por cuadro) y corregir (≈ $0.27 por caja)
python3 gen/detect.py                       # escribe build/refine_queue.json
python3 gen/refine.py --queue build/refine_queue.json
# 2. una caja a mano (coordenadas 0-2048 dentro del cuadro; el modo Reportar del mapa las da)
python3 gen/refine.py --sq=-1,0 --box 1560,270,2040,740 --closeup --poi expiatorio --note "iglesia blanca neogótica con agujas"
# 3. reportes hechos desde el mapa (pegados como JSON, o exportados de la db del artifact)
python3 gen/reports_to_queue.py reports.json && python3 gen/refine.py --queue build/refine_queue.json
# 4. reconstruir
python3 build/build_tiles.py && python3 build/build_site.py && python3 build/build_story.py
```

Cada corrección guarda el cuadro anterior en `pixels_pro/history/` y un registro en `pixels_pro/refine_log.jsonl`.

## Notas

- Chromium headless sin GPU: `--use-angle=swiftshader`. Con GPU real el render baja de ~3.5 min a segundos por cuadro.
- No pases un cuadro "ancla" como referencia de estilo: Nano Banana Pro lo copia como contenido.
- El juez (Gemini Flash) compara cada candidato con la foto; con `--min-judge 6.5 --max-n 4` reintenta hasta 4 veces.
- Atribución obligatoria: las imágenes 3D y los lugares son © Google (Map Tiles API, Places API).
