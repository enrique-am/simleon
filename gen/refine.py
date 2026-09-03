#!/usr/bin/env python3
"""Refine ONE boxed region of a finished pixel-art square, with hard constraints:
only pixels inside the box change (enforced in code), style is taken from the square itself,
and the model is shown the true geometry (photo crop + optional high-zoom 3D close-up + optional real photos).

usage:
  refine.py --sq -1,0 --box 1560,260,2040,720 --note "this is the Templo Expiatorio: white neo-gothic church with slim spires" \
            [--poi expiatorio] [--closeup] [--n 2] [--dry]
  refine.py --queue build/refine_queue.json     # run many jobs (from detect.py or map reports)

Box is in the square's 2048-px pixel space (same as the Q overlay / report tool). Keeps a backup in pixels_pro/history/.
"""
import argparse, base64, io, json, math, subprocess, sys, time, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).parent))
import pixelate as P   # reuse key, model, b64img, fidelity, judge helpers

ROOT = P.ROOT
PX = 2048
GRID = json.load(open(ROOT / 'grid.json'))
W = GRID['W']; SINP = math.sin(math.radians(abs(GRID['pitch'])))

REFINE_PROMPT = """You are editing ONE region of an existing isometric pixel-art city map.
Image 1 = the current pixel-art drawing (context). Image 2 = the aerial photo of exactly the same area, same camera. Image 3 = a mask: WHITE marks the only area you may change.
{extra_refs}
Task: redraw ONLY the white-masked area so that it faithfully matches the photo (Image 2): same building footprints, heights, roof shapes, streets and open ground, at the same scale and camera angle. Everything outside the mask must stay pixel-identical to Image 1.
Style: identical to Image 1 — hard-edged pixel art, flat colours, the same palette, same light from the top-left, no photographic texture, no blur, no text.
{note}
Output the full image at the same framing as Image 1."""

def load_env_paths(sq):
    i, j = sq
    return ROOT / f'renders/sq_{i}_{j}.png', ROOT / f'pixels_pro/sq_{i}_{j}.png'

def box_to_uv(sq, box):
    i, j = sq; x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    u = i * W + (cx / PX - 0.5) * W
    Y = j * W + (0.5 - cy / PX) * W
    return u, Y / SINP, max(x1 - x0, y1 - y0) * W / PX

def render_closeup(sq, box, out_dir):
    """Render the boxed area with the same camera but a narrow frustum: a sharp 3D close-up of the real geometry."""
    u, v, wm = box_to_uv(sq, box)
    wm = max(wm * 1.15, 120)
    g = {**GRID, 'W': wm, 'sse': 2, 'squares': [{'i': 0, 'j': 0, 'u': u, 'v': v}]}
    gp = out_dir / 'closeup_grid.json'; json.dump(g, open(gp, 'w'))
    subprocess.run(['node', str(ROOT / 'render/render.mjs'), '--grid', str(gp), '--out', str(out_dir), '--force'], check=True, cwd=ROOT, timeout=900)
    return out_dir / 'sq_0_0.png'

def context_region(box, margin=0.35, min_side=640):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    side = max(min_side, int(max(bw, bh) * (1 + 2 * margin)))
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    cx0 = min(max(0, cx - side // 2), PX - side); cy0 = min(max(0, cy - side // 2), PX - side)
    return (cx0, cy0, cx0 + side, cy0 + side)

def to_b64(im, side=1024):
    im = im.convert('RGB').resize((side, side), Image.LANCZOS if im.width > side else Image.NEAREST)
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()

def generate_region(art_crop, photo_crop, mask_img, note, refs, closeup=None):
    parts = [{'inline_data': {'mime_type': 'image/png', 'data': to_b64(art_crop)}},
             {'inline_data': {'mime_type': 'image/png', 'data': to_b64(photo_crop)}},
             {'inline_data': {'mime_type': 'image/png', 'data': to_b64(mask_img)}}]
    extra = []
    k = 4
    if closeup is not None:
        parts.append({'inline_data': {'mime_type': 'image/png', 'data': to_b64(closeup)}})
        extra.append(f'Image {k} = a sharp 3D close-up of the masked building(s) from the same camera: use it for exact shapes, towers, domes, roof colours.'); k += 1
    for r in refs[:3]:
        parts.append({'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(Path(r).read_bytes()).decode()}})
        extra.append(f'Image {k} = a real photograph of the building at this location; match its architecture (style, towers, materials, colours) — but keep the map camera angle and scale.'); k += 1
    prompt = REFINE_PROMPT.format(extra_refs='\n'.join(extra), note=('The problem with the current drawing in the masked area, which you must FIX: ' + note) if note else '')
    parts.append({'text': prompt})
    body = {'contents': [{'parts': parts}], 'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '1:1', 'imageSize': '1K'}}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.MODEL}:generateContent',
                                 data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r: res = json.load(r)
            for p in res['candidates'][0]['content']['parts']:
                if 'inlineData' in p: return Image.open(io.BytesIO(base64.b64decode(p['inlineData']['data']))).convert('RGB')
            raise RuntimeError('no image: ' + json.dumps(res)[:300])
        except urllib.error.HTTPError as e:
            print('  HTTP', e.code, e.read().decode()[:200], file=sys.stderr)
            if e.code in (429, 500, 503) and attempt < 3: time.sleep(10 * (attempt + 1)); continue
            raise

def judge_region(photo_crop, result_crop, mask_img, note):
    prompt = ("Image 1: aerial photo. Image 2: pixel-art redrawing of the same area. Image 3: mask — judge ONLY the white area. "
              "Score 0-10 how well the masked area in image 2 matches the real buildings/ground in image 1 (footprints, heights, roof and tower shapes, open ground vs buildings). "
              + (f"The reported problem with the previous drawing was: '{note}'. Check that this problem is now fixed (a fixed problem scores high). " if note else '') +
              "Ignore colour and drawing style. Reply ONLY JSON: {\"score\": number, \"issues\": [..]}")
    body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/png', 'data': to_b64(photo_crop, 768)}},
                                    {'inline_data': {'mime_type': 'image/png', 'data': to_b64(result_crop, 768)}},
                                    {'inline_data': {'mime_type': 'image/png', 'data': to_b64(mask_img, 768)}}, {'text': prompt}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.1}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.JUDGE_MODEL}:generateContent',
                                 data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
        j = json.loads(res['candidates'][0]['content']['parts'][0]['text']); return float(j.get('score', 0)), j.get('issues', [])
    except Exception as e:
        print('  judge failed', str(e)[:120], file=sys.stderr); return 5.0, ['judge failed']

def refine(sq, box, note='', poi=None, closeup=False, n=2, dry=False, source='manual'):
    render_p, art_p = load_env_paths(sq)
    render, art = Image.open(render_p).convert('RGB'), Image.open(art_p).convert('RGB')
    C = context_region(box)
    art_crop, photo_crop = art.crop(C), render.crop(C)
    mask = Image.new('RGB', art_crop.size, 'black'); ImageDraw.Draw(mask).rectangle((box[0] - C[0], box[1] - C[1], box[2] - C[0], box[3] - C[1]), fill='white')
    refs = sorted(str(p) for p in (ROOT / 'data/refs' / poi).glob('*.jpg')) if poi else []
    work = ROOT / 'refine_work' / f'sq_{sq[0]}_{sq[1]}_{int(time.time())}'; work.mkdir(parents=True, exist_ok=True)
    cu = None
    if closeup:
        try:
            cu_path = render_closeup(sq, box, work); cu = Image.open(cu_path).convert('RGB')
        except Exception as e: print('  closeup render failed:', str(e)[:200], file=sys.stderr)
    art_crop.save(work / 'art_crop.png'); photo_crop.save(work / 'photo_crop.png'); mask.save(work / 'mask.png')
    if dry: print('dry run, inputs in', work); return None
    cands = []
    for k in range(n):
        res = generate_region(art_crop, photo_crop, mask, note, refs, cu).resize(art_crop.size, Image.LANCZOS)
        # HARD CONSTRAINT: only the box changes
        merged = art_crop.copy(); merged.paste(res.crop((box[0]-C[0], box[1]-C[1], box[2]-C[0], box[3]-C[1])), (box[0]-C[0], box[1]-C[1]))
        js, issues = judge_region(photo_crop, merged, mask, note)
        merged.save(work / f'cand{k}_{js:.1f}.png'); cands.append((js, merged, issues)); print(f'  cand {k}: judge={js} {issues[:2]}')
    cands.sort(key=lambda c: -c[0]); js, best, issues = cands[0]
    hist = ROOT / 'pixels_pro/history'; hist.mkdir(exist_ok=True)
    art.save(hist / f'sq_{sq[0]}_{sq[1]}_{int(time.time())}.png')
    out = art.copy(); out.paste(best, (C[0], C[1])); out.save(art_p)
    rec = {'sq': sq, 'box': box, 'note': note, 'poi': poi, 'closeup': closeup, 'n': len(cands), 'judge': js, 'judges': [c[0] for c in cands], 'usd': round(0.134 * len(cands), 3), 'source': source, 'ts': time.time(), 'work': str(work)}
    with open(ROOT / 'pixels_pro/refine_log.jsonl', 'a') as f: f.write(json.dumps(rec) + '\n')
    print(f'refined sq {sq} box {box}: judge {js} (${rec["usd"]})')
    return rec

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--sq'); ap.add_argument('--box'); ap.add_argument('--note', default=''); ap.add_argument('--poi')
    ap.add_argument('--closeup', action='store_true'); ap.add_argument('--n', type=int, default=2); ap.add_argument('--dry', action='store_true')
    ap.add_argument('--queue')
    a = ap.parse_args()
    if a.queue:
        jobs = json.load(open(a.queue))
        for jb in jobs:
            if jb.get('done'): continue
            refine(tuple(jb['sq']), tuple(jb['box']), jb.get('note', ''), jb.get('poi'), jb.get('closeup', False), jb.get('n', 2), source=jb.get('source', 'queue'))
            jb['done'] = True; json.dump(jobs, open(a.queue, 'w'), indent=1)
    else:
        refine(tuple(map(int, a.sq.split(','))), tuple(map(int, a.box.split(','))), a.note, a.poi, a.closeup, a.n, a.dry)
