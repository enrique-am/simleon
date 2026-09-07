#!/usr/bin/env python3
"""Rank audited seam windows by an OBJECTIVE cross-border discontinuity metric (free, no API),
then keep only the worst N for repair by marking the rest done.

usage: seam_rank.py --queue build/seams.json --keep 60
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import seams as S

ap = argparse.ArgumentParser()
ap.add_argument('--queue', default='build/seams.json')
ap.add_argument('--keep', type=int, default=60)
a = ap.parse_args()
Q = json.load(open(S.ROOT / a.queue))

cache = {}
def art(i, j):
    if (i, j) not in cache: cache[(i, j)] = S.art(i, j)
    return cache[(i, j)]

def score(r):
    ta, tb, o, k = tuple(r['a']), tuple(r['b']), r['o'], r['k']
    win = np.asarray(S.window(ta, tb, o, k, art), dtype=np.float32)
    m = S.WIN // 2
    if o == 'v':
        L, R = win[:, m-64:m, :], win[:, m:m+64, :]
        edge = np.abs(win[:, m, :] - win[:, m-1, :]).mean()
    else:
        L, R = win[m-64:m, :, :], win[m:m+64, :, :]
        edge = np.abs(win[m, :, :] - win[m-1, :, :]).mean()
    # brightness/colour jump + texture-density jump across the border
    dmean = np.abs(L.reshape(-1,3).mean(0) - R.reshape(-1,3).mean(0)).mean()
    dstd  = np.abs(L.reshape(-1,3).std(0)  - R.reshape(-1,3).std(0)).mean()
    return round(float(0.5*edge + 1.0*dmean + 1.0*dstd), 3)

for r in Q:
    if r.get('done'): r.setdefault('objective', 0.0); continue
    r['objective'] = score(r)

pend = [r for r in Q if not r.get('done')]
pend.sort(key=lambda r: -r['objective'])
keep = set(id(r) for r in pend[:a.keep])
for r in pend:
    if id(r) not in keep:
        r['done'] = True; r['skipped'] = 'below objective cut'
json.dump(Q, open(S.ROOT / a.queue, 'w'), indent=1, ensure_ascii=False)
sel = pend[:a.keep]
print(f'{len(pend)} pending windows; keeping worst {len(sel)} (objective {sel[-1]["objective"] if sel else 0} .. {sel[0]["objective"] if sel else 0}) ~${0.268*len(sel):.2f}')
