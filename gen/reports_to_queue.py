#!/usr/bin/env python3
"""Turn map reports (from the artifact's shared db, dumped as JSON files, or pasted report objects)
into refine.py jobs.  usage: reports_to_queue.py <reports_dir_or_json> [--out build/refine_queue.json]
Accepts: a directory of <doc_id>.json files (read_db --out_dir), a JSON list, or a single report object."""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SUFFIX = {'invented_landmark': ' Remove the invented landmark entirely and draw the ordinary buildings and streets exactly as the photo shows.',
          'wrong_architecture': ' Match the real architecture shown in the close-up.', 'wrong_size': ' Redraw at the true size and height, matching the close-up.',
          'wrong_ground': ' Draw bare dirt or rooftops as in the photo, not grass.', 'missing_structure': ' Add the structure the photo shows there.'}
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('--out', default='build/refine_queue.json'); a = ap.parse_args()
src = Path(a.src)
if src.is_dir():
    reps = []
    for f in sorted(src.rglob('*.json')):
        d = json.load(open(f)); d.setdefault('_id', f.stem); reps.append(d)
else:
    d = json.load(open(src)); reps = d if isinstance(d, list) else [d]
outp = ROOT / a.out; jobs = json.load(open(outp)) if outp.exists() else []
seen = {(tuple(j['sq']), tuple(j['box'])) for j in jobs}
n = 0
for r in reps:
    if r.get('status') == 'done' or 'sq' not in r or 'box' not in r: continue
    key = (tuple(r['sq']), tuple(r['box']))
    if key in seen: continue
    x0, y0, x1, y1 = r['box']
    if x1 - x0 < 160: c = (x0 + x1) // 2; x0, x1 = max(0, c - 80), min(2048, c + 80)
    if y1 - y0 < 160: c = (y0 + y1) // 2; y0, y1 = max(0, c - 80), min(2048, c + 80)
    t = r.get('type', 'other')
    jobs.append({'sq': list(r['sq']), 'box': [x0, y0, x1, y1], 'type': t, 'note': (r.get('note') or '') + SUFFIX.get(t, ''),
                 'closeup': t in ('wrong_architecture', 'wrong_size', 'missing_structure'), 'n': 2, 'source': 'map', 'report_id': r.get('_id'), 'done': False}); n += 1
json.dump(jobs, open(outp, 'w'), indent=1, ensure_ascii=False)
print(f'{n} new jobs, {len(jobs)} total in {outp}')
