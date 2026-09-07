#!/usr/bin/env python3
"""Regenerate squares in the style of a STANDARD square, London-style, but as an in-context example PAIR
(standard photo -> standard drawing) so the model learns the transformation instead of copying content.
usage: restyle.py --std -1,1 --only "-4,2;-3,2" [--n 2] [--max-n 4] [--min-judge 6.5] [--min-style 6]
"""
import argparse, base64, io, json, sys, time, urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent)); import pixelate as P
ROOT = P.ROOT
SIM_PROMPT = ("Images 1-2 are crops of the STANDARD tile of an isometric pixel-art city map. Images 3-4 are crops of ANOTHER tile. "
  "Ignore what is depicted; compare only the DRAWING STYLE: pixel density and sprite detail, outline weight, roof textures, colour saturation and palette, tree/car sprites, lighting and contrast. "
  "similarity 0-10 (10 = indistinguishable style, 5 = clearly a different rendering mode). Reply ONLY JSON: {\"similarity\": n}")
def _crops(im):
    return [im.crop((600, 600, 1200, 1200)), im.crop((1300, 200, 1900, 800))]
def _b64(im):
    buf = io.BytesIO(); im.convert('RGB').save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()
def similarity(std_art_path, img_bytes):
    try:
        sp = _crops(Image.open(std_art_path)); tp = _crops(Image.open(io.BytesIO(img_bytes)).convert('RGB').resize((2048, 2048)))
        parts = [{'inline_data': {'mime_type': 'image/png', 'data': _b64(c)}} for c in sp + tp] + [{'text': SIM_PROMPT}]
        body = {'contents': [{'parts': parts}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.0}}
        req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.JUDGE_MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
        with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
        return float(json.loads(res['candidates'][0]['content']['parts'][0]['text']).get('similarity', 5))
    except Exception as e:
        print('  similarity judge failed', str(e)[:100], file=sys.stderr); return 5.0

def gen_with_pair(std_photo, std_art, target_photo, size='2K'):
    P.quota_guard()
    parts = [
      {'text': 'EXAMPLE — Image 1 is an aerial photo and Image 2 is how it was drawn. Study ONLY the drawing style: pixel density, outline weight, roof textures, colour saturation, tree and car sprites, lighting.'},
      {'inline_data': {'mime_type': 'image/png', 'data': P.b64img(std_photo, 1280)}},
      {'inline_data': {'mime_type': 'image/png', 'data': P.b64img(std_art, 1280)}},
      {'text': 'TARGET — Image 3 is a DIFFERENT area. Redraw Image 3 in exactly the style of Image 2. Its content must come ONLY from Image 3: do not copy, reuse or transplant any building, church, street or block from Images 1-2.'},
      {'inline_data': {'mime_type': 'image/png', 'data': P.b64img(target_photo, 1536)}},
      {'text': P.PROMPT}]
    body = {'contents': [{'parts': parts}], 'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '1:1', 'imageSize': size}}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: res = json.load(r)
            P.quota_bump()
            for p in res['candidates'][0]['content']['parts']:
                if 'inlineData' in p: return base64.b64decode(p['inlineData']['data'])
            raise RuntimeError('no image')
        except urllib.error.HTTPError as e:
            msg = e.read().decode() if hasattr(e, 'read') else ''
            if e.code == 429 and 'per_day' in msg:
                print('DAILY QUOTA EXHAUSTED — stopping; rerun tomorrow (progress is saved per square).', file=sys.stderr); sys.exit(75)
            if e.code in (429, 500, 503) and attempt < 3: time.sleep(10 * (attempt + 1)); continue
            raise

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--std', default='-1,1'); ap.add_argument('--only', required=True)
    ap.add_argument('--n', type=int, default=2); ap.add_argument('--max-n', type=int, default=4); ap.add_argument('--min-judge', type=float, default=6.5); ap.add_argument('--min-style', type=float, default=7); ap.add_argument('--judge-floor', type=float, default=6.0, help='hard fidelity floor: a candidate below this is never saved, however good its style')
    ap.add_argument('--out', default='pixels_pro'); ap.add_argument('--dry', action='store_true'); ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    si, sj = a.std.split(','); std_photo = ROOT / f'renders/sq_{si}_{sj}.png'; std_art = ROOT / f'pixels_pro/sq_{si}_{sj}.png'
    out = ROOT / a.out; (out / 'candidates').mkdir(parents=True, exist_ok=True); (out / 'history').mkdir(exist_ok=True)
    ap_force = '--force' in sys.argv
    done = set()
    if (out / 'gen_log.jsonl').exists():
        for l in open(out / 'gen_log.jsonl'):
            try:
                r = json.loads(l)
                if r.get('restyle_std') == a.std and not r.get('kept_original'): done.add(r['dst'])
            except Exception: pass
    for sq in a.only.split(';'):
        i, j = sq.split(','); src = ROOT / f'renders/sq_{i}_{j}.png'; dst = out / f'sq_{i}_{j}.png'
        if (i, j) == (si, sj): continue
        if dst.name in done and not ap_force: print('skip (already restyled)', dst.name); continue
        if not src.exists(): print('skip (no render)', dst.name); continue
        t = time.time(); cands = []
        try:
         for k in range(a.max_n):
            if k >= a.n and any(c[2] >= a.min_judge and c[3] >= a.min_style for c in cands): break
            img = gen_with_pair(std_photo, std_art, src)
            js, issues = P.judge(src, img); st = similarity(std_art, img); fid = P.fidelity(src, img)
            sc = js + 0.5 * fid + (0.8 * st if st >= a.min_style else -3 + 0.8 * st)
            (out / 'candidates' / f'sq_{i}_{j}_restyle_c{k}_{js:.1f}_{st:.0f}.png').write_bytes(img)
            cands.append((sc, img, js, st)); print(f'  {sq} cand {k}: judge={js} style={st} {issues[:2]}')
        except P.QuotaExhausted as e:
            print('QUOTA:', e, '- stopping cleanly, rerun after reset', file=sys.stderr)
            if not cands: sys.exit(75)
        # FIDELITY FIRST: style never buys a square that got the city wrong.
        elig = [c for c in cands if c[2] >= a.judge_floor]
        if not elig:
            print(f'{sq}: no candidate reached fidelity {a.judge_floor} (best {max(c[2] for c in cands)}) - keeping the existing square', flush=True)
            with open(out / 'gen_log.jsonl', 'a') as lf:
                lf.write(json.dumps({'src': src.name, 'dst': dst.name, 'restyle_std': a.std, 'restyle': True, 'kept_original': True,
                                     'usd': round(0.134 * len(cands), 3), 'n': len(cands), 'judge': max(c[2] for c in cands),
                                     'style': max(c[3] for c in cands), 'judges': [c[2] for c in cands], 'styles': [c[3] for c in cands], 'ts': time.time()}) + '\n')
            continue
        elig.sort(key=lambda c: (-c[3], -c[2]))   # best style among the faithful ones
        sc, img, js, st = elig[0]
        if dst.exists(): dst.rename(out / 'history' / f'sq_{i}_{j}_{int(time.time())}_prerestyle.png')
        dst.write_bytes(img)
        rec = {'src': src.name, 'dst': dst.name, 'model': P.MODEL, 'size': '2K', 'restyle_std': a.std, 'restyle': True, 'secs': round(time.time() - t, 1), 'usd': round(0.134 * len(cands), 3), 'n': len(cands), 'judge': js, 'style': st, 'judges': [c[2] for c in cands], 'styles': [c[3] for c in cands], 'ts': time.time()}
        with open(out / 'gen_log.jsonl', 'a') as lf: lf.write(json.dumps(rec) + '\n')
        print(f'{dst.name} judge {js} style {st} ${rec["usd"]}')
