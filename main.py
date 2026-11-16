#!/usr/bin/env python3
"""The Wave That Caught the Moon.

A procedural 1024x1024 image for make.fun ai-excited-01: a giant
turquoise wave curls around a golden harvest moon, spray bursting
from its lip. Pure standard library; the PNG encoder is written
by hand. Deterministic: one seeded RNG drives every random draw.

Run:  MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import math
import os
import random
import struct
import zlib

WIDTH = 1024
HEIGHT = 1024
SEED = 20261116

SKY_RAMP = [(0, (10, 16, 48)), (500, (16, 30, 64)), (780, (22, 41, 77))]
SEA_RAMP = [(780, (16, 42, 66)), (900, (10, 28, 48)), (1024, (6, 20, 38))]
WAVE_RAMP = [(175, (64, 210, 225)), (350, (30, 160, 190)),
             (600, (16, 105, 135)), (1024, (8, 45, 66))]

MOON_CENTER = (690, 566)
MOON_RADIUS = 110
MOON_HALO = 300

WAVE_OUTLINE = [
    (0, 1024), (0, 780), (60, 560), (170, 380), (300, 250),
    (450, 185), (600, 175), (720, 205), (800, 260), (835, 340),
    (815, 420), (760, 465), (680, 490), (580, 520), (480, 570),
    (400, 650), (375, 780), (350, 900), (330, 1024),
]

CREST_LINE = [(450, 185), (600, 175), (720, 205), (800, 260),
              (835, 340), (815, 420)]

WALL_LINE = [(815, 420), (760, 465), (680, 490), (580, 520),
             (480, 570), (400, 650), (370, 720)]

CRATERS = [(650, 526, 18), (730, 606, 14), (700, 526, 10),
           (665, 626, 12), (740, 546, 8)]


# ---------------------------------------------------------------- helpers

def _mix(c0, c1, t):
    """Linear blend of two RGB colors."""
    return (round(c0[0] + (c1[0] - c0[0]) * t),
            round(c0[1] + (c1[1] - c0[1]) * t),
            round(c0[2] + (c1[2] - c0[2]) * t))


def _ramp(stops, y):
    """Piecewise-linear vertical gradient; clamps past the ends."""
    if y <= stops[0][0]:
        return stops[0][1]
    for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
        if y <= y1:
            return _mix(c0, c1, (y - y0) / (y1 - y0))
    return stops[-1][1]


def _set_px(rows, x, y, color):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        rows[y][x * 3:x * 3 + 3] = bytes(color)


def _h_run(rows, x, y, length, height, color):
    """Horizontal dash, clipped to the canvas."""
    x0 = max(0, x)
    x1 = min(WIDTH, x + length)
    if x1 <= x0 or y < 0 or y >= HEIGHT:
        return
    blob = bytes(color) * (x1 - x0)
    for yy in range(y, min(HEIGHT, y + height)):
        rows[yy][x0 * 3:x1 * 3] = blob


def _disc(rows, cx, cy, radius, color):
    """Filled circle, clipped to the canvas."""
    r = int(round(radius))
    if r < 0:
        return
    blob = bytes(color)
    for yy in range(cy - r, cy + r + 1):
        if yy < 0 or yy >= HEIGHT:
            continue
        dy = yy - cy
        half = int(math.sqrt(max(0, r * r - dy * dy)))
        x0 = max(0, cx - half)
        x1 = min(WIDTH, cx + half + 1)
        if x1 > x0:
            rows[yy][x0 * 3:x1 * 3] = blob * (x1 - x0)


def _chaikin_closed(points, iterations):
    """Chaikin corner-cutting on a closed polygon."""
    pts = [(float(x), float(y)) for x, y in points]
    for _ in range(iterations):
        out = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        pts = out
    return pts


def _chaikin_open(points, iterations):
    """Chaikin corner-cutting on an open polyline; endpoints kept."""
    pts = [(float(x), float(y)) for x, y in points]
    for _ in range(iterations):
        out = [pts[0]]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        out.append(pts[-1])
        pts = out
    return pts


def _densify(points, step):
    """Walk a polyline, emitting a sample about every `step` pixels."""
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(dist / step))
        for i in range(n):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    out.append(points[-1])
    return out


def _fill_polygon(rows, points, row_fill):
    """Scanline fill of a closed polygon. Returns per-row fill spans."""
    edges = []
    n = len(points)
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        if y0 != y1:
            edges.append((x0, y0, x1, y1))
    spans = {}
    for y in range(HEIGHT):
        xs = []
        for x0, y0, x1, y1 in edges:
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
        xs.sort()
        row_spans = []
        for i in range(0, len(xs) - 1, 2):
            x0 = max(0, int(math.ceil(xs[i])))
            x1 = min(WIDTH, int(xs[i + 1]))
            if x1 > x0:
                rows[y][x0 * 3:x1 * 3] = row_fill[y] * (x1 - x0)
                row_spans.append((x0, x1))
        spans[y] = row_spans
    return spans


def _in_spans(spans, x, y):
    for x0, x1 in spans.get(y, ()):  # row spans are few; linear scan is fine
        if x0 <= x < x1:
            return True
    return False


def _disc_masked(rows, spans, cx, cy, radius, color):
    """Filled circle clipped to the wave's fill spans."""
    r = int(round(radius))
    if r < 0:
        return
    blob = bytes(color)
    for yy in range(cy - r, cy + r + 1):
        if yy < 0 or yy >= HEIGHT:
            continue
        dy = yy - cy
        half = int(math.sqrt(max(0, r * r - dy * dy)))
        x0 = max(0, cx - half)
        x1 = min(WIDTH, cx + half + 1)
        for sx0, sx1 in spans.get(yy, ()):
            ix0, ix1 = max(x0, sx0), min(x1, sx1)
            if ix1 > ix0:
                rows[yy][ix0 * 3:ix1 * 3] = blob * (ix1 - ix0)


# ---------------------------------------------------------------- layers

def _draw_sky(rows, rng):
    for y in range(780):
        rows[y][:] = bytes(_ramp(SKY_RAMP, y)) * WIDTH
    for _ in range(260):
        x = rng.randrange(WIDTH)
        y = rng.randrange(740)
        roll = rng.random()
        if roll < 0.70:
            v = rng.randint(90, 150)
            _set_px(rows, x, y, (v, v, v))
        elif roll < 0.93:
            v = rng.randint(170, 220)
            color = (v, v, min(255, v + 15))
            _set_px(rows, x, y, color)
            _set_px(rows, x + 1, y, color)
            _set_px(rows, x, y + 1, color)
            _set_px(rows, x + 1, y + 1, color)
        else:
            _set_px(rows, x, y, (255, 255, 255))
            arm = (220, 225, 255)
            for d in (1, 2):
                _set_px(rows, x + d, y, arm)
                _set_px(rows, x - d, y, arm)
                _set_px(rows, x, y + d, arm)
                _set_px(rows, x, y - d, arm)


def _draw_sea(rows, rng):
    for y in range(780, HEIGHT):
        rows[y][:] = bytes(_ramp(SEA_RAMP, y)) * WIDTH
    _h_run(rows, 360, 779, WIDTH - 360, 1, (70, 120, 150))
    _h_run(rows, 360, 780, WIDTH - 360, 1, (50, 95, 125))
    for _ in range(110):  # gold moon-path shimmer
        x = rng.randrange(580, 841)
        y = rng.randrange(790, 1016)
        length = rng.randint(8, 55)
        bright = rng.randint(120, 235)
        color = (bright, int(0.75 * bright), int(0.35 * bright))
        _h_run(rows, x, y, length, rng.randint(1, 2), color)
    for _ in range(30):  # whitecaps
        x = rng.randrange(400, 1001)
        y = rng.randrange(800, 1001)
        _h_run(rows, x, y, rng.randint(5, 22), 1, (200, 230, 240))


def _draw_moon(rows):
    cx, cy = MOON_CENTER
    for y in range(cy - MOON_HALO, cy + MOON_HALO + 1):
        row = rows[y]
        for x in range(cx - MOON_HALO, cx + MOON_HALO + 1):
            d = math.hypot(x - cx, y - cy)
            if d <= MOON_RADIUS:
                t = (d / MOON_RADIUS) ** 1.6
                color = _mix((255, 243, 196), (245, 166, 35), t)
                row[x * 3:x * 3 + 3] = bytes(color)
            elif d <= MOON_HALO:
                k = ((1 - (d - MOON_RADIUS) / 190) ** 2) * 0.5
                i = x * 3
                bg = (row[i], row[i + 1], row[i + 2])
                color = _mix(bg, (255, 196, 90), k)
                row[i:i + 3] = bytes(color)
    for ccx, ccy, cr in CRATERS:
        _disc(rows, ccx, ccy, cr, (238, 186, 84))


def _draw_wave(rows):
    smooth = _chaikin_closed(WAVE_OUTLINE, 2)
    row_fill = [bytes(_ramp(WAVE_RAMP, y)) for y in range(HEIGHT)]
    return _fill_polygon(rows, smooth, row_fill)


def _draw_tube_shadow(rows, spans):
    """Three dark bands hugging the inside of the barrel wall.

    The wall slopes down-left, so a literal straight-down offset
    would land outside the wave; instead each band follows the wall
    offset along the inward normal, which keeps it on the wave face.
    """
    wall = _densify(_chaikin_open(WALL_LINE, 2), 3.0)
    n = len(wall)
    for offset, factor in ((38, 0.90), (26, 0.75), (13, 0.60)):
        for i, (x, y) in enumerate(wall):
            x0, y0 = wall[max(0, i - 1)]
            x1, y1 = wall[min(len(wall) - 1, i + 1)]
            tx, ty = x1 - x0, y1 - y0
            length = math.hypot(tx, ty) or 1.0
            tx, ty = tx / length, ty / length
            nx, ny = -ty, tx  # one of the two normals
            px, py = int(round(x + nx * 20)), int(round(y + ny * 20))
            if not _in_spans(spans, px, py):  # wrong side: flip
                nx, ny = -nx, -ny
            cx = int(round(x + nx * offset))
            cy = int(round(y + ny * offset))
            base = _ramp(WAVE_RAMP, cy)
            color = (int(base[0] * factor), int(base[1] * factor),
                     int(base[2] * factor))
            # Taper the band toward the wall's lower end so the shadow
            # fades out instead of ending in blunt rounded caps.
            radius = 7 - 4 * (i / max(1, n - 1))
            _disc_masked(rows, spans, cx, cy, radius, color)


def _draw_crest_highlight(rows, crest):
    n = len(crest)
    for i, (x, y) in enumerate(crest):
        t = i / max(1, n - 1)
        _disc(rows, int(round(x)), int(round(y)), 16 - 9 * t, (170, 240, 250))
    for i, (x, y) in enumerate(crest):
        t = i / max(1, n - 1)
        _disc(rows, int(round(x)), int(round(y)), 6 - 3 * t, (232, 252, 255))


def _draw_foam(rows, rng, crest):
    white = (255, 255, 255)
    pale = (225, 248, 255)
    for _ in range(170):  # foam blobs along the crest
        x, y = rng.choice(crest)
        jx = x + rng.uniform(-14, 14)
        jy = y + rng.uniform(-12, 12)
        color = white if rng.random() < 0.6 else pale
        _disc(rows, int(round(jx)), int(round(jy)), rng.uniform(2, 9), color)
    for _ in range(60):  # dense foam at the lip tip
        jx = 815 + rng.uniform(-35, 35)
        jy = 420 + rng.uniform(-30, 30)
        _disc(rows, int(round(jx)), int(round(jy)), rng.uniform(2, 9), white)
    for _ in range(280):  # ballistic spray bursting off the lip
        vx = rng.uniform(60, 320)
        vy = rng.uniform(-420, -120)
        t = rng.random()
        x = 800 + vx * (t ** 0.7)
        y = 400 + vy * (t ** 0.7) + 260 * t * t
        b = round(255 - 120 * t)
        _set_px(rows, int(round(x)), int(round(y)), (b, b, b))
    for _ in range(50):  # short streaks near the lip
        x = 815 + rng.uniform(-70, 60)
        y = 420 + rng.uniform(-50, 50)
        _h_run(rows, int(round(x)), int(round(y)), rng.randint(4, 14), 1,
               (240, 250, 255))
    for _ in range(40):  # droplets in the tube mouth
        x = rng.randrange(700, 821)
        y = rng.randrange(440, 561)
        _disc(rows, x, y, rng.randint(1, 2), (230, 245, 250))
    for _ in range(60):  # foam dashes at the wave base
        x = rng.randrange(0, 341)
        y = rng.randrange(950, 1021)
        _h_run(rows, x, y, rng.randint(6, 20), rng.randint(1, 2),
               (225, 242, 248))


# ---------------------------------------------------------------- PNG output

def _png_bytes(rows):
    raw = bytearray()
    prev = bytes(WIDTH * 3)
    for i, row in enumerate(rows):
        if i == 0:
            raw.append(0)  # filter None on the first row
            raw += row
        else:
            raw.append(2)  # filter Up on every other row
            raw += bytes((c - p) & 0xFF for c, p in zip(row, prev))
        prev = bytes(row)
    payload = zlib.compress(bytes(raw), 6)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) +
            chunk(b"IDAT", payload) + chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(SEED)
    rows = [bytearray(WIDTH * 3) for _ in range(HEIGHT)]

    _draw_sky(rows, rng)
    _draw_sea(rows, rng)
    _draw_moon(rows)
    spans = _draw_wave(rows)
    _draw_tube_shadow(rows, spans)
    crest = _densify(_chaikin_open(CREST_LINE, 2), 2.0)
    _draw_crest_highlight(rows, crest)
    _draw_foam(rows, rng, crest)

    data = _png_bytes(rows)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print(f"wrote {path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
