#!/usr/bin/env python3
"""Auto-detect suspect regions in finished squares: a vision model compares photo vs pixel art and returns
bounding boxes of invented landmarks, missing structures, wrong ground cover, etc. Writes a refine.py queue.

usage: detect.py [--only "-1,0;0,1"] [--out build/refine_queue.json] [--min-sev 3] [--model gemini-flash-latest]
"""
import argparse, base64, io, json, sys, time, urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import pixelate as P

ROOT = P.ROOT; PX = 2048
PROMPT = """Image 1 is an aerial photo of part of a city; Image 2 is a pixel-art redrawing that should preserve the layout exactly.
Find every place where Image 2 does NOT match Image 1 in a way a viewer would notice at a glance. Look especially for:
- invented landmarks: a church, dome, tower, stadium, plaza or park in Image 2 that does not exist in Image 1
- a real landmark drawn with the wrong architecture (e.g. a white gothic church drawn as a golden baroque one)
- buildings much taller or larger than in the photo; missing streets; blocks replaced by parks/lawns where the photo shows dirt or roofs
Ignore colour palette, drawing style, small roof details and tree density.
Reply ONLY with JSON: {"regions":[{"box":[ymin,xmin,ymax,xmax] (integers 0-1000, on Image 2), "type":"invented_landmark|wrong_architecture|wrong_size|missing_structure|wrong_ground", "severity":1-5, "note":"what is wrong and what the photo actually shows there"}]}
Return at most 4 regions, highest severity first. Return {"regions":[]} if it matches well."""

def detect(sq, model):
    i, j = sq
    photo = Image.open(ROOT / f'renders/sq_{i}_{j}.png'); art = Image.open(ROOT / f'pixels_pro/sq_{i}_{j}.png')
    def b64(im):
        im = im.convert('RGB').resize((1024, 1024), Image.BOX); buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()
    body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/png', 'data': b64(photo)}}, {'inline_data': {'mime_type': 'image/png', 'data': b64(art)}}, {'text': PROMPT}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.1}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r: res = json.load(r)
            return json.loads(res['candidates'][0]['content']['parts'][0]['text']).get('regions', [])
        except urllib.error.HTTPError as e:
            print('  HTTP', e.code, file=sys.stderr); time.sleep(8 * (attempt + 1))
        except Exception as e:
            print('  detect failed', str(e)[:150], file=sys.stderr); return []
    return []

def to_job(sq, r, pad=0.12):
    ymin, xmin, ymax, xmax = [max(0, min(1000, v)) / 1000 for v in r['box']]
    w, h = xmax - xmin, ymax - ymin
    x0 = int(max(0, xmin - w * pad) * PX); x1 = int(min(1, xmax + w * pad) * PX)
    y0 = int(max(0, ymin - h * pad) * PX); y1 = int(min(1, ymax + h * pad) * PX)
    # enforce a minimum box so the model has something to work with
    if x1 - x0 < 200: c = (x0 + x1) // 2; x0, x1 = max(0, c - 100), min(PX, c + 100)
    if y1 - y0 < 200: c = (y0 + y1) // 2; y0, y1 = max(0, c - 100), min(PX, c + 100)
    suffix = {'invented_landmark': ' Remove the invented landmark entirely and draw the ordinary low buildings and streets exactly as the photo shows.',
              'wrong_ground': ' Draw bare tan/brown dirt or rooftops as in the photo, not grass.',
              'wrong_size': ' Redraw the building at its true size and height relative to the surrounding houses, matching the close-up.',
              'wrong_architecture': ' Match the real architecture shown in the close-up: shape of towers, domes or spires, roof and wall colours.',
              'missing_structure': ' Add the structure that the photo shows there, at the same footprint and height.'}.get(r.get('type'), '')
    return {'sq': list(sq), 'box': [x0, y0, x1, y1], 'type': r.get('type'), 'severity': r.get('severity'),
            'note': r.get('note', '') + suffix, 'closeup': r.get('type') in ('wrong_architecture', 'wrong_size'), 'n': 2, 'source': 'detect', 'done': False}

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--only'); ap.add_argument('--out', default='build/refine_queue.json')
    ap.add_argument('--min-sev', type=int, default=3); ap.add_argument('--model', default='gemini-flash-latest')
    a = ap.parse_args()
    grid = json.load(open(ROOT / 'grid.json'))
    sqs = [(s['i'], s['j']) for s in grid['squares'] if (ROOT / f"pixels_pro/sq_{s['i']}_{s['j']}.png").exists()]
    if a.only: want = {tuple(map(int, s.split(','))) for s in a.only.split(';')}; sqs = [s for s in sqs if s in want]
    outp = ROOT / a.out
    jobs = json.load(open(outp)) if outp.exists() else []
    report = {}
    for sq in sqs:
        regs = detect(sq, a.model); report[f'{sq[0]},{sq[1]}'] = regs
        keep = [r for r in regs if int(r.get('severity', 0)) >= a.min_sev][:3]
        print(f'sq {sq}: {len(regs)} regions, {len(keep)} queued', [f"{r['type']}({r['severity']})" for r in regs])
        for r in keep: jobs.append(to_job(sq, r))
    json.dump(jobs, open(outp, 'w'), indent=1)
    json.dump(report, open(ROOT / 'build/detect_report.json', 'w'), indent=1, ensure_ascii=False)
    print(f'{len(jobs)} jobs in {outp} (~${0.134*2*sum(1 for j in jobs if not j.get("done")):.2f} to run)')
