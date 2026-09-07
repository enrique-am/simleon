#!/usr/bin/env python3
"""Relative style audit: how close is each square's drawing style to the STANDARD square (-1,1)? 0-10. Writes build/style_match.json."""
import json, base64, io, sys, urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent)); import pixelate as P
ROOT = P.ROOT
std = sys.argv[1] if len(sys.argv) > 1 else '-1_1'
def crops(path):
    im = Image.open(path).convert('RGB'); return [im.crop((600, 600, 1200, 1200)), im.crop((1300, 200, 1900, 800))]
def b64(im):
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()
PROMPT = ("Images 1-2 are crops of the STANDARD tile of an isometric pixel-art city map. Images 3-4 are crops of ANOTHER tile. "
          "Ignore what is depicted; compare only the DRAWING STYLE: pixel density and sprite detail, outline weight, roof textures, colour saturation and palette, tree/car sprite style, lighting and contrast. "
          "similarity 0-10 (10 = indistinguishable style, 5 = clearly a different rendering mode, e.g. flatter/paler/smoother). "
          "Reply ONLY JSON: {\"similarity\": n, \"differences\": [short strings]}")
sp = crops(ROOT / f'pixels_pro/sq_{std}.png')
out = {}
for f in sorted((ROOT / 'pixels_pro').glob('sq_*.png')):
    k = f.stem[3:]
    if k == std: out[k] = {'similarity': 10, 'differences': []}; continue
    parts = [{'inline_data': {'mime_type': 'image/png', 'data': b64(c)}} for c in sp + crops(f)] + [{'text': PROMPT}]
    body = {'contents': [{'parts': parts}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.0}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.JUDGE_MODEL}:generateContent', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
        out[k] = json.loads(res['candidates'][0]['content']['parts'][0]['text'])
    except Exception as e: out[k] = {'error': str(e)[:100]}
    print(k, out[k].get('similarity'), (out[k].get('differences') or [''])[0][:80])
json.dump(out, open(ROOT / 'build/style_match.json', 'w'), indent=1, ensure_ascii=False)
