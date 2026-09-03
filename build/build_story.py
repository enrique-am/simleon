#!/usr/bin/env python3
"""Build the Spanish 'how it was made' story page (single self-contained HTML, images embedded)."""
import base64, io, json, math, re, sys
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, str(Path(__file__).parent)); import geo

ROOT = geo.ROOT; site = ROOT / 'site'; art = ROOT / 'artifact'
MAP_URL = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
HIRES_URL = sys.argv[2] if len(sys.argv) > 2 else ''

def img_uri(im, fmt='PNG', q=82, max_w=None):
    if max_w and im.width > max_w: im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS if fmt=='JPEG' else Image.BOX)
    buf = io.BytesIO()
    if fmt == 'JPEG': im.convert('RGB').save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
    else: im.convert('RGB').quantize(colors=256, dither=Image.Dither.NONE).save(buf, 'PNG', optimize=True)
    return f'data:image/{fmt.lower()};base64,' + base64.b64encode(buf.getvalue()).decode()

def load(p): return Image.open(p)
def pair(a, b, crop=None, w=560):
    if crop: a, b = a.crop(crop), b.crop(crop)
    return img_uri(a, 'JPEG', 80, w), img_uri(b, 'PNG', max_w=w)

# ---------- numbers from logs
gl = [json.loads(l) for l in open(ROOT / 'pixels_pro/gen_log.jsonl') if l.strip()]
final = {r['dst']: r for r in gl}                      # last record per square wins
gen_usd = sum(r['usd'] for r in gl)
gen_imgs = sum(r.get('n', 1) for r in gl)
judges = [r.get('judge') for r in final.values() if r.get('judge') is not None]
all_judges = [j for r in gl for j in r.get('judges', [])]
rlog = (ROOT / 'build/logs/render.log').read_text() if (ROOT / 'build/logs/render.log').exists() else ''
rtimes = [float(m) for m in re.findall(r'rendered .* in ([\d.]+)s', rlog)]
render_min = sum(rtimes) / 60
n_sq = len(final)
test_usd = 0.101*3 + 0.067 + 0.134  # exploratory generations before the pipeline settled (nano banana 2 tests + first pro test)
places_calls = len(json.load(open(ROOT / 'data/places_raw.json')))
meta = json.load(open(site / 'grid_meta.json')); pal = json.load(open(site / 'palette.json'))
area = n_sq * geo.W * (geo.W / geo.SINP) / 1e6
mosaic = load(site / 'mosaic.png')

# ---------- figures
hero = img_uri(mosaic, 'JPEG', 78, 1800)
r11, p11 = load(ROOT/'renders/sq_-1_1.png'), load(ROOT/'pixels_pro/sq_-1_1.png')
fig_cat_a, fig_cat_b = pair(r11, p11, crop=(1000, 900, 1700, 1600))
fig_full_a, fig_full_b = pair(r11, p11, w=640)
nb2 = load(ROOT/'pixels_test/sq_0_0_2k.png'); r00 = load(ROOT/'renders_test2/sq_0_0.png')
fig_nb2 = img_uri(nb2.crop((700,700,1300,1300)), 'PNG', max_w=480)
fig_nb2_src = img_uri(r00.crop((700,700,1300,1300)), 'JPEG', 80, 480)
fig_pro = img_uri(load(ROOT/'pixels_pro/sq_-1_1.png').crop((0,600,700,1300)), 'PNG', max_w=480)
fig_pro_src = img_uri(r11.crop((0,600,700,1300)), 'JPEG', 80, 480)
fig_orange = img_uri(load(ROOT/'pixels/candidates_old_-1_1.png').crop((0,600,700,1300)), 'PNG', max_w=480) if (ROOT/'pixels/candidates_old_-1_1.png').exists() else ''
fig_anchor = img_uri(load(ROOT/'build/logs/anchor_copy_-2_1.png'), 'PNG', max_w=480) if (ROOT/'build/logs/anchor_copy_-2_1.png').exists() else ''
fig_anchor_src = img_uri(load(ROOT/'renders/sq_-2_1.png'), 'JPEG', 78, 480)
fig_church = img_uri(load(ROOT/'build/logs/phantom_church_0_1.png'), 'PNG', max_w=480) if (ROOT/'build/logs/phantom_church_0_1.png').exists() else ''
fig_church_src = img_uri(load(ROOT/'renders/sq_0_1.png'), 'JPEG', 78, 480)
seam = Image.new('RGB', (1400, 700)); seam.paste(load(ROOT/'pixels_pro/sq_-2_1.png').crop((1348, 600, 2048, 1300)), (0, 0)); seam.paste(load(ROOT/'pixels_pro/sq_-1_1.png').crop((0, 600, 700, 1300)), (700, 0))
fig_seam = img_uri(seam, 'PNG', max_w=900)
fig_fix = img_uri(load(ROOT/'build/logs/fixes_before_after.png'), 'PNG', max_w=900) if (ROOT/'build/logs/fixes_before_after.png').exists() else ''
fig_expi = img_uri(load(ROOT/'build/logs/expiatorio_refine.png'), 'JPEG', 82, 1200) if (ROOT/'build/logs/expiatorio_refine.png').exists() else ''
rl = [json.loads(l) for l in open(ROOT/'pixels_pro/refine_log.jsonl')] if (ROOT/'pixels_pro/refine_log.jsonl').exists() else []
refine_usd = sum(r['usd'] for r in rl); n_fix = len(rl); n_fix_sq = len({tuple(r['sq']) for r in rl})
det = json.load(open(ROOT/'build/detect_report.json')) if (ROOT/'build/detect_report.json').exists() else {}
det_types = {}
for regs in det.values():
    for r in regs: det_types[r.get('type','?')] = det_types.get(r.get('type','?'), 0) + 1
det_total = sum(det_types.values())
backlog = len([j for j in json.load(open(ROOT/'build/refine_queue_backlog.json'))]) if (ROOT/'build/refine_queue_backlog.json').exists() else 0
TYPE_ES = {'invented_landmark':'templo o edificio inventado','wrong_architecture':'edificio real mal dibujado','wrong_size':'tamaño equivocado','wrong_ground':'pasto donde hay tierra o azoteas','missing_structure':'falta algo que sí existe'}
det_list = ', '.join(f"{v} {TYPE_ES.get(k,k)}" for k,v in sorted(det_types.items(), key=lambda kv:-kv[1]))
restyled = [json.loads(l) for l in open(ROOT/'pixels_pro/gen_log.jsonl') if '"style"' in l]
n_restyled = len(restyled); restyle_usd = sum(r['usd'] for r in restyled)
swatches = ''.join(f'<i style="background:rgb({r},{g},{b})"></i>' for r, g, b in sorted(pal, key=lambda c: (0.299*c[0]+0.587*c[1]+0.114*c[2])))
prompt_txt = (ROOT/'gen/prompt.txt').read_text().strip()

# grid diagram (SVG): squares with landmarks
pois = json.load(open(site/'pois.json'))
gw, gh = meta['cols'], meta['rows']
svg_sq = ''.join(f'<rect x="{(s["i"]-meta["i0"])*100}" y="{(meta["j0"]-s["j"])*100}" width="100" height="100" fill="{"var(--sq)" if s["has"] else "none"}" stroke="var(--ink-3)" stroke-dasharray="{"" if s["has"] else "4 3"}"/><text x="{(s["i"]-meta["i0"])*100+6}" y="{(meta["j0"]-s["j"])*100+14}" font-size="9" fill="var(--ink-3)" font-family="var(--mono)">{s["i"]},{s["j"]}</text>' for s in meta['squares'])
svg_pt = ''.join(f'<circle cx="{p["nx"]*gw*100:.1f}" cy="{p["ny"]*gh*100:.1f}" r="3" fill="var(--roof)"/><text x="{p["nx"]*gw*100+5:.1f}" y="{p["ny"]*gh*100+3:.1f}" font-size="7.5" fill="var(--ink)" font-family="var(--sans)">{p["name"].split(" (")[0][:26]}</text>' for p in pois if p['id'] in ('catedral','arco','expiatorio','estadio','forum','poliforum','central','plaza-piel','coecillo','guadalupe','panteon','doblado','san-juan','madero'))
grid_svg = f'<svg viewBox="-4 -4 {gw*100+8} {gh*100+8}" role="img" aria-label="Cuadrícula de {n_sq} cuadros sobre León">{svg_sq}{svg_pt}</svg>'

cost_rows = [
  ('Render 3D (Map Tiles API)', 'Dentro del crédito mensual gratuito de Google Maps Platform', '$0'),
  ('Lugares (Places API New, Text Search)', f'{places_calls} consultas', '$0 (crédito gratuito)'),
  ('Pruebas de estilo (Nano Banana 2 y Pro)', '5 imágenes', f'${test_usd:.2f}'),
  ('Pixel art final (Nano Banana Pro, 2K)', f'{gen_imgs} imágenes para {n_sq} cuadros', f'${gen_usd:.2f}'),
  ('Juez de fidelidad (Gemini Flash)', f'{gen_imgs} comparaciones', '≈ $0.05'),
  ('Cuadros desperdiciados por renders borrosos', '16 imágenes generadas sobre fotos a medio cargar', '$4.30'),
  ('Correcciones por región (Nano Banana Pro, 1K)', f'{n_fix} correcciones en {n_fix_sq} cuadros', f'${refine_usd:.2f}'),
  ('Cómputo', 'Chromium headless sin GPU, ~%.0f min de render' % render_min, '$0'),
]
total = test_usd + gen_usd + 0.05 + refine_usd + 4.30
cost_html = ''.join(f'<tr><td>{a}</td><td>{b}</td><td class="num">{c}</td></tr>' for a, b, c in cost_rows)

judge_hist = ''
if all_judges:
    bins = {k: 0 for k in range(0, 11)}
    for j in all_judges: bins[int(round(j))] += 1
    mx = max(bins.values())
    judge_hist = ''.join(f'<div class="bar" style="--h:{bins[k]/mx*100:.0f}%" title="{bins[k]} imágenes con {k}"><b>{bins[k] or ""}</b><span>{k}</span></div>' for k in range(2, 10))

html = f'''<title>Bitácora de SimLeón</title>
<meta name="description" content="Cómo se hizo el mapa isométrico en pixel art de León, Guanajuato: cámara, datos, IA, fallas y costos.">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{--bg:#eef0f4;--paper:#ffffff;--ink:#1b2130;--ink-2:#4a5364;--ink-3:#7a8497;--rule:#cfd5df;--roof:#c8553d;--gold:#b8862e;--grass:#3f8a33;--sky:#2f5f9e;--sq:#dfe5ee;--panel:#b9c3d3;--panel-2:#dbe2ec;--panel-3:#8d99ad;
  --sans:'IBM Plex Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;--mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;--pixel:'Press Start 2P','IBM Plex Mono',monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f1420;--paper:#171d2b;--ink:#e6e9f0;--ink-2:#b4bccb;--ink-3:#7f889a;--rule:#2b3445;--roof:#e0745c;--gold:#d9a441;--grass:#63b455;--sky:#7fa8de;--sq:#1f2738;--panel:#232c3d;--panel-2:#2e394d;--panel-3:#111621}}}}
:root[data-theme="dark"]{{--bg:#0f1420;--paper:#171d2b;--ink:#e6e9f0;--ink-2:#b4bccb;--ink-3:#7f889a;--rule:#2b3445;--roof:#e0745c;--gold:#d9a441;--grass:#63b455;--sky:#7fa8de;--sq:#1f2738;--panel:#232c3d;--panel-2:#2e394d;--panel-3:#111621}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:17px;line-height:1.6}}
a{{color:var(--sky)}} img{{max-width:100%;display:block}}
.hero{{position:relative;background:#0f1420}} .hero img{{width:100%;max-height:70vh;object-fit:cover;image-rendering:auto}}
.hero .cap{{position:absolute;left:0;right:0;bottom:0;padding:28px clamp(16px,5vw,64px) 22px;background:linear-gradient(transparent,rgba(15,20,32,.85));color:#fff}}
.hero h1{{margin:0 0 6px;font-family:var(--pixel);font-size:clamp(18px,3.4vw,34px);line-height:1.3;text-shadow:2px 2px 0 #000}} .hero h1 span{{color:#e0745c}}
.hero p{{margin:0;font-size:15px;opacity:.9}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 clamp(16px,4vw,40px) 80px}}
article{{max-width:68ch;margin:0 auto}}
.eyebrow{{font-family:var(--pixel);font-size:10px;letter-spacing:.5px;color:var(--roof);text-transform:uppercase;margin:64px 0 10px}}
h2{{margin:0 0 14px;font-size:30px;line-height:1.2;text-wrap:balance;font-weight:600}} h3{{font-size:20px;margin:28px 0 8px;font-weight:600}}
p{{margin:0 0 18px}} ul{{padding-left:22px}} li{{margin-bottom:6px}}
.lede{{font-size:20px;color:var(--ink-2)}}
.kpis{{display:grid;grid-template-columns:repeat(6,1fr);gap:2px;margin:40px auto;max-width:900px;background:var(--panel-3);border:2px solid var(--panel-3)}}
.kpi{{background:var(--paper);padding:14px 16px}} .kpi b{{display:block;font-family:var(--mono);font-size:22px;white-space:nowrap;font-weight:500;font-variant-numeric:tabular-nums}} .kpi span{{font-size:12.5px;color:var(--ink-3);text-transform:uppercase;letter-spacing:.4px}}
figure{{margin:28px 0}} figure.wide{{max-width:1000px;margin-left:calc(50% - min(500px,50vw - clamp(16px,4vw,40px)));width:min(1000px,calc(100vw - 2*clamp(16px,4vw,40px)))}}
figcaption{{font-size:13.5px;color:var(--ink-3);margin-top:8px;line-height:1.45}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:6px}} .pair img{{width:100%;border:1px solid var(--rule)}} .pair .px{{image-rendering:pixelated}}
.pair small{{display:block;font-family:var(--mono);font-size:11px;color:var(--ink-3);margin-top:4px}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}
pre{{background:var(--paper);border:1px solid var(--rule);padding:16px;font-family:var(--mono);font-size:12.5px;line-height:1.5;white-space:pre-wrap;overflow-x:auto;color:var(--ink-2)}}
code{{font-family:var(--mono);font-size:.92em;background:var(--paper);border:1px solid var(--rule);padding:0 4px}}
table{{width:100%;border-collapse:collapse;font-size:15px}} td,th{{padding:9px 8px;border-bottom:1px solid var(--rule);text-align:left;vertical-align:top}} th{{font-size:12px;text-transform:uppercase;letter-spacing:.4px;color:var(--ink-3)}} td.num{{font-family:var(--mono);text-align:right;white-space:nowrap}}
.sw{{display:grid;grid-template-columns:repeat(32,1fr);gap:1px;border:1px solid var(--rule)}} .sw i{{display:block;aspect-ratio:1}}
.gridfig svg{{width:100%;height:auto;background:var(--paper);border:1px solid var(--rule)}}
.hist{{display:flex;align-items:flex-end;gap:6px;height:120px;padding:8px 0 22px;border-bottom:1px solid var(--rule);position:relative}} .bar{{flex:1;position:relative;height:100%;display:flex;align-items:flex-end}} .bar::after{{content:"";display:block;width:100%;height:var(--h);background:var(--roof);min-height:1px}} .bar span{{position:absolute;bottom:-20px;left:0;right:0;text-align:center;font-family:var(--mono);font-size:11px;color:var(--ink-3)}} .bar b{{position:absolute;bottom:calc(var(--h) + 3px);left:0;right:0;text-align:center;font-family:var(--mono);font-size:11px;font-weight:500}}
.cta{{display:inline-flex;align-items:center;gap:8px;margin:8px 0 0;padding:12px 18px;background:var(--panel-2);border:2px solid;border-color:#fff var(--panel-3) var(--panel-3) #fff;color:var(--ink);text-decoration:none;font-weight:600;font-family:var(--pixel);font-size:11px}}
.note{{border-left:4px solid var(--gold);padding:10px 16px;background:var(--paper);margin:20px 0;font-size:15.5px}}
footer{{margin-top:70px;padding-top:20px;border-top:1px solid var(--rule);font-size:13.5px;color:var(--ink-3)}}
@media (max-width:900px){{.kpis{{grid-template-columns:repeat(3,1fr)}}}}
@media (max-width:640px){{.kpis{{grid-template-columns:repeat(2,1fr)}} .pair,.grid3{{grid-template-columns:1fr}} body{{font-size:16px}} h2{{font-size:25px}}}}
</style>

<div class="hero"><img src="{hero}" alt="Mosaico completo del mapa piloto de León en pixel art isométrico">
<div class="cap"><h1>Sim<span>León</span>: bitácora</h1><p>Cómo convertimos {n_sq} cuadros de la ciudad real en un mapa isométrico de pixel art — cámara, datos, IA, fallas, correcciones y lo que costó.</p></div></div>

<div class="wrap">
<div class="kpis">
 <div class="kpi"><b>{n_sq}</b><span>cuadros de 700 m</span></div>
 <div class="kpi"><b>{area:.1f} km²</b><span>de ciudad</span></div>
 <div class="kpi"><b>{meta['cols']*meta['grid']}×{meta['rows']*meta['grid']}</b><span>píxeles del mosaico</span></div>
 <div class="kpi"><b>{len(pal)}</b><span>colores, como en VGA</span></div>
 <div class="kpi"><b>${total:.2f}</b><span>USD en imágenes IA</span></div>
 <div class="kpi"><b>{render_min:.0f} min</b><span>de render 3D</span></div>
</div>

<article>
<p class="lede">De niño jugué muchísimos videojuegos, y mis favoritos eran los de construir mundos: SimCity 2000, RollerCoaster Tycoon. Como millennial de los de en medio, ya cerca de la mediana edad, soy presa fácil de la nostalgia de esos juegos de finales de los noventa. Mirando la ciudad desde arriba no pude evitar imaginarla dibujada así. Entonces, la idea: hacer un mapa gigante de León, Guanajuato, en pixel art isométrico.</p>
<p><a class="cta" href="{MAP_URL}">▶ Abrir el mapa</a> {'<a class="cta" href="'+HIRES_URL+'">▶ Alta resolución (2.93 px/m)</a>' if HIRES_URL else ''}</p>

<div class="eyebrow">01 · Los referentes</div>
<h2>Dos proyectos que ya lo hicieron con otras ciudades</h2>
<p>La idea no es original y eso es lo bueno: hay mapa de ruta. <a href="https://sheets.works/data-viz/london/story" rel="noopener">London, Drawn</a> dibujó 216 km² de Londres a partir de los modelos 3D de Google y un modelo de imágenes al que le pasaban una foto y un cuadro ya aprobado como referencia; en total unas 37 mil teselas y unas 17 libras en generación. <a href="https://cannoneyed.com/projects/isometric-nyc" rel="noopener">Isometric NYC</a> hizo Nueva York en pixel art puro, con un modelo <em>fine-tuned</em>, relleno enmascarado entre cuadrantes para que las costuras no se noten, y muchas horas de corrección a mano de agua y árboles. Los dos coinciden en una lección: el modelo de imagen no se puede supervisar a sí mismo, así que hay que construir el control de calidad alrededor.</p>
<p>SimLeón toma la cámara y la cuadrícula de Londres, el estilo de Nueva York, y agrega una cosa que ninguno tenía: un <em>juez</em> automático que compara cada cuadro contra la foto original antes de aceptarlo.</p>

<div class="eyebrow">02 · La cámara</div>
<h2>Una cámara ortográfica flotando sobre Google Earth</h2>
<p>La materia prima son las <strong>Photorealistic 3D Tiles</strong> de Google Maps Platform: el mismo modelo 3D texturizado que se ve en Google Earth. León tiene cobertura completa. Se cargan en <a href="https://cesium.com/platform/cesiumjs/" rel="noopener">CesiumJS</a> dentro de un Chromium sin cabeza, se apaga el globo, la atmósfera y la iluminación extra (las texturas ya vienen iluminadas) y se sustituye la cámara normal por una <strong>ortográfica</strong>: sin perspectiva, como en los juegos isométricos.</p>
<ul>
<li><strong>Inclinación:</strong> 40° respecto al suelo. Londres usó 45°; con 40° se ve un poco más de fachada, que es donde vive el encanto de SimCity.</li>
<li><strong>Giro:</strong> 30° al oeste del norte. La retícula del Centro Histórico queda en diagonal, como los rombos de las manzanas del juego. La brújula del mapa lo indica.</li>
<li><strong>Escala:</strong> cada cuadro cubre 700 m de ancho y se renderiza a 2048 px: 2.93 px por metro, igual que Londres. Por la inclinación, un cuadro abarca 1 089 m de suelo en vertical.</li>
<li><strong>Altura:</strong> 4 km de distancia nominal, aunque en ortográfica la distancia no cambia el tamaño; solo importa el ancho del frustum.</li>
</ul>
<p>Como la proyección es lineal y todos los cuadros comparten exactamente la misma dirección de cámara, los renders embonan al píxel sin costuras: basta desplazar el punto de mira 700 m a la derecha o 1 089 m hacia adelante en el suelo. La GPU brilla por su ausencia (SwiftShader, render por software), así que cada cuadro tardó entre 3 y 4 minutos cargando teselas y dibujando: {render_min:.0f} minutos en total para el piloto.</p>

<figure class="wide"><div class="pair"><div><img src="{fig_full_a}" alt="Render 3D del cuadro de la Catedral"><small>Render ortográfico · cuadro (−1, 1) · Catedral y Plaza Principal</small></div><div><img class="px" src="{fig_full_b}" alt="Mismo cuadro en pixel art"><small>El mismo cuadro después de Nano Banana Pro</small></div></div>
<figcaption>Entrada y salida de un cuadro completo (700 m de ancho). La geometría —calles, manzanas, alturas— se conserva; la textura fotográfica se convierte en sprites.</figcaption></figure>

<div class="eyebrow">03 · La cuadrícula</div>
<h2>Del piloto al corazón de la ciudad</h2>
<p>Empezamos chico para poder expandir. El piloto fueron 15 cuadros (5 × 3) del Centro al Estadio: la Catedral y la Plaza Principal, la calle Madero, el Templo Expiatorio, el Arco de la Calzada, el Barrio Arriba y el Coecillo, la Zona Piel y la Central de Autobuses, el Estadio León, el Forum Cultural y el Poliforum. Con el pipeline probado, la segunda pasada agregó 62 cuadros más: hoy son {meta['cols']} columnas por {meta['rows']} filas, {n_sq} cuadros y {area:.1f} km², de la Plaza Mayor y el Campestre al norte hasta San Miguel y el Blvd. Torres Landa al sur, de Chapalita y la Universidad De La Salle al poniente hasta las colonias más allá del Poliforum al oriente. Cada cuadro se identifica por su columna y fila (tecla <code>Q</code> en el mapa). Agregar el resto de la mancha urbana es agregar renglones a una lista JSON y dejar correr el pipeline otra noche.</p>
<figure class="gridfig">{grid_svg}<figcaption>Los {n_sq} cuadros actuales, en coordenadas de pantalla (la cámara ya está girada 30°). Los puntos rojos son algunos de los {len(pois)} lugares marcados en el mapa; sus coordenadas vienen de Google Places.</figcaption></figure>

<div class="eyebrow">04 · El pixel art</div>
<h2>Pedirle a una IA que trace, no que invente</h2>
<p>Cada render pasa a un modelo de imagen con una instrucción larga que dice, en esencia: <em>conviértelo en una captura de un juego isométrico de los noventa, pero calca exactamente lo que ves</em>. Probamos dos modelos de Google. <strong>Nano Banana 2</strong> (gemini-3.1-flash-image, unos 10 centavos por imagen) producía una ilustración plana bonita, pero no del todo pixel art, y con frecuencia inventaba cosas. <strong>Nano Banana Pro</strong> (gemini-3-pro-image, 13 centavos) entendió mucho mejor la geometría y el estilo, así que el piloto se hizo con él a 2048 px.</p>
<figure class="wide"><div class="pair"><div><img class="px" src="{fig_nb2}" alt="Detalle generado con Nano Banana 2"><small>Nano Banana 2 · ilustración cel-shaded, no tan pixel</small></div><div><img class="px" src="{fig_pro}" alt="Detalle generado con Nano Banana Pro"><small>Nano Banana Pro · sprites con píxel visible y fidelidad alta</small></div></div>
<figcaption>Los dos modelos sobre zonas del centro. Pro conserva la cancha, la nave blanca y la torre del templo exactamente donde están en la foto.</figcaption></figure>

<h3>La instrucción</h3>
<p>Este es el prompt completo que recibe cada cuadro. Casi todas las líneas nacieron de una falla concreta, que se cuenta abajo.</p>
<pre>{prompt_txt}</pre>

<h3>Lo que salió mal</h3>
<p><strong>El ancla que copiaba.</strong> Londres le pasa al modelo un cuadro ya aprobado como referencia de estilo. Lo intentamos y Nano Banana Pro hizo algo peor que ignorarlo: dibujó la Catedral y los edificios de la referencia encima de un barrio que no los tiene. Se eliminó la referencia; la coherencia entre cuadros se logra con el prompt y con una paleta compartida al final.</p>
<figure class="wide"><div class="pair"><div><img src="{fig_anchor_src}" alt="Render del cuadro (−2, 1)"><small>Foto del cuadro (−2, 1): Barrio Arriba, sin catedral</small></div><div><img class="px" src="{fig_anchor}" alt="Generación con la referencia de estilo, con la catedral copiada"><small>Con la referencia adjunta: apareció la Catedral del cuadro vecino</small></div></div><figcaption>El cuadro de referencia se convirtió en contenido.</figcaption></figure>
<p><strong>Los templos fantasma.</strong> El primer prompt mencionaba "iglesias en piedra ocre con cúpulas". Resultado: el modelo ponía una iglesia dorada en cada cuadro, hubiera o no. También convertía terrenos baldíos en parques verdes en una ciudad semiárida, y en una versión temprana levantó un conjunto habitacional naranja de ocho pisos en una manzana de casas de un piso. Cada una de esas fallas es hoy una línea del prompt ("NEVER add a church…", "bare dirt lots stay tan").</p>
<figure class="wide"><div class="grid3"><div><img class="px" src="{fig_orange}" alt="Conjunto habitacional inventado"><small>Torres inventadas (Nano Banana 2)</small></div><div><img src="{fig_church_src}" alt="Render del cuadro (0, 1)"><small>Cuadro (0, 1): el Malecón, sin templos</small></div><div><img class="px" src="{fig_church}" alt="Generación con templos fantasma"><small>Dos templos que no existen</small></div></div><figcaption>Alucinaciones típicas. Ninguna se detecta con métricas simples de similitud; hace falta alguien que mire.</figcaption></figure>

<p><strong>Los renders borrosos.</strong> En la expansión corrimos dos renderizadores en paralelo junto con las correcciones, en una máquina de dos núcleos sin GPU. Con la CPU saturada, 21 cuadros llegaron al tiempo límite con las teselas 3D a medio cargar: fotos borrosas que el pipeline mandó felizmente a dibujar. Nano Banana Pro alucinó una ciudad entera sobre cada mancha gris. Costó unos 4 dólares descubrirlo. Hoy el renderizador se niega a guardar un cuadro cuyas teselas no terminaron de cargar, y el generador mide la nitidez de cada foto antes de gastar un centavo en ella.</p>

<h3>El juez</h3>
<p>Ese alguien es otro modelo. Cada candidato se envía junto con la foto original a Gemini Flash con una sola pregunta: <em>del 0 al 10, ¿qué tan fielmente conserva calles, manzanas, huellas y alturas? Ignora color y estilo; castiga fuerte lo inventado.</em> Devuelve la nota y una lista de problemas. Se generan dos candidatos por cuadro; si el mejor no alcanza 6.5 se generan hasta dos más, y gana la nota más alta (con una similitud estructural SSIM como desempate). Costó centavos y atrapó las torres naranjas y varios templos fantasma sin que nadie los viera.</p>
<figure><div class="hist">{judge_hist}</div><figcaption>Notas del juez para las {len(all_judges)} imágenes generadas en el piloto. Promedio de los cuadros finales: {sum(judges)/len(judges) if judges else 0:.1f}. Nada llega a 10: el modelo siempre simplifica azoteas y arbolado.</figcaption></figure>

<div class="eyebrow">05 · Corregir sin romper</div>
<h2>Arreglar una iglesia sin volver a dibujar la ciudad</h2>
<p>Aun con el juez, un cuadro "aprobado" puede traer un templo que no existe o una iglesia real dibujada con la arquitectura equivocada: el Templo Expiatorio, blanco y neogótico, salió como una catedral barroca dorada con cúpulas. Volver a generar el cuadro entero es caro y arriesgado —el resto del cuadro, que estaba bien, cambiaría también—. La solución es corregir por regiones, con tres restricciones duras:</p>
<ul>
<li><strong>Solo cambia la caja.</strong> Se marca un rectángulo sobre el error. El modelo recibe el dibujo actual, la foto del mismo recorte y una máscara; pero da igual lo que devuelva fuera de la máscara: el código pega de vuelta únicamente los píxeles de adentro. Todo lo demás queda idéntico, píxel por píxel.</li>
<li><strong>Referencia de la geometría real.</strong> Para edificios mal dibujados se renderiza un <em>close-up</em> del mismo modelo 3D de Google con la misma cámara pero un encuadre de 120–250 m: una vista nítida de las torres, cúpulas y colores verdaderos. Si hay fotos reales del edificio en <code>data/refs/</code>, también se adjuntan.</li>
<li><strong>El mismo juez, con la pregunta invertida.</strong> Cada candidato se evalúa solo dentro de la máscara: ¿ya coincide con la foto y quedó resuelto el problema reportado? Gana la mejor de dos.</li>
</ul>
<figure class="wide"><img src="{fig_expi}" alt="Foto, close-up 3D y resultado del Templo Expiatorio"><figcaption>Templo Expiatorio: la foto aérea, el close-up 3D que sirve de referencia y el resultado corregido, ya con sus agujas blancas. Costo: dos imágenes, $0.27.</figcaption></figure>
<h3>Quién encuentra los errores</h3>
<p>Dos caminos alimentan la misma cola de trabajo. El <strong>detector</strong> le pide a Gemini Flash que compare cada cuadro con su foto y devuelva cajas con lo que no cuadra —templo inventado, arquitectura equivocada, tamaño, pasto donde hay tierra, algo que falta— con severidad del 1 al 5. En la pasada sobre los 62 cuadros nuevos encontró {det_total} regiones: {det_list}. Y en el mapa, la tecla <code>R</code> abre el modo <strong>Reportar</strong>: se dibuja un rectángulo, se elige el tipo de error, se escribe qué hay realmente ahí, y el reporte queda guardado junto al mapa para la siguiente pasada de corrección. Los reportes se ven como cajas amarillas; cuando se corrigen, cambian a verde.</p>
<figure class="wide"><img class="px" src="{fig_fix}" alt="Cuatro correcciones: foto, antes y después"><figcaption>Cuatro correcciones automáticas del detector (foto · antes · después): el Santuario de Guadalupe recupera sus cúpulas azules y su tamaño real; un baldío deja de ser parque; una catedral y una torre inventadas desaparecen. Fuera de cada caja no cambió un solo píxel.</figcaption></figure>
<p>En total, {n_fix} correcciones en {n_fix_sq} cuadros por ${refine_usd:.2f}; quedan en la cola {backlog} regiones de severidad baja para una siguiente pasada. El costo de corregir una región es un tercio de rehacer el cuadro, y el riesgo de romper lo que estaba bien es cero.</p>

<div class="eyebrow">06 · La paleta</div>
<h2>{len(pal)} colores, como mandaba la tarjeta VGA</h2>
<p>Los cuadros salen del modelo con miles de colores y con ligeras variaciones de tono entre uno y otro. Para que el mosaico se sienta como <em>un solo</em> juego, se reduce todo a una paleta única de {len(pal)} colores calculada con k-means sobre una muestra de todos los cuadros, sin tramado (dithering). SimCity 2000 corría en 256 colores; aquí es a la vez guiño y pegamento. El mosaico se dibuja a {meta['grid']} px por cuadro ({meta['grid']/geo.W:.2f} px/m) y el visor lo amplía con interpolación desactivada para que el píxel se vea píxel.</p>
<h3>El mismo juego en todos los cuadros</h3>
<p>Aun con el mismo prompt, Nano Banana Pro tiene dos "modos": a veces entrega pixel art denso —azoteas con textura, ventanitas, contornos duros— y a veces una ilustración vectorial plana y pálida. Puestos uno junto a otro, el salto en la costura se nota de inmediato. La solución tiene tres partes. Primero, una <strong>auditoría de estilo</strong>: el mismo juez califica dos recortes de cada cuadro del 0 al 10 según qué tan "pixel" se ven, sin mirar el contenido; los que sacan 5 o menos se regeneran. Segundo, esa nota entra en la selección de candidatos: un cuadro fiel pero plano ya no gana. Tercero, antes de cortar las teselas, cada cuadro se <strong>normaliza en color</strong> —su brillo y contraste por canal se acercan un 60% a la mediana de todo el mapa—, así las costuras dejan de ser saltos de tono. En esta pasada se regeneraron {n_restyled} cuadros por ${restyle_usd:.2f}.</p>
<figure><div class="sw">{swatches}</div><figcaption>La paleta compartida, ordenada por luminosidad: terracota de azoteas, ocres de cantera, grises de asfalto y lámina, los verdes de las jardineras.</figcaption></figure>
<figure class="wide"><img class="px" src="{fig_seam}" alt="Costura entre dos cuadros generados por separado"><figcaption>Costura entre los cuadros (−2, 1) y (−1, 1), generados por separado. La geometría embona porque la cámara es idéntica; el estilo embona por el prompt y la paleta.</figcaption></figure>

<div class="eyebrow">07 · Los lugares</div>
<h2>Puntos de interés con coordenadas reales</h2>
<p>Los {len(pois)} pines del mapa vienen de la <strong>Places API</strong> de Google: nombre oficial, coordenadas y calificación. Para ponerlos sobre el dibujo se invierte la matemática de la cámara: latitud y longitud pasan a metros en el plano tangente, se giran 30°, se aplanan por el seno de 40° y se convierten a píxeles del mosaico. El error típico es de unos 20–40 m (la coordenada de Google suele ser la entrada del lugar, no su centro), suficiente para caer sobre el edificio correcto. Los textos de cada lugar los escribimos nosotros.</p>

<div class="eyebrow">08 · Cuentas</div>
<h2>Lo que costó</h2>
<table><thead><tr><th>Concepto</th><th>Detalle</th><th class="num">USD</th></tr></thead><tbody>{cost_html}<tr><td colspan="2"><strong>Total pagado en IA</strong></td><td class="num"><strong>${total:.2f}</strong></td></tr></tbody></table>
<p class="note">Extrapolando: a unos ${gen_usd/n_sq:.2f} por cuadro generado más ${refine_usd/n_sq:.2f} de correcciones, la mancha urbana completa de León —unos 300 km², cerca de 400 cuadros— costaría alrededor de ${(gen_usd+refine_usd)/n_sq*400:.0f} USD en imágenes y unas 20 horas de render sin GPU. Es un fin de semana, no un presupuesto.</p>

<div class="eyebrow">09 · Lo que sigue</div>
<h2>Expandir</h2>
<ul>
<li><strong>Más cuadros.</strong> La cuadrícula vive en <code>grid.json</code>; los scripts saltan lo que ya existe. Del piloto de 15 cuadros pasamos a {n_sq}; lo que falta es el resto de la mancha urbana hasta el periférico.</li>
<li><strong>Costuras de estilo.</strong> Hoy cada cuadro se genera solo. El siguiente paso es el truco de Isometric NYC: generar con un borde del vecino ya dibujado como contexto enmascarado, sin que el modelo lo copie como contenido.</li>
<li><strong>Corrección con la gente.</strong> El modo Reportar ya existe; falta correr la cola de reportes de forma periódica y mostrar el historial de cada cuadro.</li>
<li><strong>Más lugares.</strong> Fotos, historias de barrio y las tiendas de la Zona Piel.</li>
</ul>
<p><a class="cta" href="{MAP_URL}">▶ Abrir el mapa</a> {'<a class="cta" href="'+HIRES_URL+'">▶ Alta resolución (2.93 px/m)</a>' if HIRES_URL else ''}</p>

<footer>
<p>Imágenes 3D y datos de lugares © Google (Map Tiles API, Places API). Pixel art generado con Nano Banana Pro y juzgado con Gemini Flash (Google). Render con CesiumJS y Playwright; visor con OpenSeadragon. Todo el pipeline —renderer, prompts, juez, paleta, visor y este texto— lo escribió y ejecutó Claude en una sesión de Cowork a partir de la idea, las llaves de API y las respuestas de Enrique. Inspirado en <a href="https://sheets.works/data-viz/london/story">London, Drawn</a> y <a href="https://cannoneyed.com/projects/isometric-nyc">Isometric NYC</a>. León, Guanajuato · septiembre de 2026.</p>
</footer>
</article>
</div>
'''
art.mkdir(exist_ok=True)
(art / 'simleon-bitacora.html').write_text(html)
(site / 'story.html').write_text('<!doctype html>\n<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n' + html + '\n</body></html>\n')
print('story', (art/'simleon-bitacora.html').stat().st_size/1e6, 'MB; total AI usd', round(total,2), 'render min', round(render_min))
