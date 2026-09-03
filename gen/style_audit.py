#!/usr/bin/env python3
"""Style audit: rate every square's rendering style (dense pixel-art vs flat vector illustration) with a vision model,
using two 600px crops per square, so outliers can be regenerated. Writes build/style_audit.json.  Cost ≈ $0.002/square."""
import json, base64, io, sys, urllib.request
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent)); import pixelate as P
ROOT = P.ROOT
PROMPT = ("These are two crops from the same tile of an isometric pixel-art city map. Rate the DRAWING STYLE only, not the content. "
          "pixel_score 0-10: 10 = dense retro pixel-art sprites (visible hard pixels, textured roofs, tiny windows, crisp outlines, saturated), "
          "0 = smooth flat vector illustration (large uniform colour fills, soft or no outlines, little texture, washed-out). "
          "Also give saturation 0-10 (0 pale, 10 vivid) and outline 0-10 (0 none, 10 strong dark outlines). "
          "Reply ONLY JSON: {\"pixel_score\": n, \"saturation\": n, \"outline\": n, \"label\": \"pixel_dense|mixed|flat_vector\"}")
def b64(im):
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True); return base64.b64encode(buf.getvalue()).decode()
def audit(path):
    im = Image.open(path).convert('RGB')
    crops = [im.crop((600, 600, 1200, 1200)), im.crop((1200, 300, 1800, 900))]
    body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/png', 'data': b64(c)}} for c in crops] + [{'text': PROMPT}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.0}}
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{P.JUDGE_MODEL}:generateContent', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': P.KEY})
    with urllib.request.urlopen(req, timeout=120) as r: res = json.load(r)
    return json.loads(res['candidates'][0]['content']['parts'][0]['text'])
if __name__ == '__main__':
    out = {}
    for f in sorted((ROOT / 'pixels_pro').glob('sq_*.png')):
        try: out[f.stem[3:]] = audit(f)
        except Exception as e: out[f.stem[3:]] = {'error': str(e)[:100]}
        print(f.stem[3:], out[f.stem[3:]])
    json.dump(out, open(ROOT / 'build/style_audit.json', 'w'), indent=1)
