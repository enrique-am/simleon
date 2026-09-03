"""Shared geometry: lon/lat -> mosaic pixel coordinates for the tilted-orthographic grid in grid.json."""
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G = json.load(open(ROOT / 'grid.json'))
W = G['W']; PITCH = abs(G['pitch']); H = math.radians(G['heading']); PX = G['px']
SINP, COSP = math.sin(math.radians(PITCH)), math.cos(math.radians(PITCH))
IS = sorted({s['i'] for s in G['squares']}); JS = sorted({s['j'] for s in G['squares']}, reverse=True)
COLS, ROWS = len(IS), len(JS)
I0, J0 = IS[0], JS[0]          # top-left square
LON0, LAT0, H0 = G['origin']['lon'], G['origin']['lat'], G['origin']['h0']
M_PER_DEG_LAT = 110574.0
M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

# manual calibration offset in metres (screen x, screen y-up), set after eyeballing landmarks on the mosaic
CAL = json.load(open(ROOT / 'build' / 'calibration.json')) if (ROOT / 'build' / 'calibration.json').exists() else {'dx': 0, 'dy': 0}

def lonlat_to_uv(lon, lat):
    e = (lon - LON0) * M_PER_DEG_LON; n = (lat - LAT0) * M_PER_DEG_LAT
    u = e * math.cos(H) - n * math.sin(H)      # along camera-right
    v = e * math.sin(H) + n * math.cos(H)      # along camera-forward (ground)
    return u, v

def uv_to_pixel(u, v, h=0.0, scale=1.0):
    """Mosaic pixel (x right, y down) at full render resolution (PX per square) times `scale`."""
    X = u + CAL['dx']
    Y = v * SINP + h * COSP + CAL['dy']          # screen-up metres
    left = I0 * W - W / 2
    top = J0 * (W / SINP) * SINP + W / 2         # = J0*W + W/2
    x = (X - left) / W * PX
    y = (top - Y) / W * PX
    return x * scale, y * scale

def lonlat_to_pixel(lon, lat, h=0.0, scale=1.0):
    return uv_to_pixel(*lonlat_to_uv(lon, lat), h=h, scale=scale)

def pixel_to_lonlat(x, y, scale=1.0):
    x /= scale; y /= scale
    left = I0 * W - W / 2; top = J0 * W + W / 2
    X = x / PX * W + left - CAL['dx']; Y = top - y / PX * W - CAL['dy']
    u = X; v = Y / SINP
    e = u * math.cos(H) + v * math.sin(H); n = -u * math.sin(H) + v * math.cos(H)
    return LON0 + e / M_PER_DEG_LON, LAT0 + n / M_PER_DEG_LAT

MOSAIC_W, MOSAIC_H = COLS * PX, ROWS * PX

if __name__ == '__main__':
    print('mosaic', MOSAIC_W, MOSAIC_H, 'cols', IS, 'rows', JS)
    for p in json.load(open(ROOT / 'data/pois.json')):
        x, y = lonlat_to_pixel(p['lon'], p['lat'])
        print(f"{p['name'][:40]:40s} {x:7.0f} {y:7.0f}")
