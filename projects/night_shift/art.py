"""nightshift.assets -- every texture, material, model and sound of Night
Shift, made here from code. Original work (GPL-3.0-or-later), no third-party
bytes: textures are drawn texel by texel, signs use a 5x7 pixel font defined
below, sounds are synthesised from sines, squares and seeded noise.

Everything is deterministic: the same source builds the same package bytes.
"""
from __future__ import annotations

import math
import struct

from assetlab import assets as assetlib
from assetlab.dependencies import Library

NS = 'nightshift'
PACKAGE = 'nightshift.assets'
RATE = 22050
ORIGIN = {'provider': 'original', 'creator': 'MegaMod Night Shift', 'license': 'GPL-3.0-or-later',
          'redistribution': 'allowed', 'source_url': None}


def rid(kind, name):
    return f'{NS}:{kind}/{name}'


def prov(what):
    return dict(ORIGIN, made_by=f'projects/night_shift/art.py:{what}')


# ---- textures ----------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h, rgb):
        self.w, self.h = w, h
        self.px = [list(rgb) for _ in range(w * h)]

    def put(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = list(rgb)

    def rect(self, x0, y0, x1, y1, rgb):
        for y in range(y0, y1):
            for x in range(x0, x1):
                self.put(x, y, rgb)

    def border(self, rgb, t=1):
        self.rect(0, 0, self.w, t, rgb); self.rect(0, self.h - t, self.w, self.h, rgb)
        self.rect(0, 0, t, self.h, rgb); self.rect(self.w - t, 0, self.w, self.h, rgb)

    def grain(self, amount, seed):
        s = seed
        for p in self.px:
            s = (s * 1103515245 + 12345) & 0x7FFFFFFF
            d = ((s >> 16) % (2 * amount + 1)) - amount
            for k in range(3):
                p[k] = max(0, min(255, p[k] + d))

    def rgba(self):
        # box_model puts v = 0 at the BOTTOM of a face and MegaMod samples
        # texel row 0 at v = 0: write the rows bottom-up so the canvas's top
        # is the face's top (found on the first screenshot: hazard bands
        # painted at a door's foot showed at its head).
        rows = [self.px[y * self.w:(y + 1) * self.w] for y in range(self.h)]
        return bytes(b for row in reversed(rows) for p in row for b in (p[0], p[1], p[2], 255))


# A 5x7 pixel font: '#' lit, '.' dark. Uppercase, digits and the few marks
# the signs use.
FONT = {
    'A': '.###.#...##...#######...##...##...#', 'B': '####.#...##...#####.#...##...#####.',
    'C': '.###.#...##....#....#....#...#.###.', 'D': '####.#...##...##...##...##...#####.',
    'E': '######....#....####.#....#....#####', 'F': '######....#....####.#....#....#....',
    'G': '.###.#...##....#.####...##...#.####', 'H': '#...##...##...#######...##...##...#',
    'I': '.###...#....#....#....#....#...###.', 'J': '..###...#....#....#.#..#.#..#..##..',
    'K': '#...##..#.#.#..##...#.#..#..#.#...#', 'L': '#....#....#....#....#....#....#####',
    'M': '#...###.###.#.##...##...##...##...#', 'N': '#...##...###..##.#.##..###...##...#',
    'O': '.###.#...##...##...##...##...#.###.', 'P': '####.#...##...#####.#....#....#....',
    'Q': '.###.#...##...##...##.#.##..#..##.#', 'R': '####.#...##...#####.#.#..#..#.#...#',
    'S': '.#####....#.....###.....#....#####.', 'T': '#####..#....#....#....#....#....#..',
    'U': '#...##...##...##...##...##...#.###.', 'V': '#...##...##...##...##...#.#.#...#..',
    'W': '#...##...##...##.#.##.#.##.#.#.#.#.', 'X': '#...##...#.#.#...#...#.#.#...##...#',
    'Y': '#...##...#.#.#...#....#....#....#..', 'Z': '#####....#...#...#...#...#....#####',
    '0': '.###.#...##..###.#.###..##...#.###.', '1': '..#...##....#....#....#....#...###.',
    '2': '.###.#...#....#...#...#...#...#####', '3': '#####...#...#.....#.....##...#.###.',
    '4': '...#...##..#.#.#..#.#####...#....#.', '5': '######....####.....#....##...#.###.',
    '6': '..##..#...#....####.#...##...#.###.', '7': '#####....#...#...#...#....#....#...',
    '8': '.###.#...##...#.###.#...##...#.###.', '9': '.###.#...##...#.####....#...#..##..',
    ' ': '.' * 35, '-': '...............#####...............',
    '+': '.......#....#..#####..#....#.......', '>': '.#.....#.....#.....#...#...#...#...',
    '<': '...#...#...#...#.....#.....#.....#.', ':': '......##...##.......##...##........',
    '.': '..............................##...', '/': '.....#...#...#...#...#.............',
    '!': '..#....#....#....#....#.........#..', '[': '.###..#....#....#....#....#....###.',
    ']': '.###....#....#....#....#....#..###.', '=': '..........#####.....#####..........',
}


assert all(len(g) == 35 for g in FONT.values()), "a glyph is not 5x7"


def text_canvas(lines, fg, bg, scale=1, pad=2, rule=None, width=None):
    """Lines of text centred on a panel; one texel per font pixel times scale."""
    cw, ch = 6 * scale, 8 * scale
    w = width or max(len(s) for s in lines) * cw + 2 * pad
    h = len(lines) * ch + 2 * pad
    c = Canvas(w, h, bg)
    for row, s in enumerate(lines):
        x0 = (w - len(s) * cw) // 2 + scale // 2
        y0 = pad + row * ch
        for i, chh in enumerate(s):
            g = FONT[chh]
            for gy in range(7):
                for gx in range(5):
                    if g[gy * 5 + gx] == '#':
                        c.rect(x0 + i * cw + gx * scale, y0 + gy * scale,
                               x0 + i * cw + (gx + 1) * scale, y0 + (gy + 1) * scale, fg)
    if rule:
        c.border(rule)
    return c


def _pow2(n):
    p = 1
    while p < n:
        p *= 2
    return p


def sign_canvas(lines, fg, bg, rule, scale=1):
    """A sign texture padded out to power-of-two sides."""
    c = text_canvas(lines, fg, bg, scale=scale, rule=None)
    w, h = _pow2(c.w), _pow2(c.h)
    out = Canvas(w, h, bg)
    ox, oy = (w - c.w) // 2, (h - c.h) // 2
    for y in range(c.h):
        for x in range(c.w):
            out.put(ox + x, oy + y, c.px[y * c.w + x])
    out.border(rule)
    return out


def hazard(c, y0, y1, a=(214, 168, 20), b=(26, 26, 26), period=8):
    for y in range(y0, y1):
        for x in range(c.w):
            c.put(x, y, a if ((x + y) // (period // 2)) % 2 == 0 else b)


def tex_door():
    # Models are lit by the scene (about 3x brighter than their texels on
    # the desktop): a door is authored dark so it reads as steel, not paper.
    c = Canvas(32, 32, (36, 38, 42))
    for x in range(0, 32, 8):                 # vertical ribs
        c.rect(x, 0, x + 1, 26, (22, 23, 26))
    hazard(c, 26, 32)
    c.rect(0, 25, 32, 26, (20, 20, 20))
    c.rect(13, 8, 19, 10, (30, 32, 36))       # a view slit
    c.grain(4, 11)
    return c


def tex_button():
    c = Canvas(16, 16, (40, 40, 44))
    c.rect(4, 4, 12, 12, (225, 150, 30))      # amber press plate
    c.rect(5, 5, 11, 7, (255, 205, 90))
    c.border((20, 20, 22))
    return c


def tex_lamp(rgb, hot):
    c = Canvas(16, 16, rgb)
    c.rect(3, 5, 13, 11, hot)
    c.border(tuple(v // 2 for v in rgb))
    return c


def tex_breaker():
    c = Canvas(32, 32, (86, 90, 84))
    hazard(c, 0, 4); hazard(c, 28, 32)
    c.rect(12, 8, 20, 24, (30, 30, 32))       # the lever slot
    c.rect(13, 9, 19, 14, (200, 40, 30))      # the red handle, up = off
    c.rect(4, 8, 9, 11, (170, 170, 160)); c.rect(23, 8, 28, 11, (170, 170, 160))
    c.grain(5, 23)
    return c


def tex_console():
    c = Canvas(32, 32, (38, 42, 46))
    c.rect(3, 3, 29, 20, (8, 26, 14))          # the screen
    for y in range(4, 19, 3):
        c.rect(5, y, 5 + (7 * y) % 20 + 4, y + 1, (60, 210, 110))
    for x in range(4, 28, 5):                 # keys
        c.rect(x, 23, x + 3, 26, (90, 94, 100))
    c.border((20, 22, 24))
    return c


def tex_valve():
    c = Canvas(32, 32, (40, 60, 90))
    cx = cy = 15.5
    for y in range(32):
        for x in range(32):
            r = math.hypot(x - cx, y - cy)
            if 10 <= r < 13 or (r < 13 and (abs(x - cx) < 1.5 or abs(y - cy) < 1.5)):
                c.put(x, y, (190, 40, 36))
    c.rect(13, 13, 19, 19, (120, 120, 126))
    c.grain(4, 31)
    return c


def tex_core():
    c = Canvas(16, 32, (20, 90, 110))
    for y in range(0, 32, 4):
        c.rect(0, y, 16, y + 1, (140, 250, 255))
    c.rect(6, 0, 10, 32, (190, 255, 255))
    c.border((10, 40, 50))
    return c


def tex_shutter():
    c = Canvas(32, 32, (50, 40, 32))
    for y in range(0, 32, 4):
        c.rect(0, y, 32, y + 1, (26, 21, 17))
        c.rect(0, y + 1, 32, y + 2, (68, 55, 44))
    hazard(c, 28, 32, a=(150, 115, 16))
    c.grain(6, 47)
    return c


def tex_plain(rgb, hot=None, seed=0, grain=0):
    c = Canvas(16, 16, rgb)
    if hot:
        c.rect(1, 6, 15, 10, hot)
    if grain:
        c.grain(grain, seed)
    return c


def tex_steam():
    c = Canvas(16, 16, (205, 210, 214))
    c.grain(22, 77)
    return c


def tex_piston():
    c = Canvas(16, 32, (130, 134, 138))
    for y in range(0, 32, 6):
        c.rect(0, y, 16, y + 1, (70, 72, 76))
    hazard(c, 0, 4)
    c.grain(4, 55)
    return c


SIGNS = {
    # name: (lines, fg, bg, rule, half extents of the sign board (x thin))
    'sign_aux': (['AUX POWER', 'MAINTENANCE'], (240, 200, 60), (22, 22, 24), (214, 168, 20), (0.02, 0.62, 0.16)),
    'sign_research': (['RESEARCH WING ACCESS', 'NEEDS COOLANT', '+ SECURITY'], (120, 230, 150), (14, 20, 16),
                      (60, 120, 70), (0.02, 0.7, 0.2)),
    'sign_orders': (['WORK ORDER 0417 - NIGHT SHIFT', 'ANNEX SILENT SINCE 02:10', 'RECOVER THE DATA CORE',
                     'RESEARCH WING'], (230, 230, 220), (30, 34, 40), (150, 150, 140), (0.02, 0.9, 0.3)),
    'sign_lift': (['FREIGHT LIFT', 'TO SURFACE'], (240, 240, 240), (120, 24, 20), (240, 240, 240), (0.02, 0.6, 0.16)),
}


# ---- models --------------------------------------------------------------------------

# model name: (half extents, texture maker)
MODELS = {
    'door_panel': ((0.05, 0.6, 0.6), tex_door),
    'door_button': ((0.14, 0.08, 0.1), tex_button),
    'door_lamp': ((0.08, 0.5, 0.04), lambda: tex_lamp((40, 200, 90), (160, 255, 180))),
    'status_lamp': ((0.04, 0.09, 0.07), lambda: tex_lamp((40, 200, 90), (170, 255, 190))),
    'breaker_box': ((0.06, 0.28, 0.34), tex_breaker),
    'console_desk': ((0.28, 0.55, 0.36), tex_console),
    'valve_wheel': ((0.07, 0.26, 0.26), tex_valve),
    'data_core': ((0.14, 0.14, 0.3), tex_core),
    'shutter': ((0.05, 0.6, 0.6), tex_shutter),
    'ceiling_light': ((0.7, 0.07, 0.03), lambda: tex_plain((255, 240, 205), (255, 255, 240))),
    'alarm_light': ((0.5, 0.08, 0.04), lambda: tex_plain((230, 30, 20), (255, 120, 90))),
    'steam_plume': ((0.45, 0.5, 0.3), tex_steam),
    'pump_piston': ((0.22, 0.22, 0.4), tex_piston),
}


def model_id(name):
    return rid('model', name)


# ---- sounds ---------------------------------------------------------------------------

class Noise:
    def __init__(self, seed):
        self.s = seed

    def __call__(self):
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.s >> 16) / 32768.0 - 1.0


def pcm(samples):
    return b''.join(struct.pack('<h', max(-32767, min(32767, int(v)))) for v in samples)


def env(i, n, attack, release):
    a = min(1.0, i / max(1, attack))
    r = min(1.0, (n - i) / max(1, release))
    return a * r


def snd_click():
    n, nz = RATE * 6 // 100, Noise(3)
    return [9000 * math.exp(-i / 90.0) * (nz() * 0.6 + math.sin(2 * math.pi * 2200 * i / RATE) * 0.4) for i in range(n)]


def snd_locked():
    n = RATE * 35 // 100
    return [5200 * (1 if math.sin(2 * math.pi * 110 * i / RATE) >= 0 else -1) * env(i, n, 60, 900) *
            (1.0 if (i // (RATE // 20)) % 2 == 0 else 0.35) for i in range(n)]


def snd_servo():
    n, nz = RATE * 7 // 10, Noise(9)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.15 * (nz() - lp)
        whine = math.sin(2 * math.pi * (180 + 140 * t) * t)
        out.append(env(i, n, 400, 3000) * (6500 * lp + 2600 * whine))
    return out


def snd_power_on():
    n = RATE * 8 // 10
    out = []
    for i in range(n):
        t = i / RATE
        f = 220 + 520 * min(1.0, t / 0.45)
        v = math.sin(2 * math.pi * f * t) * 0.5 + (math.sin(2 * math.pi * 1320 * t) * math.exp(-(t - 0.5) * 6) if t > 0.5 else 0)
        out.append(7000 * v * env(i, n, 200, 2500))
    return out


def snd_power_down():
    n = RATE * 7 // 10
    return [7000 * math.sin(2 * math.pi * (700 - 560 * min(1.0, i / n)) * i / RATE) * env(i, n, 100, 3000) for i in range(n)]


def snd_generator():
    """A diesel-electric spin-up: a sawtooth rising from 18 to 56 Hz under rumble."""
    n, nz = RATE * 3, Noise(21)
    out, ph, lp = [], 0.0, 0.0
    for i in range(n):
        t = i / RATE
        f = 18 + 38 * min(1.0, t / 2.2)
        ph = (ph + f / RATE) % 1.0
        lp += 0.05 * (nz() - lp)
        out.append(env(i, n, RATE // 3, RATE // 2) * (5500 * (2 * ph - 1) + 9000 * lp + 1800 * math.sin(2 * math.pi * 3 * f * t)))
    return out


def snd_machinery():
    """Distant plant noise: a heavy thud and a ringing pipe."""
    n, nz = RATE * 14 // 10, Noise(33)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.03 * (nz() - lp)
        thud = math.sin(2 * math.pi * 48 * t) * math.exp(-t * 5)
        ring = (math.sin(2 * math.pi * 311 * t) + 0.6 * math.sin(2 * math.pi * 467 * t)) * math.exp(-t * 2.2)
        out.append(env(i, n, 40, 3000) * (12000 * thud + 2200 * ring + 5000 * lp * math.exp(-t)))
    return out


def snd_alarm():
    n = RATE * 13 // 10
    out = []
    for i in range(n):
        t = i / RATE
        f = 620 if (int(t / 0.32) % 2 == 0) else 460
        v = (1 if math.sin(2 * math.pi * f * t) >= 0 else -1) * 0.55 + math.sin(2 * math.pi * f * 2 * t) * 0.2
        out.append(8000 * v * env(i, n, 200, 2000))
    return out


def snd_shock():
    n, nz = RATE * 5 // 10, Noise(41)
    out = []
    for i in range(n):
        t = i / RATE
        burst = 1.0 if (int(t * 37) % 3) else 0.25
        out.append(14000 * nz() * burst * math.exp(-t * 4.5) + 5000 * math.sin(2 * math.pi * 120 * t) * math.exp(-t * 6))
    return out


def snd_steam():
    n, nz = RATE * 9 // 10, Noise(53)
    out, lp = [], 0.0
    for i in range(n):
        lp += 0.45 * (nz() - lp)
        out.append(11000 * lp * env(i, n, 300, 9000))
    return out


def snd_bang():
    """Something heavy falls, far off: a boom and a long metallic ring."""
    n, nz = RATE * 25 // 10, Noise(61)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.02 * (nz() - lp)
        boom = math.sin(2 * math.pi * 38 * t) * math.exp(-t * 3)
        ring = sum(a * math.sin(2 * math.pi * f * t) for f, a in ((183, 1.0), (257, 0.7), (419, 0.5), (733, 0.3))) * math.exp(-t * 1.4)
        out.append(env(i, n, 20, 6000) * (15000 * boom + 2600 * ring + 9000 * lp * math.exp(-t * 2)))
    return out


def snd_knock():
    """Three blows on a steel door, from the other side."""
    n = RATE * 17 // 10
    out = [0.0] * n
    for k, at in enumerate((0.0, 0.45, 0.9)):
        s0 = int(at * RATE)
        for i in range(int(RATE * 0.5)):
            if s0 + i >= n:
                break
            t = i / RATE
            v = math.sin(2 * math.pi * 72 * t) * math.exp(-t * 16) + 0.35 * math.sin(2 * math.pi * 390 * t) * math.exp(-t * 20)
            out[s0 + i] += (16000 - 2500 * k) * v
    return out


def snd_anomaly():
    """A cold, beating chord with breath underneath."""
    n, nz = RATE * 3, Noise(71)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.08 * (nz() - lp)
        chord = sum(math.sin(2 * math.pi * f * t) for f in (146.8, 148.1, 207.7, 311.1)) / 4
        breath = lp * (0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * t))
        out.append(env(i, n, RATE // 2, RATE) * (9000 * chord + 7000 * breath))
    return out


def snd_core():
    """The core unlatches: a deep drop and a falling tone."""
    n = RATE * 22 // 10
    out = []
    for i in range(n):
        t = i / RATE
        v = math.sin(2 * math.pi * 55 * t) * math.exp(-t * 1.5) + 0.5 * math.sin(2 * math.pi * (880 - 600 * min(1, t / 1.8)) * t)
        out.append(9000 * v * env(i, n, 100, 4000))
    return out


def snd_confirm():
    n = RATE * 5 // 10
    out = []
    for i in range(n):
        t = i / RATE
        f = 660 if t < 0.16 else 990
        out.append(6500 * math.sin(2 * math.pi * f * t) * env(i, n, 100, 2000))
    return out


def snd_pump():
    n, nz = RATE * 6 // 10, Noise(87)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.1 * (nz() - lp)
        out.append(env(i, n, 30, 3000) * (11000 * math.sin(2 * math.pi * 64 * t) * math.exp(-t * 7) + 4000 * lp * math.exp(-t * 4)))
    return out


def snd_lift():
    """The freight lift: a bell, then the motor hauling away."""
    n, nz = RATE * 3, Noise(93)
    out, lp = [], 0.0
    for i in range(n):
        t = i / RATE
        lp += 0.04 * (nz() - lp)
        bell = (math.sin(2 * math.pi * 1046 * t) + 0.5 * math.sin(2 * math.pi * 1568 * t)) * math.exp(-t * 3)
        motor = math.sin(2 * math.pi * 90 * t) * min(1.0, t / 0.8)
        out.append(env(i, n, 50, RATE) * (6000 * bell + 4000 * motor + 5000 * lp))
    return out


def snd_shift_over():
    """Surface air after the plant: a slow, open chord."""
    n = RATE * 3
    out = []
    for i in range(n):
        t = i / RATE
        chord = sum(math.sin(2 * math.pi * f * t) for f in (261.6, 392.0, 523.3, 659.3)) / 4
        out.append(9000 * chord * env(i, n, RATE // 3, RATE))
    return out


SOUNDS = {
    'click': snd_click, 'locked': snd_locked, 'door_servo': snd_servo, 'power_on': snd_power_on,
    'power_down': snd_power_down, 'generator': snd_generator, 'machinery': snd_machinery, 'alarm': snd_alarm,
    'shock': snd_shock, 'steam': snd_steam, 'distant_bang': snd_bang, 'knock': snd_knock, 'anomaly': snd_anomaly,
    'core_release': snd_core, 'confirm': snd_confirm, 'pump': snd_pump, 'lift': snd_lift, 'shift_over': snd_shift_over,
}


def sound_id(name):
    return rid('sound', name)


# ---- the library ---------------------------------------------------------------------

def library():
    textures, materials, models = [], [], []
    for name, (half, maker) in sorted(MODELS.items()):
        c = maker()
        textures.append(assetlib.Texture(rid('texture', name), c.w, c.h, c.rgba(), provenance=prov(maker.__name__)))
        materials.append(assetlib.Material(rid('material', name), rid('texture', name), 'opaque', provenance=prov('material')))
        models.append(assetlib.box_model(model_id(name), half, [rid('material', name)], provenance=prov('box_model')))
    for name, (lines, fg, bg, rule, half) in sorted(SIGNS.items()):
        c = sign_canvas(lines, fg, bg, rule, scale=2)
        textures.append(assetlib.Texture(rid('texture', name), c.w, c.h, c.rgba(), provenance=prov('sign_canvas')))
        materials.append(assetlib.Material(rid('material', name), rid('texture', name), 'opaque', provenance=prov('material')))
        models.append(assetlib.box_model(model_id(name), half, [rid('material', name)], provenance=prov('box_model')))
    sounds = [assetlib.Sound(sound_id(name), RATE, 1, pcm(make()), provenance=prov(make.__name__))
              for name, make in sorted(SOUNDS.items())]
    return Library(PACKAGE, [], display_name='Night Shift assets', textures=textures, materials=materials,
                   models=models, sounds=sounds)
