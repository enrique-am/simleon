#!/usr/bin/env python3
"""Fill the viewer template twice: a self-hosted site (DZI tiles) and a single-file artifact (embedded tiles).
usage: build_site.py [--story-url URL] [--map-url URL]"""
import argparse, json, math, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import geo

ap = argparse.ArgumentParser(); ap.add_argument('--story-url', default='story.html'); ap.add_argument('--artifact-story-url', default='#'); ap.add_argument('--hires-url', default='')
a = ap.parse_args()
ROOT = geo.ROOT; site = ROOT / 'site'; art = ROOT / 'artifact'; art.mkdir(exist_ok=True)
tpl = (ROOT / 'site_src/viewer.template.html').read_text()
pois = json.load(open(site / 'pois.json')); meta = json.load(open(site / 'grid_meta.json'))
emb = json.load(open(site / 'embedded_tiles.json'))
mosaic_w, mosaic_h = meta['cols'] * meta['grid'], meta['rows'] * meta['grid']
scale = meta['grid'] / geo.PX
geo_js = {'scale': scale, 'W': geo.W, 'PX': geo.PX, 'left': geo.I0 * geo.W - geo.W / 2, 'top': geo.J0 * geo.W + geo.W / 2, 'dx': geo.CAL['dx'], 'dy': geo.CAL['dy'],
          'sinp': geo.SINP, 'H': geo.H, 'lon0': geo.LON0, 'lat0': geo.LAT0, 'mlon': geo.M_PER_DEG_LON, 'mlat': geo.M_PER_DEG_LAT}
n_sq = sum(1 for s in meta['squares'] if s['has'])
area = round(n_sq * geo.W * (geo.W / geo.SINP) / 1e6, 1)
common = {
  '{{COMPASS_ROT}}': str(-geo.G['heading']),   # screen-up = camera heading; north sits -heading degrees clockwise from up
  '{{SQUARES}}': str(n_sq), '{{AREA}}': str(area), '{{PX_M}}': f'{meta["grid"]/geo.W:.2f}',
  '{{M_PER_PX}}': f'{geo.W/meta["grid"]:.5f}', '{{FLY_ZOOM}}': '4', '{{OPEN_EXTRA}}': '',
  '{{NAV_AR}}': f'{meta["cols"]}/{meta["rows"]}', '{{SUBTITLE}}': f'León, Guanajuato · pixel art isométrico · {n_sq} cuadros · {area} km²',
}
REPORT_DB_INIT = '''const dbReady = new Promise(res=>{ const t0=Date.now(); const tick=()=>{ if(window.claude&&window.claude.use){ window.claude.use('db').then(res,()=>res(null)); } else if(Date.now()-t0>10000) res(null); else setTimeout(tick,200); }; tick(); });
dbReady.then(db=>{ if(!db){ btnReport.title='Reportes: copia al portapapeles'; return; } try{ db.collection('reports').onSnapshot(snap=>{ snap.docs.forEach(d=>{ if(d.exists) drawReport(d.id, d.data()); }); }, err=>{}); }catch(e){} });
function fallbackReport(rep){ const txt=JSON.stringify(rep); (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(()=>showToast('Reporte copiado al portapapeles: pégalo en el chat para corregirlo.',6000),()=>showToast('Reporte: '+txt,9000)); drawReport('local'+rep.ts, rep); }'''
REPORT_DB_SUBMIT = '''const db = await dbReady; if(db){ try{ const ref = await db.collection('reports').add(rep); drawReport(ref.id, rep); showToast('¡Gracias! Reporte guardado; se corrige en la siguiente pasada.',5000); }catch(err){ showToast('No se pudo guardar ('+(err&&err.code||err)+'); copiando al portapapeles.'); fallbackReport(rep); } } else fallbackReport(rep);'''
REPORT_LOCAL_INIT = '''function fallbackReport(rep){ const txt=JSON.stringify(rep); (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(()=>showToast('Reporte copiado al portapapeles: pégalo en build/reports.json o en el chat.',6000),()=>showToast('Reporte: '+txt,9000)); drawReport('local'+rep.ts, rep); }'''
REPORT_LOCAL_SUBMIT = '''fallbackReport(rep);'''
def fill(t, m):
  for k, v in m.items(): t = t.replace(k, v)
  return t

# ---- hosted
data = f"const POIS={json.dumps(pois, ensure_ascii=False)};\nconst META={{width:{mosaic_w},height:{mosaic_h}}};\nconst GRID={json.dumps(meta)};\nconst GEO={json.dumps(geo_js)};\nconst TILE_SOURCE='tiles.dzi';"
hosted = fill(tpl, {**common, '{{STORY_URL}}': a.story_url, '{{OSD_SCRIPT}}': '<script src="vendor/openseadragon.min.js"></script>', '{{DATA_INLINE}}': data, '{{MAX_ZOOM_PX}}': '6', '{{REPORT_INIT}}': REPORT_LOCAL_INIT, '{{REPORT_SUBMIT}}': REPORT_LOCAL_SUBMIT, '{{HIRES_LINK}}': ''})
(site / 'index.html').write_text('<!doctype html>\n<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n' + hosted + '\n</body></html>\n')
(site / 'vendor').mkdir(exist_ok=True); shutil.copy(ROOT / 'node_modules/openseadragon/build/openseadragon/openseadragon.min.js', site / 'vendor/openseadragon.min.js')

# ---- artifact (single file, tiles embedded as data URIs)
escale = emb['tileSize'] / geo.PX
pois_e = [{**p, 'x': round(p['x'] * emb['width'] / mosaic_w), 'y': round(p['y'] * emb['height'] / mosaic_h)} for p in pois]
geo_e = {**geo_js, 'scale': escale}
data_e = (f"const POIS={json.dumps(pois_e, ensure_ascii=False)};\nconst META={{width:{emb['width']},height:{emb['height']}}};\nconst GRID={json.dumps(meta)};\nconst GEO={json.dumps(geo_e)};\n"
          f"const EMB={json.dumps({k: v for k, v in emb.items() if k != 'tiles'})};\nconst TILES={json.dumps(emb['tiles'])};\n"
          "const TILE_SOURCE={width:EMB.width,height:EMB.height,tileSize:EMB.tileSize,tileOverlap:EMB.tileOverlap,minLevel:0,maxLevel:EMB.maxLevel,getTileUrl:(l,x,y)=>TILES[`${l}/${x}_${y}`]||''};")
artifact = fill(tpl, {**common, '{{PX_M}}': f'{emb["tileSize"]/geo.W:.2f}', '{{M_PER_PX}}': f'{geo.W/emb["tileSize"]:.5f}', '{{STORY_URL}}': a.artifact_story_url,
                      '{{OSD_SCRIPT}}': '<script src="https://cdnjs.cloudflare.com/ajax/libs/openseadragon/5.0.1/openseadragon.min.js"></script>', '{{DATA_INLINE}}': data_e, '{{MAX_ZOOM_PX}}': '8', '{{REPORT_INIT}}': REPORT_DB_INIT, '{{REPORT_SUBMIT}}': REPORT_DB_SUBMIT, '{{HIRES_LINK}}': (f'<a class="tb story-link" href="{a.hires_url}" target="_blank" rel="noopener" title="Versión a 2.93 px/m, 4× más detalle">Alta resolución ↗</a>' if a.hires_url else '')})
(art / 'simleon-mapa.html').write_text(artifact)
print('hosted', (site/'index.html').stat().st_size//1024, 'KB; artifact', (art/'simleon-mapa.html').stat().st_size/1e6, 'MB')
