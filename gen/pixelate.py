#!/usr/bin/env python3
"""Restyle rendered 3D squares into SimCity-2000-style pixel art with Nano Banana 2 (gemini-3.1-flash-image).

usage: pixelate.py --in renders --out pixels [--only -1,1;0,0] [--anchor pixels/sq_0_0.png] [--force] [--size 2K]
Writes pixels/sq_i_j.png plus a JSON log with cost accounting.
"""
import argparse, base64, io, json, os, sys, time, urllib.request
from pathlib import Path
from PIL import Image
import numpy as np
from skimage.metrics import structural_similarity as ssim

def fidelity(src_path, img_bytes):
    """How well the generated image keeps the source layout: SSIM on 256px grayscale + edge correlation."""
    a = np.asarray(Image.open(src_path).convert('L').resize((256,256), Image.BOX), dtype=np.float32)
    b = np.asarray(Image.open(io.BytesIO(img_bytes)).convert('L').resize((256,256), Image.BOX), dtype=np.float32)
    s1 = ssim(a, b, data_range=255)
    ga = np.hypot(*np.gradient(a)); gb = np.hypot(*np.gradient(b))
    c = float(np.corrcoef(ga.ravel(), gb.ravel())[0,1])
    return round(0.5*s1 + 0.5*c, 4)

def judge(src_path, img_bytes):
    """Ask a vision LLM how faithfully the drawing preserves the source layout. Returns (score 0-10, issues)."""
    prompt = ("Image 1 is an aerial photo of a city. Image 2 is a pixel-art redrawing of it that should preserve the layout EXACTLY. "
              "Compare them carefully. Score 0-10 how faithfully image 2 keeps every street, block, plaza, building footprint and building height "
              "(10 = perfect tracing; subtract heavily for invented buildings/towers/plazas/parks, missing streets, shifted or rescaled areas). "
              "Ignore colour and drawing style. Reply ONLY with JSON: {\"score\": number, \"issues\": [short strings]}")
    body = {'contents':[{'parts':[{'inline_data':{'mime_type':'image/png','data':b64img(src_path, 1024)}},
                                  {'inline_data':{'mime_type':'image/png','data':base64.b64encode(_shrink(img_bytes,1024)).decode()}},
                                  {'text':prompt}]}],
            'generationConfig':{'responseMimeType':'application/json','temperature':0.1}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{JUDGE_MODEL}:generateContent',
                                 data=json.dumps(body).encode(), headers={'Content-Type':'application/json','x-goog-api-key':KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
        txt = res['candidates'][0]['content']['parts'][0]['text']
        j = json.loads(txt)
        return float(j.get('score', 0)), j.get('issues', [])
    except Exception as e:
        print('  judge failed:', str(e)[:200], file=sys.stderr)
        return 5.0, ['judge failed']

STYLE_PROMPT = ("These are two crops from one tile of an isometric pixel-art city map. Rate the DRAWING STYLE only, not the content. "
  "pixel_score 0-10: 10 = dense retro pixel-art sprites (visible hard pixels, textured roofs, tiny windows, crisp dark outlines, saturated colours), "
  "0 = smooth flat vector illustration (large uniform fills, soft or no outlines, little texture, washed-out). Reply ONLY JSON: {\"pixel_score\": n}")
def style_score(img_bytes):
    """0-10 how much the candidate looks like dense pixel art (vs flat vector). Used to keep the map's style uniform."""
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert('RGB'); W = im.width; k = W / 2048
        crops = [im.crop((int(600*k), int(600*k), int(1200*k), int(1200*k))), im.crop((int(1200*k), int(300*k), int(1800*k), int(900*k)))]
        parts = []
        for c in crops:
            buf = io.BytesIO(); c.save(buf, 'PNG', optimize=True); parts.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(buf.getvalue()).decode()}})
        parts.append({'text': STYLE_PROMPT})
        body = {'contents': [{'parts': parts}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.0}}
        req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{JUDGE_MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': KEY})
        with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
        return float(json.loads(res['candidates'][0]['content']['parts'][0]['text']).get('pixel_score', 5))
    except Exception as e:
        print('  style judge failed:', str(e)[:120], file=sys.stderr); return 5.0

def _shrink(img_bytes, side):
    im = Image.open(io.BytesIO(img_bytes)).convert('RGB').resize((side, side), Image.BOX)
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return buf.getvalue()

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(l.strip().split('=',1) for l in (ROOT/'.env').read_text().splitlines() if '=' in l)
KEY = ENV['GEMINI_API_KEY']
MODEL = os.environ.get('NB_MODEL', 'gemini-3-pro-image-preview')  # Nano Banana Pro: far more faithful to the source geometry than 3.1-flash-image
PRICES = {'gemini-3.1-flash-image': {'1K':0.067, '2K':0.101, '4K':0.151}, 'gemini-3-pro-image-preview': {'1K':0.134, '2K':0.134, '4K':0.24}, 'gemini-3-pro-image': {'1K':0.134, '2K':0.134, '4K':0.24}}
PRICE = PRICES.get(MODEL, PRICES['gemini-3-pro-image-preview'])
JUDGE_MODEL = 'gemini-flash-latest'

PROMPT = (Path(__file__).parent/'prompt.txt').read_text().strip()

def b64img(path, max_side=1536):
    im = Image.open(path).convert('RGB')
    if max(im.size) > max_side:
        im = im.resize((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode()

def generate(src, anchor=None, size='2K', prompt=PROMPT, retries=4):
    parts = []
    if anchor:
        parts.append({'text': 'REFERENCE STYLE (already-drawn neighbouring square of the same map — match its palette, pixel density, line weight and lighting exactly):'})
        parts.append({'inline_data': {'mime_type':'image/png', 'data': b64img(anchor)}})
        parts.append({'text': 'SOURCE PHOTO to redraw:'})
    parts.append({'inline_data': {'mime_type':'image/png', 'data': b64img(src)}})
    parts.append({'text': prompt})
    body = {'contents':[{'parts':parts}],
            'generationConfig':{'responseModalities':['IMAGE'], 'imageConfig':{'aspectRatio':'1:1','imageSize':size}}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent',
                                 data=json.dumps(body).encode(), headers={'Content-Type':'application/json','x-goog-api-key':KEY})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                res = json.load(r)
            for p in res['candidates'][0]['content']['parts']:
                if 'inlineData' in p:
                    return base64.b64decode(p['inlineData']['data']), res.get('usageMetadata',{})
            raise RuntimeError('no image in response: ' + json.dumps(res)[:500])
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:400]
            print(f'  HTTP {e.code}: {msg}', file=sys.stderr)
            if e.code in (429, 500, 503) and attempt < retries-1:
                time.sleep(10*(attempt+1)); continue
            raise
    raise RuntimeError('exhausted retries')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', default='renders'); ap.add_argument('--out', default='pixels')
    ap.add_argument('--only'); ap.add_argument('--anchor'); ap.add_argument('--force', action='store_true')
    ap.add_argument('--size', default='2K'); ap.add_argument('--suffix', default='')
    ap.add_argument('--n', type=int, default=2, help='candidates per square; best fidelity wins')
    ap.add_argument('--min-judge', type=float, default=6.5, help='keep generating (up to --max-n) until a candidate reaches this judge score')
    ap.add_argument('--max-n', type=int, default=4)
    ap.add_argument('--min-style', type=float, default=6.0, help='keep generating until a candidate is at least this pixel-art-dense (0-10)')
    a = ap.parse_args()
    out = ROOT/a.out; out.mkdir(exist_ok=True, parents=True)
    log_path = out/'gen_log.jsonl'
    files = sorted((ROOT/a.inp).glob('sq_*.png'))
    if a.only:
        want = {tuple(map(int, s.split(','))) for s in a.only.split(';')}
        files = [f for f in files if tuple(map(int, f.stem.split('_')[1:3])) in want]
    for f in files:
        dst = out/(f.stem + a.suffix + '.png')
        if dst.exists() and not a.force:
            print('skip', dst.name); continue
        # guard: a render whose 3D tiles never loaded is a blur — never spend money on it
        _a = np.asarray(Image.open(f).convert('L').resize((512,512)), dtype=np.float32)
        _lap = np.abs(4*_a[1:-1,1:-1]-_a[:-2,1:-1]-_a[2:,1:-1]-_a[1:-1,:-2]-_a[1:-1,2:])
        if float(_lap.var()) < 300:
            print(f'SKIP {f.name}: render is blurry (sharpness {_lap.var():.0f}); re-render it', file=sys.stderr); continue
        t = time.time()
        cands = []
        for k in range(a.max_n):
            if k >= a.n and any(c[2] >= a.min_judge and c[4] >= a.min_style for c in cands): break
            img, usage = generate(f, a.anchor, a.size)
            js, issues = judge(f, img); st = style_score(img)
            sc = js + 0.5*fidelity(f, img) + (0.8*st if st >= a.min_style else -3 + 0.8*st)  # fidelity first, but flat-vector candidates are heavily penalised
            print(f'  cand {k}: judge={js} style={st} issues={issues[:2]}')
            (out/'candidates').mkdir(exist_ok=True)
            (out/'candidates'/f'{f.stem}{a.suffix}_c{k}_{sc:.3f}.png').write_bytes(img)
            cands.append((sc, img, js, usage, st))
        cands.sort(key=lambda c: -c[0])
        sc, img, js, usage, st = cands[0]
        dst.write_bytes(img)
        rec = {'src': f.name, 'dst': dst.name, 'model': MODEL, 'size': a.size, 'anchor': a.anchor, 'secs': round(time.time()-t,1), 'usd': round(PRICE.get(a.size)*len(cands),3), 'n': len(cands), 'judge': js, 'style': st, 'scores': [c[0] for c in cands], 'judges': [c[2] for c in cands], 'styles': [c[4] for c in cands], 'usage': usage, 'ts': time.time()}
        with open(log_path, 'a') as lf: lf.write(json.dumps(rec)+'\n')
        print(f'{dst.name}  {rec["secs"]}s  ${rec["usd"]}')

if __name__ == '__main__':
    main()
