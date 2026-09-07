#!/usr/bin/env python3
"""Seam audit + repair across tile borders (Isometric-NYC-style infill, applied after the fact).

audit:  seams.py audit [--out build/seams.json]          → judge every join (2 crops per join), 0-10 how visible the seam is
repair: seams.py repair --queue build/seams.json --min 5  → for each flagged join, regenerate ONLY a band of ±150 px around the
        border inside a 1024 px window that spans both tiles; the model sees both finished sides and the photo, and must
        continue the drawing so the two sides meet; the band is pasted back into BOTH tiles (hard mask). ≈ $0.27 per window.
"""
import argparse, base64, io, json, math, sys, time, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent)); import pixelate as P
ROOT = P.ROOT; PX = 2048; WIN = 1024; BAND = 150
GRID = json.load(open(ROOT / 'grid.json'))
HAVE = {(s['i'], s['j']) for s in GRID['squares'] if (ROOT / f"pixels_pro/sq_{s['i']}_{s['j']}.png").exists()}

def art(i, j): return Image.open(ROOT / f'pixels_pro/sq_{i}_{j}.png').convert('RGB')
def photo(i, j): return Image.open(ROOT / f'renders/sq_{i}_{j}.png').convert('RGB')

def joins():
    """Each join: (a, b, orientation). 'v' = b is right of a (i+1); 'h' = b is below a (j-1)."""
    out = []
    for (i, j) in sorted(HAVE):
        if (i + 1, j) in HAVE: out.append(((i, j), (i + 1, j), 'v'))
        if (i, j - 1) in HAVE: out.append(((i, j), (i, j - 1), 'h'))
    return out

def window(a, b, orient, k, loader):
    """1024x1024 window centred on the border, at position k (0 or 1) along the border. Returns image + paste info."""
    A, B = loader(*a), loader(*b)
    if orient == 'v':   # A | B side by side
        y0 = k * WIN; canvas = Image.new('RGB', (WIN, WIN))
        canvas.paste(A.crop((PX - WIN // 2, y0, PX, y0 + WIN)), (0, 0)); canvas.paste(B.crop((0, y0, WIN // 2, y0 + WIN)), (WIN // 2, 0))
    else:               # A above B
        x0 = k * WIN; canvas = Image.new('RGB', (WIN, WIN))
        canvas.paste(A.crop((x0, PX - WIN // 2, x0 + WIN, PX)), (0, 0)); canvas.paste(B.crop((x0, 0, x0 + WIN, WIN // 2)), (0, WIN // 2))
    return canvas

def b64(im, side=None):
    if side: im = im.resize((side, side), Image.BOX)
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()

def judge_seam(win):
    prompt = ("This is a crop of an isometric pixel-art city map that spans the border between two separately generated tiles; the border runs exactly through the middle "
              "(vertical or horizontal). Rate 0-10 how VISIBLE the join is: 0 = seamless, 10 = obvious change in drawing style, colour, density, brightness or a hard line. "
              "Ignore real content changes (a road ending, a different neighbourhood). Reply ONLY JSON: {\"seam\": n, \"why\": \"...\"}")
    body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/png', 'data': b64(win, 768)}}, {'text': prompt}]}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.0}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.JUDGE_MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
        j = json.loads(res['candidates'][0]['content']['parts'][0]['text']); return float(j.get('seam', 5)), j.get('why', '')
    except Exception as e:
        print('  judge failed', str(e)[:100], file=sys.stderr); return 5.0, 'judge failed'

def gen_band(art_win, photo_win, mask, orient):
    P.quota_guard()
    parts = [{'inline_data': {'mime_type': 'image/png', 'data': b64(art_win)}}, {'inline_data': {'mime_type': 'image/png', 'data': b64(photo_win)}}, {'inline_data': {'mime_type': 'image/png', 'data': b64(mask)}},
             {'text': ("Image 1 is an isometric pixel-art city map in which two separately drawn tiles meet along a " + ('vertical' if orient == 'v' else 'horizontal') + " line through the middle. "
                       "Image 2 is the aerial photo of exactly the same area. Image 3 is a mask: WHITE is the band you may change. "
                       "Redraw ONLY the white band so the two sides meet seamlessly: continue streets, blocks and roofs across the join exactly as the photo shows them, and blend the drawing style so that "
                       "pixel density, outline weight, roof textures, saturation and brightness are the same on both sides of the band. Everything outside the mask must stay pixel-identical. "
                       "Hard-edged pixel art, no blur, no text.")}]
    body = {'contents': [{'parts': parts}], 'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '1:1', 'imageSize': '1K'}}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: res = json.load(r)
            P.quota_bump()
            for p in res['candidates'][0]['content']['parts']:
                if 'inlineData' in p: return Image.open(io.BytesIO(base64.b64decode(p['inlineData']['data']))).convert('RGB').resize((WIN, WIN), Image.LANCZOS)
            raise RuntimeError('no image')
        except urllib.error.HTTPError as e:
            print('  HTTP', e.code, file=sys.stderr)
            if e.code in (429, 500, 503) and attempt < 3: time.sleep(10 * (attempt + 1)); continue
            raise

def paste_back(a, b, orient, k, band_img):
    """Write the band pixels of band_img back into both tiles (only the band region)."""
    A, B = art(*a), art(*b)
    if orient == 'v':
        y0 = k * WIN
        A.paste(band_img.crop((WIN // 2 - BAND, 0, WIN // 2, WIN)), (PX - BAND, y0)); B.paste(band_img.crop((WIN // 2, 0, WIN // 2 + BAND, WIN)), (0, y0))
    else:
        x0 = k * WIN
        A.paste(band_img.crop((0, WIN // 2 - BAND, WIN, WIN // 2)), (x0, PX - BAND)); B.paste(band_img.crop((0, WIN // 2, WIN, WIN // 2 + BAND)), (x0, 0))
    hist = ROOT / 'pixels_pro/history'; hist.mkdir(exist_ok=True); ts = int(time.time())
    for (t, im) in ((a, A), (b, B)):
        p = ROOT / f'pixels_pro/sq_{t[0]}_{t[1]}.png'
        if not (hist / f'sq_{t[0]}_{t[1]}_{ts}_preseam.png').exists(): Image.open(p).save(hist / f'sq_{t[0]}_{t[1]}_{ts}_preseam.png')
        im.save(p)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['audit', 'repair']); ap.add_argument('--out', default='build/seams.json'); ap.add_argument('--queue', default='build/seams.json')
    ap.add_argument('--min', type=float, default=5); ap.add_argument('--n', type=int, default=2)
    a = ap.parse_args()
    if a.cmd == 'audit':
        res = []
        for (ta, tb, o) in joins():
            for k in (0, 1):
                s, why = judge_seam(window(ta, tb, o, k, art)); res.append({'a': list(ta), 'b': list(tb), 'o': o, 'k': k, 'seam': s, 'why': why, 'done': False})
                print(ta, tb, o, k, s, why[:70])
        json.dump(res, open(ROOT / a.out, 'w'), indent=1, ensure_ascii=False)
        flagged = [r for r in res if r['seam'] >= a.min]
        print(f'{len(res)} windows, {len(flagged)} at seam>={a.min} (~${0.134*a.n*len(flagged):.2f} to repair)')
    else:
        q = json.load(open(ROOT / a.queue))
        for r in q:
            if r['done'] or r['seam'] < a.min: continue
            ta, tb, o, k = tuple(r['a']), tuple(r['b']), r['o'], r['k']
            aw, pw = window(ta, tb, o, k, art), window(ta, tb, o, k, photo)
            mask = Image.new('RGB', (WIN, WIN), 'black')
            ImageDraw.Draw(mask).rectangle((WIN // 2 - BAND, 0, WIN // 2 + BAND, WIN) if o == 'v' else (0, WIN // 2 - BAND, WIN, WIN // 2 + BAND), fill='white')
            best = None
            for c in range(a.n):
                try:
                    out = gen_band(aw, pw, mask, o)
                except P.QuotaExhausted as e:
                    print('QUOTA:', e, '- stopping cleanly, rerun after reset', file=sys.stderr)
                    if best is None: sys.exit(75)
                    break
                merged = aw.copy(); merged.paste(out.crop((WIN // 2 - BAND, 0, WIN // 2 + BAND, WIN)) if o == 'v' else out.crop((0, WIN // 2 - BAND, WIN, WIN // 2 + BAND)), (WIN // 2 - BAND, 0) if o == 'v' else (0, WIN // 2 - BAND))
                s, why = judge_seam(merged)
                print(f'  {ta}{tb}{o}{k} cand {c}: seam {s} (was {r["seam"]})')
                if best is None or s < best[0]: best = (s, merged)
            if best[0] < r['seam']:
                paste_back(ta, tb, o, k, best[1]); r['after'] = best[0]
            else: r['after'] = r['seam']; print('  kept original')
            r['done'] = True; r['usd'] = round(0.134 * a.n, 3)
            json.dump(q, open(ROOT / a.queue, 'w'), indent=1, ensure_ascii=False)
