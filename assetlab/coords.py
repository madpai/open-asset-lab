"""Source -> Open Halo coordinates, in one place.

Source's world unit is one inch (Valve Developer Community, "Dimensions").
Open Halo's world unit is Halo's: ten feet, i.e. 120 inches. Both are
right-handed with +Z up, so the axes carry over unchanged and only the
scale differs. Nothing else in the importer may scale or reorient
positions; it calls these.
"""
from __future__ import annotations
import math

SOURCE_UNITS_PER_RUNTIME_UNIT = 120.0
SCALE = 1.0 / SOURCE_UNITS_PER_RUNTIME_UNIT
# Source's MAX_COORD_INTEGER: a legal map lies inside +-16384 units.
SOURCE_MAX_COORD = 16384.0
RUNTIME_MAX_SPAN = 2.0 * SOURCE_MAX_COORD * SCALE

TRANSFORM = {
    'axes': 'Source xyz -> Open Halo xyz (right handed, +Z up)',
    'scale': SCALE,
    'source_unit': 'inch',
    'runtime_unit': 'ten feet',
}


def to_runtime(p):
    """A Source position (inches) as an Open Halo position."""
    return (float(p[0]) * SCALE, float(p[1]) * SCALE, float(p[2]) * SCALE)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def norm(v):
    n = math.sqrt(sum(x*x for x in v))
    return tuple(x/n for x in v) if n > 1e-12 else (0.0, 0.0, 0.0)


def angle_matrix(pitch, yaw, roll):
    """Valve's AngleMatrix (mathlib): QAngle degrees -> rotation, columns
    forward, left, up. Used for static props and brush/model entities."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    return ((cp*cy, sr*sp*cy - cr*sy, cr*sp*cy + sr*sy),
            (cp*sy, sr*sp*sy + cr*cy, cr*sp*sy - sr*cy),
            (-sp, sr*cp, cr*cp))


def rotate(m, v):
    return tuple(m[r][0]*v[0] + m[r][1]*v[1] + m[r][2]*v[2] for r in range(3))


def parse_vector(text, n=3):
    """A Source keyvalue vector ("x y z"); None when malformed."""
    try:
        parts = [float(x) for x in str(text).split()]
    except ValueError:
        return None
    if len(parts) != n or not all(math.isfinite(x) for x in parts):
        return None
    return tuple(parts)
