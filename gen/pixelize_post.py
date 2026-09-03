#!/usr/bin/env python3
"""Deterministic pixel-art post-process: downsample generated squares to a coarse pixel grid,
quantize all of them to ONE shared retro palette (built from all squares), then nearest-upscale.
usage: pixelize_post.py --in pixels --out pixels_final [--grid 1024] [--colors 64] [--scale 2]
"""
import argparse, json
from pathlib import Path
from PIL import Image
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--in', dest='inp', default='pixels'); ap.add_argument('--out', default='pixels_final')
ap.add_argument('--grid', type=int, default=1024); ap.add_argument('--colors', type=int, default=64)
ap.add_argument('--scale', type=int, default=2); ap.add_argument('--palette')
a = ap.parse_args()
inp, out = Path(a.inp), Path(a.out); out.mkdir(exist_ok=True, parents=True)
files = sorted(f for f in inp.glob('sq_*.png') if '_' not in f.stem[3:].replace('_','',2))  # sq_i_j.png only
files = sorted(inp.glob('sq_*_*.png'))
files = [f for f in files if len(f.stem.split('_')) == 3]

small = {f: Image.open(f).convert('RGB').resize((a.grid, a.grid), Image.BOX) for f in files}

if a.palette and Path(a.palette).exists():
    pal_img = Image.open(a.palette)
else:
    # shared 256-colour palette via k-means over a strided sample of every square (SimCity 2000 was 256-colour VGA)
    from sklearn.cluster import MiniBatchKMeans
    X = np.concatenate([np.asarray(im)[::3, ::3].reshape(-1, 3) for im in small.values()]).astype(np.float32)
    km = MiniBatchKMeans(n_clusters=a.colors, random_state=0, batch_size=4096, n_init=3).fit(X)
    pal = np.clip(km.cluster_centers_.round(), 0, 255).astype(np.uint8)
    pal_img = Image.new('P', (1, 1)); pal_img.putpalette(pal.flatten().tolist())
    pal_img.save(out / 'palette.png')
    json.dump(pal.tolist(), open(out / 'palette.json', 'w'))

for f, im in small.items():
    q = im.quantize(palette=pal_img, dither=Image.Dither.NONE).convert('RGB')
    q = q.resize((a.grid * a.scale, a.grid * a.scale), Image.NEAREST)
    q.save(out / f.name, optimize=True)
    print('ok', f.name)
