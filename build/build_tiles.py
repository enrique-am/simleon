#!/usr/bin/env python3
"""Assemble the pixel-art squares into one mosaic, quantize to a single 256-colour palette,
and cut a DZI tile pyramid (for the self-hosted site) plus an embedded pyramid JSON (for the artifact page).

usage: build_tiles.py --in pixels_pro --out site [--grid 1024] [--embed-grid 768]
"""
import argparse, base64, io, json, math, sys
from pathlib import Path
from PIL import Image
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import geo

ap = argparse.ArgumentParser()
ap.add_argument('--in', dest='inp', default='pixels_pro'); ap.add_argument('--out', default='site')
ap.add_argument('--grid', type=int, default=1024, help='pixel grid per square for the hosted mosaic')
ap.add_argument('--embed-grid', type=int, default=768, help='pixel grid per square for the embedded (artifact) pyramid')
ap.add_argument('--colors', type=int, default=256); ap.add_argument('--tile', type=int, default=512)
ap.add_argument('--embed-format', default='webp', choices=['png','webp']); ap.add_argument('--embed-quality', type=int, default=82)
ap.add_argument('--normalize', type=float, default=0.6, help='0-1 strength of per-square colour normalization (mean/std matched to the map-wide median)')
ap.add_argument('--tile-format', default='webp', choices=['png','webp'], help='hosted DZI tile format'); ap.add_argument('--tile-quality', type=int, default=85, help='WebP quality for hosted tiles (100 = lossless)')
a = ap.parse_args()
ROOT = geo.ROOT; inp = ROOT / a.inp; out = ROOT / a.out; out.mkdir(parents=True, exist_ok=True)

# ---- 1. load squares, downsample to the pixel grid
squares = {}
for s in geo.G['squares']:
    f = inp / f"sq_{s['i']}_{s['j']}.png"
    if f.exists():
        squares[(s['i'], s['j'])] = Image.open(f).convert('RGB').resize((a.grid, a.grid), Image.BOX)
    else:
        print('MISSING', f.name)
print(f'{len(squares)} squares')

# ---- 1b. colour normalization: pull every square's per-channel mean/std toward the map-wide median (softens style jumps at seams)
if a.normalize > 0 and len(squares) > 2:
    stats = {k: (np.asarray(im, dtype=np.float32).reshape(-1, 3).mean(0), np.asarray(im, dtype=np.float32).reshape(-1, 3).std(0)) for k, im in squares.items()}
    ref_mean = np.median(np.stack([m for m, _ in stats.values()]), 0); ref_std = np.median(np.stack([sd for _, sd in stats.values()]), 0)
    for k, im in squares.items():
        m, sd = stats[k]
        tgt_m = m + a.normalize * (ref_mean - m); tgt_sd = sd + a.normalize * (ref_std - sd)
        arr = np.asarray(im, dtype=np.float32)
        arr = (arr - m) / np.maximum(sd, 1e-3) * tgt_sd + tgt_m
        squares[k] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    print(f'normalized colours toward mean {ref_mean.round(1)} std {ref_std.round(1)} (strength {a.normalize})')

# ---- 2. one shared palette (k-means) across every square
from sklearn.cluster import MiniBatchKMeans
X = np.concatenate([np.asarray(im)[::4, ::4].reshape(-1, 3) for im in squares.values()]).astype(np.float32)
km = MiniBatchKMeans(n_clusters=a.colors, random_state=0, batch_size=8192, n_init=3).fit(X)
pal = np.clip(km.cluster_centers_.round(), 0, 255).astype(np.uint8)
pal_img = Image.new('P', (1, 1)); pal_img.putpalette(pal.flatten().tolist())
json.dump(pal.tolist(), open(out / 'palette.json', 'w'))

# ---- 3. mosaic (quantized, mode P)
cols, rows, g = geo.COLS, geo.ROWS, a.grid
mosaic = Image.new('P', (cols * g, rows * g)); mosaic.putpalette(pal.flatten().tolist())
bg = int(np.argmin(np.abs(pal.astype(int) - np.array([24, 24, 32])).sum(1)))
mosaic.paste(bg, (0, 0, mosaic.width, mosaic.height))
for (i, j), im in squares.items():
    q = im.quantize(palette=pal_img, dither=Image.Dither.NONE)
    mosaic.paste(q, ((i - geo.I0) * g, (geo.J0 - j) * g))
mosaic.save(out / 'mosaic.png', optimize=True)
print('mosaic', mosaic.size, (out / 'mosaic.png').stat().st_size // 1024, 'KB')
mosaic_rgb = mosaic.convert('RGB')

OV = 1  # 1px tile overlap hides sub-pixel seams when smoothing is off
def pyramid(img, tile, min_size=1):
    """Yield (level, x, y, PIL tile) DZI-style: level N is full-res, level 0 is 1px."""
    W, H = img.size
    max_level = math.ceil(math.log2(max(W, H)))
    lv = img
    for level in range(max_level, -1, -1):
        w, h = lv.size
        for ty in range(math.ceil(h / tile)):
            for tx in range(math.ceil(w / tile)):
                yield level, tx, ty, lv.crop((max(0, tx * tile - OV), max(0, ty * tile - OV), min((tx + 1) * tile + OV, w), min((ty + 1) * tile + OV, h)))
        if max(w, h) <= min_size: break
        lv = lv.resize((max(1, math.ceil(w / 2)), max(1, math.ceil(h / 2))), Image.BOX)

# ---- 4. DZI for the hosted site
dzi_dir = out / 'tiles_files'; dzi_dir.mkdir(exist_ok=True)
n = 0
for level, tx, ty, t in pyramid(mosaic_rgb, a.tile):
    d = dzi_dir / str(level); d.mkdir(exist_ok=True)
    tq = t.quantize(palette=pal_img, dither=Image.Dither.NONE)
    if a.tile_format == 'webp':
        if a.tile_quality >= 100: tq.convert('RGB').save(d / f'{tx}_{ty}.webp', 'WEBP', lossless=True, method=6)
        else: tq.convert('RGB').save(d / f'{tx}_{ty}.webp', 'WEBP', quality=a.tile_quality, method=6)
    else: tq.save(d / f'{tx}_{ty}.png', optimize=True)
    n += 1
(out / 'tiles.dzi').write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" Format="{a.tile_format}" Overlap="{OV}" TileSize="{a.tile}"><Size Width="{mosaic.width}" Height="{mosaic.height}"/></Image>\n')
print('dzi tiles', n)

# ---- 5. embedded pyramid for the artifact page (data URIs), tile = one square at embed-grid
eg = a.embed_grid
small = mosaic_rgb.resize((cols * eg, rows * eg), Image.BOX).quantize(palette=pal_img, dither=Image.Dither.NONE).convert('RGB')
tiles = {}; total = 0
for level, tx, ty, t in pyramid(small, eg):
    buf = io.BytesIO(); tq = t.quantize(palette=pal_img, dither=Image.Dither.NONE)
    if a.embed_format == 'webp': tq.convert('RGB').save(buf, 'WEBP', quality=a.embed_quality, method=6); mime = 'image/webp'
    else: tq.save(buf, 'PNG', optimize=True); mime = 'image/png'
    b = buf.getvalue(); total += len(b)
    tiles[f'{level}/{tx}_{ty}'] = f'data:{mime};base64,' + base64.b64encode(b).decode()
emb = {'width': small.width, 'height': small.height, 'tileSize': eg, 'tileOverlap': OV, 'maxLevel': math.ceil(math.log2(max(small.size))), 'tiles': tiles}
json.dump(emb, open(out / 'embedded_tiles.json', 'w'))
print(f'embedded: {len(tiles)} tiles, {total/1e6:.1f} MB raw, {(out/"embedded_tiles.json").stat().st_size/1e6:.1f} MB json')

# ---- 6. POIs projected to mosaic pixels (hosted grid) + normalized coords
pois = json.load(open(ROOT / 'data/pois.json'))
scale = g / geo.PX
for p in pois:
    x, y = geo.lonlat_to_pixel(p['lon'], p['lat'], scale=scale)
    p['x'], p['y'] = round(x), round(y)
    p['nx'], p['ny'] = round(x / mosaic.width, 5), round(y / mosaic.height, 5)   # fraction of width (OSD viewport coords use x/width)
json.dump(pois, open(out / 'pois.json', 'w'), ensure_ascii=False, indent=1)
json.dump({'cols': cols, 'rows': rows, 'i0': geo.I0, 'j0': geo.J0, 'grid': g, 'W': geo.W, 'heading': geo.G['heading'], 'pitch': geo.G['pitch'],
           'squares': [{'i': s['i'], 'j': s['j'], 'has': (s['i'], s['j']) in squares} for s in geo.G['squares']]}, open(out / 'grid_meta.json', 'w'))
print('done')
