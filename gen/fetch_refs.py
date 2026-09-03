#!/usr/bin/env python3
"""Download real-building reference photos for landmarks from Google Places (New) into data/refs/<poi_id>/.
usage: fetch_refs.py [poi_id ...]   (default: every POI in data/pois.json that has a Places id)
Cost: Place Details (photos field) + Place Photo ≈ $0.01–0.02 per landmark; skips landmarks already fetched.
"""
import json, os, sys, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ENV = dict(l.strip().split('=', 1) for l in (ROOT / '.env').read_text().splitlines() if '=' in l)
KEY = ENV['MAPS_API_KEY']
MAX_PHOTOS = int(os.environ.get('REF_PHOTOS', '3'))

pois = json.load(open(ROOT / 'data/pois.json'))
raw = json.load(open(ROOT / 'data/places_raw.json'))
# map poi -> place id by nearest coordinates among raw results
def place_id_for(p):
    best, bd = None, 1e9
    for r in raw:
        d = abs(r['location']['latitude'] - p['lat']) + abs(r['location']['longitude'] - p['lon'])
        if d < bd: best, bd = r, d
    return best['id'] if best and bd < 0.0005 else None

want = sys.argv[1:] or [p['id'] for p in pois]
for p in pois:
    if p['id'] not in want: continue
    out = ROOT / 'data/refs' / p['id']
    if out.exists() and any(out.glob('*.jpg')):
        print('have', p['id']); continue
    pid = place_id_for(p)
    if not pid: print('no place id', p['id']); continue
    req = urllib.request.Request(f'https://places.googleapis.com/v1/places/{pid}', headers={'X-Goog-Api-Key': KEY, 'X-Goog-FieldMask': 'photos'})
    try:
        det = json.load(urllib.request.urlopen(req))
    except Exception as e:
        print('details failed', p['id'], str(e)[:100]); continue
    photos = det.get('photos', [])[:MAX_PHOTOS]
    out.mkdir(parents=True, exist_ok=True)
    for k, ph in enumerate(photos):
        url = f"https://places.googleapis.com/v1/{ph['name']}/media?maxWidthPx=1200&key={KEY}"
        try:
            data = urllib.request.urlopen(url).read()
            (out / f'{k}.jpg').write_bytes(data)
        except Exception as e:
            print('photo failed', p['id'], k, str(e)[:100])
    attrib = [a.get('displayName') for ph in photos for a in ph.get('authorAttributions', [])]
    json.dump({'place_id': pid, 'attributions': attrib}, open(out / 'meta.json', 'w'), ensure_ascii=False)
    print(p['id'], len(photos), 'photos')
