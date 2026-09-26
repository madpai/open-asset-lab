"""Original worlds: geometry and generic world entities authored as data,
compiled by the same packaging stage as imported maps (package.py).

This is the first source-independent world path (MegaMod's X1 slice). A
world is built in Python -- boxes, starts and placed entities -- and never
goes through a Source entity class: an entity is one of five generic kinds
the runtime implements natively.

  interactable  a thing a player uses (a button). Emits `used`.
  relay         passes an activation on. Accepts `activate`; emits `fired`.
  mover         geometry that slides by `move` at `speed` (a door).
                Accepts `open`, `close`, `toggle`.
  trigger       a box that notices a player entering. Emits `entered`.
  teleport      a destination. Accepts `teleport`: moves the player who
                caused the chain to its position.

Links wire them: (event, target placed ID, input). Placed IDs use the
content-ID grammar (docs/CONTENT_IDS.md) with type `entity`, in the world's
own namespace: `x1:entity/door_main`. They name the placement, not a
definition, and are unique within the world. The runtime resolves them to
checked handles once, at load; nothing is looked up by name during play.

`validate()` rejects what the runtime would otherwise have to survive:
duplicate or malformed IDs, missing targets, a target that does not accept
the input, an event its source does not emit, cycles, fan-out
and chain length over the runtime's limits, bad mover/trigger/teleport
parameters, and a destination inside a trigger (it would fire again).
The runtime still checks all of it (defence in depth).

There is deliberately no text format for this yet: tests and
`assetlab fixture` build worlds in code (docs/ORIGINAL_WORLDS.md).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from . import ids
from .package import (GROUP_NO_COLLISION, build_groups, manifest_json, pack_vertices,
                      write_package)

# OALMAP v3: the v2 layout plus a manifest `world_entities` section the
# runtime must implement. A runtime that does not know v3 refuses the
# package instead of loading the world without its behaviour.
VERSION = 3
GROUP_ENTITY = 8        # a world entity's triangles; its index + 1 in bits 8..23
ENTITY_SCHEMA = 1

# The runtime's limits (MegaMod src/asset/world_def.h); a package that
# passes here passes there.
MAX_ENTITIES = 64
MAX_LINKS_PER_ENTITY = 8
MAX_LINKS = 256
MAX_CHAIN = 16          # links from a root event to the last one it causes
MAX_EVENTS_PER_ROOT = 256
MAX_REACH = 4.0         # wu
MAX_MOVE = 64.0         # wu
MAX_SPEED = 64.0        # wu/s
WORLD_LIMIT = 4096.0    # |coordinate|, wu

KINDS = ('interactable', 'relay', 'mover', 'trigger', 'teleport')
EMITS = {'interactable': ('used',), 'relay': ('fired',), 'trigger': ('entered',),
         'mover': (), 'teleport': ()}
ACCEPTS = {'relay': ('activate',), 'mover': ('open', 'close', 'toggle'),
           'teleport': ('teleport',), 'interactable': (), 'trigger': ()}
EVENTS = ('used', 'fired', 'entered')
INPUTS = ('activate', 'open', 'close', 'toggle', 'teleport')
# Every X1 event carries the player who started its chain (a button's
# user, a trigger's enterer, passed on by relays): `teleport` acts on them.


class WorldError(ValueError):
    def __init__(self, diagnostics):
        self.diagnostics = list(diagnostics)
        super().__init__('\n'.join(self.diagnostics))


@dataclass
class Link:
    event: str
    target: str
    input: str


@dataclass
class Entity:
    id: str
    kind: str
    links: list = field(default_factory=list)
    position: tuple = None      # interactable, teleport
    reach: float = None         # interactable
    yaw_degrees: float = 0.0    # teleport: facing on arrival
    bounds: tuple = None        # trigger: (min, max)
    move: tuple = None          # mover: offset when open
    speed: float = None         # mover: wu/s


@dataclass
class Box:
    min: tuple
    max: tuple
    material: str
    solid: bool = True
    owner: str = None           # the placed ID of the mover this box is


@dataclass
class OriginalWorld:
    id: str                      # namespace:world/name
    file_name: str               # the runtime looks packages up by this (maps/<name>.oalmap)
    display_name: str
    materials: dict              # name -> (r, g, b) 0..255
    boxes: list
    spawns: list                 # {'position', 'yaw_degrees', 'team'}
    entities: list


def _finite(v, n=3):
    return (isinstance(v, (tuple, list)) and len(v) == n and
            all(isinstance(x, (int, float)) and math.isfinite(x) and abs(x) <= WORLD_LIMIT for x in v))


def _a(kind):
    return ('an ' if kind[0] in 'aeiou' else 'a ') + kind


def _inside(p, lo, hi):
    return all(lo[k] <= p[k] <= hi[k] for k in range(3))


def owned_bounds(world, eid):
    boxes = [b for b in world.boxes if b.owner == eid]
    if not boxes:
        return None
    return (tuple(min(b.min[k] for b in boxes) for k in range(3)),
            tuple(max(b.max[k] for b in boxes) for k in range(3)))


def validate(world):
    """Diagnostics (errors) for the world's entities and links; [] when it
    compiles. Each names the placement, and the link, it is about."""
    errs = []
    ok, why = ids.valid_id(world.id)
    ns = world.id.partition(':')[0]
    if not ok:
        errs.append(f'world id {world.id!r}: {why}')
    elif world.id.partition(':')[2].partition('/')[0] != 'world':
        errs.append(f'world id {world.id!r}: type must be world')
    if len(world.entities) > MAX_ENTITIES:
        errs.append(f'{len(world.entities)} entities; the runtime takes at most {MAX_ENTITIES}')
    by_id = {}
    for e in world.entities:
        ok, why = ids.valid_id(e.id)
        if not ok:
            errs.append(f'{e.id!r}: malformed placed ID: {why}')
            continue
        e_ns, _, rest = e.id.partition(':')
        if rest.partition('/')[0] != 'entity':
            errs.append(f'{e.id}: a placed ID has type entity')
        if e_ns != ns:
            errs.append(f'{e.id}: placed IDs belong to the world\'s namespace {ns!r}')
        if e.id in by_id:
            errs.append(f'{e.id}: duplicate placed ID')
            continue
        by_id[e.id] = e
    total = 0
    for e in world.entities:
        if e.kind not in KINDS:
            errs.append(f'{e.id}: unknown kind {e.kind!r} (one of {", ".join(KINDS)})')
            continue
        if e.kind in ('interactable', 'teleport'):
            if not _finite(e.position):
                errs.append(f'{e.id}: {e.kind} needs a finite position inside the world')
        if e.kind == 'interactable' and not (isinstance(e.reach, (int, float)) and 0 < e.reach <= MAX_REACH):
            errs.append(f'{e.id}: reach must be in (0, {MAX_REACH}] wu')
        if e.kind == 'teleport' and not (isinstance(e.yaw_degrees, (int, float)) and math.isfinite(e.yaw_degrees)):
            errs.append(f'{e.id}: yaw_degrees must be finite')
        if e.kind == 'trigger':
            b = e.bounds
            if not (b and len(b) == 2 and _finite(b[0]) and _finite(b[1])):
                errs.append(f'{e.id}: trigger needs finite bounds (min, max)')
            elif not all(b[1][k] - b[0][k] >= 0.05 for k in range(3)):
                errs.append(f'{e.id}: trigger bounds are empty or thinner than 0.05 wu')
        if e.kind == 'mover':
            if not _finite(e.move) or not (0.01 <= math.sqrt(sum(x*x for x in e.move)) <= MAX_MOVE):
                errs.append(f'{e.id}: mover needs a finite move between 0.01 and {MAX_MOVE} wu')
            if not (isinstance(e.speed, (int, float)) and math.isfinite(e.speed) and 0 < e.speed <= MAX_SPEED):
                errs.append(f'{e.id}: mover speed must be in (0, {MAX_SPEED}] wu/s')
            if owned_bounds(world, e.id) is None:
                errs.append(f'{e.id}: mover has no geometry (no box is owned by it)')
        if len(e.links) > MAX_LINKS_PER_ENTITY:
            errs.append(f'{e.id}: {len(e.links)} links; at most {MAX_LINKS_PER_ENTITY} per entity')
        total += len(e.links)
        for ln in e.links:
            where = f'{e.id}: link {ln.event} -> {ln.target}.{ln.input}'
            if ln.event not in EMITS[e.kind]:
                errs.append(f'{where}: {_a(e.kind)} does not emit {ln.event!r}'
                            + (f' (it emits {", ".join(EMITS[e.kind])})' if EMITS[e.kind] else ' (it emits nothing)'))
            if ln.input not in INPUTS:
                errs.append(f'{where}: unknown input {ln.input!r}')
            t = by_id.get(ln.target)
            if t is None:
                errs.append(f'{e.id} references missing target {ln.target}')
                continue
            if t is e:
                errs.append(f'{where}: an entity cannot target itself')
            elif t.kind in KINDS and ln.input in INPUTS and ln.input not in ACCEPTS[t.kind]:
                errs.append(f'{where}: {_a(t.kind)} does not accept {ln.input!r}'
                            + (f' (it accepts {", ".join(ACCEPTS[t.kind])})' if ACCEPTS[t.kind] else ' (it accepts nothing)'))
    if total > MAX_LINKS:
        errs.append(f'{total} links; the runtime takes at most {MAX_LINKS}')
    for b in world.boxes:
        if b.owner is not None:
            o = by_id.get(b.owner)
            if o is None:
                errs.append(f'geometry owned by missing entity {b.owner}')
            elif o.kind != 'mover':
                errs.append(f'{b.owner}: only a mover owns geometry (it is a {o.kind})')
    # A destination inside a trigger would send whoever arrives straight
    # back through it.
    for e in world.entities:
        if e.kind == 'teleport' and _finite(e.position):
            for t in world.entities:
                if (t.kind == 'trigger' and t.bounds and len(t.bounds) == 2 and _finite(t.bounds[0]) and
                        _finite(t.bounds[1]) and _inside(e.position, *t.bounds)):
                    errs.append(f'{e.id}: destination is inside trigger {t.id} (it would fire again on arrival)')
    if not errs:
        errs += _graph_errors(world.entities, by_id)
    return errs


def _graph_errors(entities, by_id):
    """Cycles, chain length and worst-case work per root, over the links.
    Every X1 link is zero-delay, so any cycle loops within one tick."""
    out = {e.id: [ln.target for ln in e.links] for e in entities}
    errs, state, order = [], {}, []

    def visit(n, path):
        state[n] = 1; path.append(n)
        for m in out[n]:
            if state.get(m) == 1:
                cyc = path[path.index(m):] + [m]
                errs.append('link cycle: ' + ' -> '.join(cyc))
            elif m not in state:
                visit(m, path)
        path.pop(); state[n] = 2; order.append(n)

    for e in entities:
        if e.id not in state:
            visit(e.id, [])
    if errs:
        return errs
    depth, work = {}, {}
    for n in order:                     # post-order: successors first
        depth[n] = 1 + max((depth[m] for m in out[n]), default=0)
        work[n] = sum(1 + work[m] for m in out[n])
    for e in entities:
        if depth[e.id] - 1 > MAX_CHAIN:
            errs.append(f'{e.id}: a chain of {depth[e.id]-1} links starts here; at most {MAX_CHAIN}')
        if work[e.id] > MAX_EVENTS_PER_ROOT:
            errs.append(f'{e.id}: one event here can cause {work[e.id]} more; at most {MAX_EVENTS_PER_ROOT}')
    return errs


def _entity_record(world, e):
    r = {'id': e.id, 'kind': e.kind,
         'links': [{'event': ln.event, 'target': ln.target, 'input': ln.input} for ln in e.links]}
    if e.kind in ('interactable', 'teleport'):
        r['position'] = [float(x) for x in e.position]
    if e.kind == 'interactable':
        r['reach'] = float(e.reach)
    if e.kind == 'teleport':
        r['yaw_degrees'] = float(e.yaw_degrees)
    if e.kind == 'trigger':
        r['bounds'] = {'min': [float(x) for x in e.bounds[0]], 'max': [float(x) for x in e.bounds[1]]}
    if e.kind == 'mover':
        lo, hi = owned_bounds(world, e.id)
        r['bounds'] = {'min': [float(x) for x in lo], 'max': [float(x) for x in hi]}
        r['move'] = [float(x) for x in e.move]
        r['speed'] = float(e.speed)
    return r


# ---- geometry -----------------------------------------------------------------

# (normal, four corners as (x, y, z) picks of lo/hi, counter-clockwise seen
# from outside) for the six faces of a box.
_FACES = (
    ((1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ((-1, 0, 0), ((0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1))),
    ((0, 1, 0), ((1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
    ((0, 0, -1), ((0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0))),
)


def _box_triangles(b, vertices, indices):
    lo, hi = b.min, b.max
    for nrm, corners in _FACES:
        axis = [k for k in range(3) if nrm[k] == 0]      # the face's two in-plane axes
        base = len(vertices)
        for c in corners:
            p = tuple(float(hi[k] if c[k] else lo[k]) for k in range(3))
            uv = (p[axis[0]], p[axis[1]])                  # one texture repeat per wu
            vertices.append((p, tuple(float(x) for x in nrm), uv))
        indices += [base, base + 1, base + 2, base, base + 2, base + 3]


def _texture(rgb):
    """16x16 RGBA: the colour with a faint 4-texel check, so motion shows."""
    px = bytearray()
    for y in range(16):
        for x in range(16):
            d = 0.9 if ((x // 4) + (y // 4)) % 2 else 1.0
            px += bytes((int(rgb[0] * d), int(rgb[1] * d), int(rgb[2] * d), 255))
    return 16, 16, bytes(px)


def compile_world(world, output):
    """Validate and write `world` as an OALMAP. Raises WorldError with every
    diagnostic when it does not validate. Returns (manifest, report)."""
    errs = validate(world)
    for b in world.boxes:
        if not (_finite(b.min) and _finite(b.max) and all(b.max[k] > b.min[k] for k in range(3))):
            errs.append(f'box {b.min}..{b.max}: empty or not finite')
        if b.material not in world.materials:
            errs.append(f'box {b.min}..{b.max}: unknown material {b.material!r}')
    if not world.spawns:
        errs.append('the world has no player start')
    if errs:
        raise WorldError(errs)
    index_of = {e.id: i for i, e in enumerate(world.entities)}
    vertices, src_indices, runs = [], [], []
    for b in world.boxes:
        first = len(src_indices)
        _box_triangles(b, vertices, src_indices)
        owner = (GROUP_ENTITY, index_of[b.owner]) if b.owner else None
        # A mover's triangles are its own collision, not the world's.
        runs.append((b.material, first, len(src_indices) - first, b.solid and not b.owner, owner))
    mats = sorted(world.materials)
    tex_index = {m: i for i, m in enumerate(mats)}
    indices, groups, collision_triangles = build_groups(runs, src_indices, tex_index, lambda m: False,
                                                        {}, len(mats), VERSION)
    packed = pack_vertices(indices, vertices, {})
    lo = [min(v[0][k] for v in vertices) for k in range(3)]
    hi = [max(v[0][k] for v in vertices) for k in range(3)]
    for e in world.entities:            # a mover's open position counts too
        if e.kind == 'mover':
            blo, bhi = owned_bounds(world, e.id)
            lo = [min(lo[k], blo[k] + min(0.0, e.move[k])) for k in range(3)]
            hi = [max(hi[k], bhi[k] + max(0.0, e.move[k])) for k in range(3)]
    entities = [_entity_record(world, e) for e in world.entities]
    kinds = {k: sum(e.kind == k for e in world.entities) for k in KINDS}
    manifest = {
        'package_version': VERSION, 'importer_version': 'original_world-0.1.0',
        'id': world.id, 'namespace': world.id.partition(':')[0],
        'map_id': world.file_name, 'display_name': world.display_name,
        'source_format': 'original world (Open Asset Lab)',
        'required_open_halo_runtime': f'external-map-v{VERSION}',
        'geometry': {'vertices': len(packed), 'triangles': len(indices) // 3,
                     'collision_triangles': collision_triangles, 'boxes': len(world.boxes)},
        'material_paths': mats, 'spawn_points': world.spawns, 'flag_points': [], 'breakables': [],
        'world_entities': {'schema': ENTITY_SCHEMA, 'entities': entities},
        'supported_features': ['boxes', 'player starts', 'world entities: ' + ', '.join(KINDS)],
        'unsupported_features': [],
        'bounds': {'min': lo, 'max': hi}, 'texture_count': len(mats),
        'source_provenance': 'original content built by Open Asset Lab; no third-party assets',
    }
    manifest_bytes = manifest_json(manifest)
    write_package(output, VERSION, manifest_bytes, packed, indices, groups,
                  [_texture(world.materials[m]) for m in mats], world.spawns, lo, hi)
    with open(output, 'rb') as f:
        data = f.read()
    report = {'world': world.id, 'entities': len(entities), 'kinds': kinds,
              'links': sum(len(e.links) for e in world.entities),
              'triangles': len(indices) // 3, 'package_bytes': len(data),
              'package_sha256': hashlib.sha256(data).hexdigest()}
    return manifest, report
