"""Package-backed asset resources (MegaMod X5): textures, materials, models
and sounds as MegaMod resources a library package provides.

Open Asset Lab turns external content into a MegaMod RESOURCE, not into a
file MegaMod knows how to find. A normalised model is known to the engine as
`community:model/security_door`; the Source path it came from
(`models/props_lab/door01.mdl`) is provenance, kept in the library's
"provenance" member and never hashed, never used to find anything.

  texture   x5shared:texture/test_crate    RGBA8 pixels
  material  x5shared:material/test_crate   one texture (a typed reference) and a draw mode
  model     x5shared:model/test_crate      a static mesh (mesh1) whose groups draw with its
                                           material slots (typed references)
  sound     x5shared:sound/test_impact     one clip of 16-bit PCM

A library declares them in its manifest's "assets" member and carries their
bytes right after the manifest, one MEMBER per resource. A member path
(`models/test_crate.mesh`) is storage inside the package -- never identity,
never a host path. Formats reuse what MegaMod already reads (the OALMAP's
40-byte vertex, the OALASSET's PCM, RGBA8 texels).

MegaMod is the authority. Every rule, limit and message here is the
engine's (src/asset/asset_res.c): the limits come from its contract
(data/megamod_resources.json, "assets"), and member paths are checked against
its own verdicts (data/megamod_id_conformance.json, "member_paths").
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from . import resources as res

A = res.CONTRACT['assets']
SCHEMA = A['schema']
LIMITS = A['limits']
PATH = A['member_path']
TYPES = A['types']
MESH_MAGIC = b'MSH1'
KINDS = ('texture', 'material', 'model', 'sound')
LIST = {'texture': 'textures', 'material': 'materials', 'model': 'models', 'sound': 'sounds'}
DIRS = {'texture': ('textures', 'rgba'), 'model': ('models', 'mesh'), 'sound': ('sounds', 'pcm')}
# A descriptor's fields, in the engine's reading order (asset_res.c KEYS).
KEYS = ('id', 'member', 'format', 'width', 'height', 'texture', 'draw', 'materials', 'rate', 'channels', 'frames')
FIELDS = {t: tuple(k for k in KEYS if k in TYPES[t]['fields']) for t in KINDS}


class AssetError(ValueError):
    pass


def _shown(c):
    if 0x21 <= c < 0x7F:
        return f"'{chr(c)}'"
    return 'a space' if c == 0x20 else f'\\x{c:02x}'


def member_path_error(path):
    """None, or why `path` is not a member path (the engine's words)."""
    b = res._bytes(path)
    if not b:
        return 'empty member path'
    if b'\x00' in b:
        b = b[:b.index(b'\x00')]
        if not b:
            return 'empty member path'
    if len(b) > PATH['max_bytes']:
        return f"longer than {PATH['max_bytes']} bytes"
    if b[0] == 0x2F:
        return "starts with '/' (member paths are package-relative)"
    if b[-1] == 0x2F:
        return "ends with '/'"
    segs = b.split(b'/')
    for n, seg in enumerate(segs):
        last = n == len(segs) - 1
        if n + 1 > PATH['max_segments']:
            return f"more than {PATH['max_segments']} segments"
        if not seg:
            return 'has an empty segment'
        if seg == b'..':
            return "has '..' (no parent references)"
        if seg == b'.':
            return "has '.' as a segment"
        for c in seg:
            if 0x61 <= c <= 0x7A or 0x30 <= c <= 0x39 or c in (0x5F, 0x2E):
                continue
            if 0x41 <= c <= 0x5A:
                return f'has capital {_shown(c)} (paths are lowercase; nothing is folded)'
            if c == 0x5C:
                return "has '\\' (the separator is '/')"
            return f'has {_shown(c)}, not [a-z0-9_./]'
        dots = seg.count(b'.')
        if not last and dots:
            return "has '.' in a directory segment (one extension, on the last segment)"
        if last and (dots != 1 or seg.index(b'.') == 0 or seg.endswith(b'.')):
            return 'needs exactly one extension on its last segment (name.ext)'
    return None


def default_member(rid):
    """Where a resource's bytes go by default: <kind>s/<name>.<ext>."""
    _, _, r = res.parse_id(rid)
    d, ext = DIRS[r.type]
    return f'{d}/{r.name}.{ext}'


# ---- the resources, as Open Asset Lab builds them --------------------------------

@dataclass
class Texture:
    id: str
    width: int
    height: int
    rgba: bytes
    member: str = None
    provenance: dict = field(default_factory=dict)


@dataclass
class Material:
    id: str
    texture: str                  # a texture resource ID (the library's own, or imported)
    draw: str = 'opaque'          # opaque | alpha
    provenance: dict = field(default_factory=dict)


@dataclass
class Model:
    """Model space, MegaMod runtime units. vertices: (pos, normal, uv);
    groups: (first index, index count, material slot)."""
    id: str
    vertices: list
    indices: list
    groups: list
    materials: list               # material resource IDs, one per slot
    member: str = None
    provenance: dict = field(default_factory=dict)

    def bounds(self):
        ps = [v[0] for v in self.vertices]
        return (tuple(min(p[k] for p in ps) for k in range(3)), tuple(max(p[k] for p in ps) for k in range(3)))


@dataclass
class Sound:
    id: str
    rate: int
    channels: int
    pcm: bytes                    # signed 16-bit little endian, interleaved
    member: str = None
    provenance: dict = field(default_factory=dict)

    @property
    def frames(self):
        return len(self.pcm) // (2 * self.channels)


def mesh1(model):
    """A Model's mesh1 bytes: MSH1, counts, 40-byte vertices, u32 indices,
    12-byte groups."""
    out = bytearray(MESH_MAGIC + struct.pack('<3I', len(model.vertices), len(model.indices), len(model.groups)))
    for pos, nrm, uv in model.vertices:
        out += struct.pack('<10f', *pos, *nrm, *uv, 0.0, 0.0)
    out += struct.pack(f'<{len(model.indices)}I', *model.indices)
    for first, count, slot in model.groups:
        out += struct.pack('<3I', first, count, slot)
    return bytes(out)


def box_model(rid, half, materials, member=None, provenance=None):
    """A box centred on the origin (half extents), one group, slot 0: the
    simplest original model."""
    faces = (((1, 0, 0), 0), ((-1, 0, 0), 0), ((0, 1, 0), 1), ((0, -1, 0), 1), ((0, 0, 1), 2), ((0, 0, -1), 2))
    verts, idx = [], []
    for nrm, a in faces:
        s = nrm[a]
        u, w = (a + 1) % 3, (a + 2) % 3
        base = len(verts)
        for c in range(4):
            p = [0.0, 0.0, 0.0]
            p[a] = s * half[a]
            p[u] = half[u] if c & 1 else -half[u]
            p[w] = half[w] if c & 2 else -half[w]
            verts.append((tuple(p), tuple(float(x) for x in nrm), (1.0 if c & 1 else 0.0, 1.0 if c & 2 else 0.0)))
        quad = (0, 1, 3, 0, 3, 2) if s > 0 else (0, 3, 1, 0, 2, 3)
        idx += [base + q for q in quad]
    return Model(rid, verts, idx, [(0, len(idx), 0)], list(materials), member, dict(provenance or {}))


# ---- a library's "assets" member and payload ------------------------------------------

def _descriptor(kind, r, member):
    if kind == 'texture':
        return {'format': 'rgba8', 'height': r.height, 'id': r.id, 'member': member, 'width': r.width}
    if kind == 'material':
        return {'draw': r.draw, 'id': r.id, 'texture': r.texture}
    if kind == 'model':
        return {'format': 'mesh1', 'id': r.id, 'materials': list(r.materials), 'member': member}
    return {'channels': r.channels, 'format': 'pcm_s16le', 'frames': r.frames, 'id': r.id, 'member': member,
            'rate': r.rate}


def _payload(kind, r):
    return {'texture': lambda: bytes(r.rgba), 'model': lambda: mesh1(r), 'sound': lambda: bytes(r.pcm)}[kind]()


def build(textures=(), materials=(), models=(), sounds=()):
    """(assets member dict, payload bytes, provides, provenance) for a
    library: every list in canonical ID order, members in canonical path
    order, the payload their bytes in that order."""
    groups = {'texture': list(textures), 'material': list(materials), 'model': list(models), 'sound': list(sounds)}
    member = {}
    descs = {}
    blobs = {}
    provenance = {}
    for kind in KINDS:
        items = sorted(groups[kind], key=lambda r: res._bytes(r.id))
        descs[kind] = []
        for r in items:
            m = None
            if kind != 'material':
                m = r.member or default_member(r.id)
                blobs[m] = _payload(kind, r)
                member[r.id] = m
            descs[kind].append(_descriptor(kind, r, m))
            if r.provenance:
                provenance[r.id] = dict(r.provenance)
    paths = sorted(blobs, key=res._bytes)
    assets = {'materials': descs['material'], 'members': [{'path': p, 'size': len(blobs[p])} for p in paths],
              'models': descs['model'], 'schema': SCHEMA, 'sounds': descs['sound'], 'textures': descs['texture']}
    provides = sorted((r.id for kind in KINDS for r in groups[kind]), key=res._bytes)
    return assets, b''.join(blobs[p] for p in paths), provides, provenance


def validate(textures=(), materials=(), models=(), sounds=()):
    """Diagnostics before a library is written ([] when good): what the
    engine would refuse about the descriptors themselves (references are
    checked with the package set, dependencies.link_assets)."""
    errs = []
    for kind, items in (('texture', textures), ('material', materials), ('model', models), ('sound', sounds)):
        if len(items) > LIMITS['per_type']:
            errs.append(f"more than {LIMITS['per_type']} {LIST[kind]}")
        for r in items:
            code, why, rid = res.parse_id(r.id)
            if code != res.OK:
                errs.append(f"assets.{LIST[kind]}: '{r.id}': {why}")
                continue
            if rid.type != kind:
                errs.append(f'assets.{LIST[kind]}: {r.id} is a {res.noun(rid.type)} ID, expected a {res.noun(kind)}')
            if res.reserved_namespace(rid.namespace):
                errs.append(f"{r.id}: namespace '{rid.namespace}' is reserved for built-in content")
            if kind != 'material':
                m = r.member or default_member(r.id)
                why = member_path_error(m)
                if why:
                    errs.append(f"{r.id}: member path '{m}': {why}")
            if kind == 'texture':
                if not (1 <= r.width <= TYPES['texture']['max_side'] and 1 <= r.height <= TYPES['texture']['max_side']):
                    errs.append(f"{r.id}: width and height must be whole numbers in 1..{TYPES['texture']['max_side']}")
                elif len(r.rgba) != r.width * r.height * 4:
                    errs.append(f'{r.id}: {r.width}x{r.height} rgba8 is {r.width * r.height * 4} bytes, not {len(r.rgba)}')
            elif kind == 'material' and r.draw not in TYPES['material']['draw']:
                errs.append(f"{r.id}: unknown draw '{r.draw}' (opaque or alpha)")
            elif kind == 'model':
                if not r.materials or len(r.materials) > TYPES['model']['max_slots']:
                    errs.append(f"{r.id}: a model needs 1..{TYPES['model']['max_slots']} materials")
                try:
                    decode_mesh1(mesh1(r), r.id, 'models', len(r.materials) or 1, 'package')
                except (AssetError, struct.error) as e:
                    errs.append(str(e))
            elif kind == 'sound':
                if not (4000 <= r.rate <= 96000 and r.channels in (1, 2) and
                        1 <= r.frames <= TYPES['sound']['max_frames'] and len(r.pcm) % (2 * r.channels) == 0):
                    errs.append(f"{r.id}: rate 4000..96000, channels 1..2 and frames 1..{TYPES['sound']['max_frames']} "
                                f'are whole numbers')
        ids_ = [r.id for r in items]
        for d in sorted({i for i in ids_ if ids_.count(i) > 1}):
            errs.append(f'{d} is declared twice')
    members = {}
    for kind, items in (('texture', textures), ('model', models), ('sound', sounds)):
        for r in items:
            m = r.member or default_member(r.id)
            if m in members:
                errs.append(f'member {m} backs both {members[m]} and {r.id} (one member, one resource)')
            members[m] = r.id
    return errs


# ---- reading one back, as the engine does ------------------------------------------------

def decode_mesh1(data, rid, path, slots, pkg):
    """(vertex count, index count, groups, bounds) or AssetError, the
    engine's checks and words."""
    def bad(why):
        raise AssetError(f'{pkg}: {rid}: member {path}: {why}')
    if len(data) < 16 or data[:4] != MESH_MAGIC:
        bad('not a mesh1 payload')
    vc, ic, gc = struct.unpack_from('<3I', data, 4)
    T = TYPES['model']
    if not (1 <= vc <= T['max_vertices']) or not (3 <= ic <= T['max_indices']) or ic % 3 or not (1 <= gc <= T['max_groups']):
        bad(f'counts out of range ({vc} vertices, {ic} indices, {gc} groups)')
    need = 16 + vc * 40 + ic * 4 + gc * 12
    if need != len(data):
        bad(f'is {len(data)} bytes, but its counts need {need}')
    lo, hi = [1e30] * 3, [-1e30] * 3
    for i in range(vc):
        v = struct.unpack_from('<10f', data, 16 + i * 40)
        if any(not math.isfinite(x) or abs(x) > 4096.0 for x in v):
            bad(f'vertex {i} is not finite or beyond 4096')
        for k in range(3):
            lo[k], hi[k] = min(lo[k], v[k]), max(hi[k], v[k])
    at = 16 + vc * 40
    idx = struct.unpack_from(f'<{ic}I', data, at)
    for i, x in enumerate(idx):
        if x >= vc:
            bad(f'index {i} names vertex {x} of {vc}')
    at += ic * 4
    end, groups = 0, []
    for i in range(gc):
        first, count, slot = struct.unpack_from('<3I', data, at + i * 12)
        if first != end or not count or count % 3 or count > ic - first:
            bad(f'group {i} does not follow on from the one before')
        if slot >= slots:
            bad(f'group {i} draws with material slot {slot}, but the model has {slots}')
        groups.append((first, count, slot))
        end = first + count
    if end != ic:
        bad(f'its groups cover {end} of {ic} indices')
    return vc, ic, groups, (tuple(lo), tuple(hi))


@dataclass
class AssetTable:
    """One library's assets as the engine holds them: descriptors by type,
    in canonical order (a resource's local index is its place here)."""
    textures: list = field(default_factory=list)      # descriptor dicts
    materials: list = field(default_factory=list)
    models: list = field(default_factory=list)        # + 'bounds', 'triangles'
    sounds: list = field(default_factory=list)
    payload_bytes: int = 0

    def of(self, kind):
        return getattr(self, LIST[kind])

    def ids(self):
        return [d['id'] for kind in KINDS for d in self.of(kind)]


def _whole(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v == int(v) and lo <= v <= hi


def parse(manifest, payload, pkg):
    """The AssetTable of a library's manifest dict and payload bytes, or
    AssetError with the engine's words (asset_res.c hta_asset_parse).
    No "assets" member: an empty table, and the payload must be empty."""
    t = AssetTable()
    if 'assets' not in manifest:
        if payload:
            raise AssetError(f'{pkg}: {len(payload)} bytes follow the manifest, but it declares no assets')
        return t, False
    a = manifest['assets']
    if not isinstance(a, dict):
        raise AssetError(f'{pkg}: assets is not an object')
    known = ('materials', 'members', 'models', 'schema', 'sounds', 'textures')
    for k in a:
        if k not in known:
            raise AssetError(f"{pkg}: unknown or repeated field '{k}' in assets (schema {SCHEMA} has "
                             f"materials, members, models, schema, sounds, textures)")
    members, wants = [], []
    for key in known:                       # the engine reads them in key order
        if key not in a:
            continue
        v = a[key]
        if key == 'schema':
            if v != SCHEMA:
                raise AssetError(f'{pkg}: unsupported assets schema {v:g} (this engine has {SCHEMA})'
                                 if isinstance(v, (int, float)) else f'{pkg}: malformed assets schema')
            continue
        if not isinstance(v, list):
            raise AssetError(f'{pkg}: assets.{key} is not a list')
        if key == 'members':
            for m in v:
                if len(members) >= LIMITS['members']:
                    raise AssetError(f"{pkg}: more than {LIMITS['members']} members")
                if not isinstance(m, dict):
                    raise AssetError(f'{pkg}: a member is not an object')
                for k in m:
                    if k not in ('path', 'size'):
                        raise AssetError(f"{pkg}: unknown or repeated member field '{k}'")
                p = m.get('path')
                if 'path' in m:
                    if not isinstance(p, str) or len(res._bytes(p)) > 255:
                        raise AssetError(f'{pkg}: a member path is not a string (or over 255 bytes)')
                    why = member_path_error(p)
                    if why:
                        raise AssetError(f"{pkg}: member path '{p}': {why}")
                if 'size' in m and not _whole(m['size'], 1, LIMITS['payload_bytes']):
                    raise AssetError(f"{pkg}: a member size is not a whole number of bytes in 1..{LIMITS['payload_bytes']}")
                if 'path' not in m or 'size' not in m:
                    raise AssetError(f'{pkg}: a member needs path and size')
                if members and res._bytes(members[-1]['path']) >= res._bytes(p):
                    raise AssetError(f'{pkg}: member {p} is listed twice' if members[-1]['path'] == p else
                                     f'{pkg}: assets.members is not in canonical (byte) order at {p}')
                members.append({'path': p, 'size': int(m['size'])})
            continue
        kind = {'materials': 'material', 'models': 'model', 'sounds': 'sound', 'textures': 'texture'}[key]
        out = t.of(kind)
        for d in v:
            if not isinstance(d, dict):
                raise AssetError(f'{pkg}: an entry of assets.{key} is not an object')
            rid = d.get('id') if isinstance(d.get('id'), str) else ''
            for k in d:
                if k not in KEYS:
                    raise AssetError(f"{pkg}: {rid}{': ' if rid else ''}unknown or repeated field '{k}' in assets.{key}")
            if not rid:
                raise AssetError(f'{pkg}: an entry of assets.{key} has no id')
            if len(res._bytes(rid)) > res.LIMITS['total']:
                raise AssetError(f"{pkg}: assets.{key}: an ID is longer than {res.LIMITS['total']} bytes")
            if len(out) >= LIMITS['per_type']:
                raise AssetError(f"{pkg}: more than {LIMITS['per_type']} {key}")
            code, why, r = res.parse_id(rid)
            if code != res.OK:
                raise AssetError(f"{pkg}: assets.{key}: '{rid}': {why}")
            if r.type != kind:
                raise AssetError(f'{pkg}: assets.{key}: {rid} is a {res.noun(r.type)} ID, expected a {res.noun(kind)}')
            if res.reserved_namespace(r.namespace):
                raise AssetError(f"{pkg}: {rid}: namespace '{r.namespace}' is reserved for built-in content")
            if out and res._bytes(out[-1]['id']) >= res._bytes(rid):
                raise AssetError(f'{pkg}: {rid} is declared twice' if out[-1]['id'] == rid else
                                 f'{pkg}: assets.{key} is not in canonical (byte) order at {rid}')
            for k in KEYS:
                if k in d and k not in FIELDS[kind]:
                    raise AssetError(f"{pkg}: {rid}: a {res.noun(kind)} has no field '{k}'")
                if k not in d and k in FIELDS[kind]:
                    raise AssetError(f"{pkg}: {rid}: a {res.noun(kind)} needs '{k}'")
            if 'member' in d:
                why = member_path_error(d['member'])
                if why:
                    raise AssetError(f"{pkg}: {rid}: member path '{d['member']}': {why}")
            if kind == 'texture':
                if d['format'] != 'rgba8':
                    raise AssetError(f"{pkg}: {rid}: unsupported texture format '{d['format']}' (this engine reads rgba8)")
                mx = TYPES['texture']['max_side']
                if not (_whole(d['width'], 1, mx) and _whole(d['height'], 1, mx)):
                    raise AssetError(f'{pkg}: {rid}: width and height must be whole numbers in 1..{mx}')
            elif kind == 'material':
                if d['draw'] not in TYPES['material']['draw']:
                    raise AssetError(f"{pkg}: {rid}: unknown draw '{d['draw']}' (opaque or alpha)")
            elif kind == 'model':
                if d['format'] != 'mesh1':
                    raise AssetError(f"{pkg}: {rid}: unsupported model format '{d['format']}' (this engine reads mesh1)")
                if len(d['materials']) > TYPES['model']['max_slots']:
                    raise AssetError(f"{pkg}: {rid}: more than {TYPES['model']['max_slots']} material slots")
                if not d['materials']:
                    raise AssetError(f'{pkg}: {rid}: a model needs at least one material')
            else:
                if d['format'] != 'pcm_s16le':
                    raise AssetError(f"{pkg}: {rid}: unsupported sound format '{d['format']}' (this engine reads pcm_s16le)")
                if not (_whole(d['rate'], 4000, 96000) and _whole(d['channels'], 1, 2) and
                        _whole(d['frames'], 1, TYPES['sound']['max_frames'])):
                    raise AssetError(f"{pkg}: {rid}: rate 4000..96000, channels 1..2 and frames 1..{TYPES['sound']['max_frames']} "
                                     f'are whole numbers')
            out.append(dict(d))
            if kind != 'material':
                wants.append((kind, len(out) - 1, d['member']))
    if any(k not in a for k in known):
        raise AssetError(f'{pkg}: assets needs materials, members, models, schema, sounds and textures')
    # the payload: members' bytes, in order
    total = 0
    for m in members:
        total += m['size']
        if total > LIMITS['payload_bytes']:
            raise AssetError(f"{pkg}: its members add up to more than {LIMITS['payload_bytes']} bytes")
    if total != len(payload):
        raise AssetError(f'{pkg}: its members add up to {total} bytes, but the package carries {len(payload)} after the manifest')
    at = 0
    for m in members:
        m['at'] = at
        at += m['size']
    by_path = {m['path']: m for m in members}
    # wants in the engine's order: by the manifest key order it read them in
    order = {'models': 0, 'sounds': 1, 'textures': 2}
    wants.sort(key=lambda w: order[LIST[w[0]]])
    used = {}
    for kind, i, path in wants:
        rid = t.of(kind)[i]['id']
        if path not in by_path:
            raise AssetError(f'{rid} declares package member {path}, but that member is missing')
        if path in used:
            raise AssetError(f'{pkg}: member {path} backs both {used[path]} and {rid} (one member, one resource)')
        used[path] = rid
    for m in members:
        if m['path'] not in used:
            raise AssetError(f"{pkg}: member {m['path']} is not used by any resource")
    for kind, i, path in wants:
        d = t.of(kind)[i]
        m = by_path[path]
        blob = payload[m['at']:m['at'] + m['size']]
        if kind == 'texture':
            need = d['width'] * d['height'] * 4
            if need != m['size']:
                raise AssetError(f"{d['id']}: {d['width']}x{d['height']} rgba8 is {need} bytes, but member {path} holds {m['size']}")
        elif kind == 'sound':
            need = d['frames'] * d['channels'] * 2
            if need != m['size']:
                raise AssetError(f"{d['id']}: {d['frames']} frames of {d['channels']}-channel pcm_s16le are {need} bytes, "
                                 f"but member {path} holds {m['size']}")
        else:
            vc, ic, groups, bounds = decode_mesh1(blob, d['id'], path, len(d['materials']), pkg)
            d['bounds'], d['triangles'] = bounds, ic // 3
        d['bytes'] = blob
    t.payload_bytes = len(payload)
    return t, True


# ---- from an imported Source model -------------------------------------------------------

def from_source_model(resolver, path, namespace, name=None, skin=0, lod=0, provider=None):
    """A Source static model (MDL/VVD/VTX through `resolver`) as MegaMod
    resources: (Model, [Material], [Texture], report). IDs are MegaMod's --
    `<namespace>:model/<name>`, one material and texture per Source
    material, named from its file name -- and every Source path is kept as
    provenance, never as identity. Positions are converted to runtime units
    (assetlab.coords); nothing else is changed."""
    from .coords import to_runtime
    from .importers.source_bsp import BSPError
    from .importers.source_mdl import Model as SourceModel
    import re
    base = path.replace('\\', '/').lower().removesuffix('.mdl')
    blobs = [resolver.read(base + ext) for ext in ('.mdl', '.vvd', '.dx90.vtx')]
    if None in blobs:
        raise AssetError(f'{path}: missing ' + ', '.join(base + e for e, b in zip(('.mdl', '.vvd', '.dx90.vtx'), blobs) if b is None))
    try:
        src = SourceModel(*blobs, skin, resolver.has_material, lod)
    except BSPError as e:
        raise AssetError(f'{path}: {e}')

    def slug(text):
        s = re.sub(r'[^a-z0-9_]+', '_', text.lower()).strip('_')
        s = s if s and s[0].isalpha() else 'm_' + s
        return s[:res.LIMITS['name']].rstrip('_') or 'unnamed'

    name = name or slug(base.rpartition('/')[2])
    origin = dict(provider or {}, source_path=base + '.mdl', importer='assetlab.assets.from_source_model')
    verts, idx, groups, materials, textures, missing = [], [], [], [], [], []
    for slot, (mat, tris) in enumerate(sorted(src.groups.items())):
        first = len(idx)
        for pos, nrm, uv in tris:
            idx.append(len(verts))
            verts.append((to_runtime(pos), tuple(float(x) for x in nrm), (float(uv[0]), float(uv[1]))))
        groups.append((first, len(idx) - first, slot))
        mslug = slug(mat.rpartition('/')[2])
        decoded, params = resolver.material(mat)
        tid, mid = f'{namespace}:texture/{mslug}', f'{namespace}:material/{mslug}'
        if decoded is None:
            missing.append(mat)
            decoded = (1, 1, bytes((255, 0, 255, 255)))          # MegaMod's missing-texture magenta, labelled
        w, h, px = decoded
        alpha = params.get('$translucent') == '1' or params.get('$alphatest') == '1'
        textures.append(Texture(tid, w, h, px, provenance=dict(origin, source_material=f'materials/{mat}.vmt',
                                                                 source_texture=params.get('$basetexture'),
                                                                 substituted=decoded[2] == bytes((255, 0, 255, 255)))))
        materials.append(Material(mid, tid, 'alpha' if alpha else 'opaque', provenance=dict(origin, source_material=f'materials/{mat}.vmt')))
    model = Model(f'{namespace}:model/{name}', verts, idx, groups, [m.id for m in materials], provenance=origin)
    return model, materials, textures, {'model': model.id, 'source': base + '.mdl', 'triangles': len(idx) // 3,
                                        'materials': [m.id for m in materials], 'missing_textures': missing}
