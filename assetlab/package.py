"""OALMAP v1 compiler and Source material/model resolution.

One code path for every map: the BSP reader produces world triangles, the
resolver finds materials and models through a configured search path, the
translation registry (assetlab.translate) decides what each Source feature
becomes, and whatever is not reproduced lands in the report.
"""
from __future__ import annotations
import hashlib
import io
import json
import math
import re
import struct
import zipfile
from collections import Counter
from pathlib import Path
from PIL import Image
from srctools.vpk import VPK
from . import translate
from .coords import TRANSFORM, angle_matrix, cross, norm, rotate, sub, to_runtime
from .importers.source_bsp import BSPError, SourceBSP
from .importers.source_mdl import Model

MAGIC = b'OALM'
VERSION = 1
MAX_TEXTURE = 2048
HEADER = '<4s8I6fI'  # 64 bytes
GROUP_NO_COLLISION = 1  # group record flags: drawn but not solid
# Open Halo's loader refuses more RGBA texture data than this (external_map.c).
RUNTIME_TEXTURE_CAP = 128 * 1024 * 1024
RUNTIME_FILE_CAP = 256 * 1024 * 1024
DEFAULT_TEXTURE_BUDGET = RUNTIME_TEXTURE_CAP


# ---- VMT (Valve KeyValues) -------------------------------------------------

def parse_keyvalues(text):
    """Valve KeyValues: quoted or bare tokens, {} blocks, // comments.
    Returns (root key, nested dict with lower-cased keys)."""
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        elif c in '{}':
            tokens.append(c); i += 1
        elif c == '"':
            j = text.find('"', i+1)
            if j < 0:
                raise BSPError('VMT: unterminated string')
            tokens.append(('s', text[i+1:j])); i = j+1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '{}"':
                j += 1
            tokens.append(('s', text[i:j])); i = j

    pos = 0

    def block():
        nonlocal pos
        out = {}
        while pos < len(tokens):
            t = tokens[pos]
            if t == '}':
                pos += 1
                return out
            if t == '{':
                raise BSPError('VMT: block without a key')
            key = t[1].lower(); pos += 1
            if pos < len(tokens) and tokens[pos] == '{':
                pos += 1
                out[key] = block()
            elif pos < len(tokens) and tokens[pos] not in ('{', '}'):
                out[key] = tokens[pos][1]; pos += 1
            else:
                raise BSPError(f'VMT: key {key!r} without a value')
        return out

    if not tokens or tokens[0] in ('{', '}'):
        raise BSPError('VMT: missing shader name')
    root = tokens[0][1].lower(); pos = 1
    if pos >= len(tokens) or tokens[pos] != '{':
        raise BSPError('VMT: shader without a block')
    pos += 1
    return root, block()


# ---- VTF -------------------------------------------------------------------

# format id -> (bytes per pixel or DXT block bytes, how to decode)
VTF_FORMATS = {
    0: (4, ('raw', 'RGBA')), 1: (4, ('raw', 'ABGR')), 2: (3, ('raw', 'RGB')), 3: (3, ('raw', 'BGR')),
    5: (1, ('raw', 'L')), 6: (2, ('raw', 'LA')), 8: (1, ('alpha', None)), 11: (4, ('raw', 'ARGB')),
    12: (4, ('raw', 'BGRA')), 16: (4, ('raw', 'BGRX')),
    13: (8, ('dxt', b'DXT1')), 20: (8, ('dxt', b'DXT1')), 14: (16, ('dxt', b'DXT3')), 15: (16, ('dxt', b'DXT5')),
}
VTF_FLAG_ENVMAP = 0x4000


def _vtf_rgba(data):
    if len(data) < 80 or data[:4] != b'VTF\0':
        raise BSPError('invalid VTF header')
    major, minor, head = struct.unpack_from('<III', data, 4)
    if major != 7 or minor > 5 or head > len(data):
        raise BSPError('unsupported VTF version')
    w, h, flags, frames = struct.unpack_from('<HHIH', data, 16)
    fmt = struct.unpack_from('<i', data, 52)[0]
    # VTF stores mipmapCount at byte 56; depth (7.2+) at 63.
    mip = data[56]
    depth = max(1, struct.unpack_from('<H', data, 63)[0]) if minor >= 2 else 1
    frames = max(1, frames)
    faces = (6 if minor >= 5 else 7) if flags & VTF_FLAG_ENVMAP else 1
    if not 0 < w <= MAX_TEXTURE or not 0 < h <= MAX_TEXTURE or mip < 1 or mip > 16 or depth > 64:
        raise BSPError('VTF dimensions or mip count out of range')
    if fmt not in VTF_FORMATS:
        raise BSPError(f'unsupported VTF image format {fmt}')
    unit, (kind, arg) = VTF_FORMATS[fmt]

    def level_size(a, b):
        if kind == 'dxt':
            return max(1, (a+3)//4)*max(1, (b+3)//4)*unit
        return a*b*unit
    high = head
    if minor >= 3:
        count = struct.unpack_from('<I', data, 68)[0]
        if count > 32 or 80+count*8 > head:
            raise BSPError('invalid VTF resource table')
        for i in range(count):
            if data[80+i*8:83+i*8] == b'\x30\x00\x00':
                high = struct.unpack_from('<I', data, 84+i*8)[0]
    else:
        lowfmt = struct.unpack_from('<i', data, 57)[0]; lw, lh = data[61:63]
        if lowfmt != -1:
            high += max(1, (lw+3)//4)*max(1, (lh+3)//4)*8
    # Mips smallest first; within a mip every frame, face and slice. Frame 0,
    # face 0, slice 0 of the largest mip is the texture.
    pos = high
    for i in range(mip-1, 0, -1):
        pos += level_size(max(1, w >> i), max(1, h >> i))*frames*faces*depth
    n = level_size(w, h)
    if pos+n > len(data):
        raise BSPError('truncated VTF high-resolution image')
    pixels = data[pos:pos+n]
    if kind == 'raw':
        im = Image.frombytes('RGBA' if arg in ('RGBA', 'ABGR', 'ARGB', 'BGRA') else
                             'RGB' if arg in ('RGB', 'BGR', 'BGRX') else arg, (w, h), pixels, 'raw', arg)
    elif kind == 'alpha':
        im = Image.new('RGBA', (w, h), (255, 255, 255, 255)); im.putalpha(Image.frombytes('L', (w, h), pixels))
    else:
        dds = bytearray(128); dds[:4] = b'DDS '
        struct.pack_into('<I', dds, 4, 124); struct.pack_into('<I', dds, 8, 0x0002100F)
        struct.pack_into('<III', dds, 12, h, w, n); struct.pack_into('<I', dds, 76, 32)
        struct.pack_into('<I', dds, 80, 4); dds[84:88] = arg; struct.pack_into('<I', dds, 108, 0x1000)
        im = Image.open(io.BytesIO(bytes(dds)+pixels))
    return w, h, im.convert('RGBA').tobytes()


# ---- resolution -------------------------------------------------------------

class Resolver:
    """Finds files by Source path through, in order: the BSP's embedded
    pakfile, configured unpacked roots, configured VPKs. The search path is
    configuration, never code."""

    def __init__(self, bsp, roots=(), vpks=()):
        self.bsp = bsp
        pak = bsp.lump(40) if bsp is not None else b''
        self.zip = zipfile.ZipFile(io.BytesIO(pak)) if pak else None
        if self.zip:
            entries = self.zip.infolist()
            if len(entries) > 10000 or any(e.file_size > 64*1024*1024 for e in entries):
                raise BSPError('embedded pakfile resource limit exceeded')
            self.names = {e.filename.lower(): e.filename for e in entries}
        else:
            self.names = {}
        self.roots = [Path(r).resolve() for r in roots]
        self.vpks = []
        for path in vpks:
            archive = Path(path).resolve()
            if not archive.is_file() or not archive.name.lower().endswith('_dir.vpk'):
                raise BSPError(f'VPK directory file not found: {archive}')
            try:
                self.vpks.append(VPK(archive))
            except (OSError, ValueError) as e:
                raise BSPError(f'cannot read VPK {archive}: {e}') from e
        self.missing = []; self.warnings = []; self.found_in = Counter(); self._vmts = {}

    def search_path(self):
        return (['bsp pakfile'] if self.zip else []) + [str(r) for r in self.roots] + [v.folder + '/' + v.file_prefix + '_dir.vpk' for v in self.vpks]

    def read(self, name):
        name = name.replace('\\', '/').lstrip('/').lower()
        if '..' in Path(name).parts or '\0' in name:
            raise BSPError('unsafe resource path')
        if name in self.names:
            self.found_in['bsp pakfile'] += 1
            return self.zip.read(self.names[name])
        for root in self.roots:
            p = (root/name).resolve()
            if p.is_relative_to(root) and p.is_file() and p.stat().st_size < 64*1024*1024:
                self.found_in[str(root)] += 1
                return p.read_bytes()
        for archive in self.vpks:
            if name in archive:
                entry = archive[name]
                if entry.size > 64*1024*1024:
                    raise BSPError(f'VPK resource exceeds 64 MiB: {name}')
                try:
                    data = entry.read()
                except FileNotFoundError:
                    self.warnings.append(f'{name}: VPK entry is indexed but its data archive is unavailable')
                    continue
                except (OSError, ValueError) as e:
                    raise BSPError(f'cannot read VPK resource {name}: {e}') from e
                self.found_in[archive.file_prefix + '_dir.vpk'] += 1
                return data
        return None

    def has_material(self, name):
        """Is there a VMT by this name? A probe: a miss is not a missing
        dependency (studiomdl tries each $cdmaterials folder in turn)."""
        return self.read('materials/' + name.removesuffix('.vmt') + '.vmt') is not None

    def vmt(self, name):
        """(shader, flat parameter dict) for a material, following `patch`
        includes; None when it cannot be found or parsed."""
        name = name.removesuffix('.vmt')
        if name not in self._vmts:
            self._vmts[name] = self._load_vmt('materials/'+name+'.vmt', set())
        return self._vmts[name]

    def _load_vmt(self, path, seen):
        if path in seen or len(seen) > 4:
            self.warnings.append(f'{path}: VMT include cycle or depth limit'); return None
        seen.add(path)
        raw = self.read(path)
        if raw is None:
            self.missing.append(path); return None
        try:
            shader, body = parse_keyvalues(raw.decode('utf-8', 'replace'))
        except BSPError as e:
            self.warnings.append(f'{path}: {e}'); return None
        flat = {k: v.strip().lower().replace('\\', '/') for k, v in body.items() if isinstance(v, str)}
        if shader == 'patch':
            parent = flat.get('include', '').lstrip('/')
            if not parent:
                self.warnings.append(f'{path}: patch without include'); return None
            if not parent.startswith('materials/'):
                parent = 'materials/'+parent
            if not parent.endswith('.vmt'):
                parent += '.vmt'
            base = self._load_vmt(parent, seen)
            if base is None:
                return None
            shader, params = base[0], dict(base[1])
            for block in ('insert', 'replace'):
                if isinstance(body.get(block), dict):
                    params.update({k: v.strip().lower().replace('\\', '/') for k, v in body[block].items() if isinstance(v, str)})
            return shader, params
        return shader, flat

    def material(self, name):
        """Decoded RGBA albedo (w, h, bytes) or None, plus the VMT parameters."""
        found = self.vmt(name)
        if found is None:
            return None, {}
        shader, params = found
        params = dict(params, shader=shader)
        base = params.get('$basetexture')
        if not base:
            self.warnings.append(f'materials/{name}.vmt: no $basetexture ({shader})'); return None, params
        tex = 'materials/'+base.removesuffix('.vtf')+'.vtf'
        raw = self.read(tex)
        if raw is None:
            self.missing.append(tex); return None, params
        try:
            return _vtf_rgba(raw), params
        except BSPError as e:
            self.warnings.append(f'{tex}: {e}'); return None, params


# ---- models ---------------------------------------------------------------------

def add_models(world, placements, resolver, lod=0):
    """Static props and model entities into the world triangles. Returns
    (placed count by source, model paths that could not be read)."""
    cache = {}; failed = set(); placed = Counter()
    exists = resolver.has_material
    for path, origin, angles, skin, solid, source in placements:
        key = (path, skin)
        if key not in cache:
            base = path.removesuffix('.mdl')
            try:
                blobs = [resolver.read(base+ext) for ext in ('.mdl', '.vvd', '.dx90.vtx')]
                if None in blobs:
                    for ext, blob in zip(('.mdl', '.vvd', '.dx90.vtx'), blobs):
                        if blob is None:
                            resolver.missing.append(base+ext)
                    cache[key] = None
                else:
                    cache[key] = Model(*blobs, skin, exists, lod)
            except BSPError as e:
                resolver.warnings.append(f'{path}: {e}'); cache[key] = None
        model = cache[key]
        if model is None:
            failed.add(path); continue
        m = angle_matrix(*angles)
        for mat, tris in model.groups.items():
            start = len(world.indices)
            for t in range(0, len(tris), 3):
                corners = []
                for pos, nrm, uv in tris[t:t+3]:
                    wp = rotate(m, pos)
                    corners.append((to_runtime(tuple(wp[k]+origin[k] for k in range(3))), norm(rotate(m, nrm)), uv))
                a, b, c = corners
                face = cross(sub(b[0], a[0]), sub(c[0], a[0]))
                if norm(face) == (0., 0., 0.):
                    continue
                # Wind to agree with the model's own normals, whatever the source order.
                if sum(face[k]*(a[1][k]+b[1][k]+c[1][k]) for k in range(3)) < 0:
                    b, c = c, b
                i0 = len(world.vertices); world.vertices.extend((a, b, c)); world.indices.extend((i0, i0+1, i0+2))
            # Source SOLID_NONE (0) props are drawn, not collided with.
            if len(world.indices) > start:
                world.groups.append((mat, start, len(world.indices)-start, solid != 0))
        placed[source] += 1
    return placed, sorted(failed)


def fit_textures(textures, budget):
    """Halve the largest textures until the RGBA total fits `budget`.
    Returns the names downsampled and how many halvings each took."""
    total = sum(len(t[2]) for t in textures.values())
    halved = Counter()
    while total > budget:
        name = max(textures, key=lambda k: (len(textures[k][2]), k))
        w, h, px = textures[name]
        if w <= 4 and h <= 4:
            raise BSPError(f'textures cannot fit a {budget} byte budget')
        nw, nh = max(1, w//2), max(1, h//2)
        im = Image.frombytes('RGBA', (w, h), px).resize((nw, nh), Image.Resampling.BOX)
        textures[name] = (nw, nh, im.tobytes())
        total -= len(px) - nw*nh*4
        halved[name] += 1
    return dict(sorted(halved.items()))


# ---- compile ----------------------------------------------------------------------

def compile_map(source, output, material_roots=(), identifier=None, vpks=(), texture_budget=DEFAULT_TEXTURE_BUDGET,
                prop_lod=0):
    bsp = SourceBSP(source)
    world = bsp.convert()
    resolver = Resolver(bsp, material_roots, vpks)
    prop_warning = None
    try:
        placements = [(*p, 'static_prop') for p in bsp.static_prop_placements()]
    except BSPError as e:
        placements = []; prop_warning = str(e)
    placements += [(m, o, a, sk, so, f'entity:{c}') for m, o, a, sk, so, c in bsp.model_entity_placements()]
    in_sky = [p for p in placements if bsp.in_skybox(p[1])]
    placements = [p for p in placements if not bsp.in_skybox(p[1])]
    placed, models_failed = add_models(world, placements, resolver, prop_lod)

    mats = sorted(set(g[0] for g in world.groups))
    textures = {}; params = {}; placeholders = []; dropped = Counter(); nonsolid_materials = []
    hidden = set()
    for name in mats:
        decoded, p = resolver.material(name)
        params[name] = p
        if translate.material_hidden(p):
            hidden.add(name); dropped['additive surface not drawn'] += 1
            continue
        solid, lost = translate.material_policy(p)
        if not solid:
            nonsolid_materials.append(name)
        for msg in lost:
            dropped[msg] += 1
        if decoded:
            textures[name] = decoded
        else:
            placeholders.append(name); textures[name] = translate.placeholder(name, p)
    mats = [m for m in mats if m not in hidden]
    downsampled = fit_textures(textures, min(texture_budget, RUNTIME_TEXTURE_CAP))
    tex_index = {m: i for i, m in enumerate(mats)}

    buckets = {}
    for mat, first, count, solid in world.groups:
        if mat in hidden:
            continue
        solid = solid and mat not in nonsolid_materials
        buckets.setdefault((mat, solid), []).extend(world.indices[first:first+count])
    indices = []; groups = []; collision_triangles = 0
    for mat, solid in sorted(buckets, key=lambda k: (k[0], not k[1])):
        first = len(indices); indices.extend(buckets[(mat, solid)])
        groups.append((first, len(indices)-first, tex_index[mat], 0 if solid else GROUP_NO_COLLISION))
        if solid:
            collision_triangles += (len(indices)-first)//3

    # Share identical vertices (at the float32 precision they are stored in):
    # every triangle was emitted with its own three. First occurrence order,
    # so the output stays deterministic.
    packed, remap = [], {}
    for k, i in enumerate(indices):
        pos, nrm, uv = world.vertices[i]
        key = struct.pack('<10f', *pos, *nrm, *uv, 0., 0.)
        j = remap.get(key)
        if j is None:
            j = remap[key] = len(packed); packed.append(key)
        indices[k] = j
    del remap

    src = Path(source)
    source_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    if identifier is None:
        identifier = re.sub('[^a-z0-9_-]+', '-', src.stem.lower()).strip('-')[:64]
    r = world.report
    unsupported = list(r['unsupported_features'])
    if prop_warning:
        unsupported.append(prop_warning)
    unsupported += sorted(f'{msg} ({n} materials)' for msg, n in dropped.items())
    lo = r['converted_bounds']['min']; hi = r['converted_bounds']['max']
    lo = [min([lo[k]]+[v[0][k] for v in world.vertices]) for k in range(3)]
    hi = [max([hi[k]]+[v[0][k] for v in world.vertices]) for k in range(3)]
    compat = {
        'map': src.name, 'bsp_version': bsp.version, 'bsp_version_label': r['bsp_version_label'],
        'geometry': {'world_faces': r['world_face_count'], 'vertices': len(packed),
                     'triangles': len(indices)//3, 'collision_triangles': collision_triangles,
                     'world_triangles': r['converted_triangles'], 'degenerate_triangles_dropped': r['degenerate_triangles'],
                     'faces_excluded_by_flag': r['faces_excluded'], 'water_faces': r['water_faces'],
                     'brush_entities_converted': r['brush_entities_converted'],
                     'brush_entities_hidden_at_spawn': r['brush_entities_hidden']},
        'displacements': {'in_bsp': r['displacement_count'], 'converted': r['converted_displacements']},
        'materials': {'used': len(mats), 'resolved': len(mats)-len(placeholders), 'placeholder': len(placeholders),
                      'non_solid': len(nonsolid_materials), 'features_not_reproduced': dict(sorted(dropped.items())),
                      'textures_downsampled': len(downsampled),
                      'texture_bytes': sum(len(t[2]) for t in textures.values())},
        'static_props': {'lump_version': r['static_props']['version'], 'in_bsp': r['static_props']['count'],
                         'placed': placed.get('static_prop', 0), 'model_entities_placed': sum(v for k, v in placed.items() if k != 'static_prop'),
                         'models_unresolved': models_failed, 'left_out_in_3d_skybox': len(in_sky),
                         'model_lod': prop_lod},
        'entities': {'total': r['entity_count'], **{k: sum(v.values()) for k, v in r['entities'].items()},
                     'unsupported_classes': r['entities']['unsupported']},
        'spawns': {'total': len(world.spawns), 'red': sum(s['team'] == translate.RED for s in world.spawns),
                   'blue': sum(s['team'] == translate.BLUE for s in world.spawns),
                   'either': sum(s['team'] is None for s in world.spawns),
                   'grounded': sum('ground_delta' in s for s in world.spawns),
                   'rejected_no_ground': len(r['rejected_spawns'])},
        'dependencies': {'search_path': resolver.search_path(), 'found_in': dict(resolver.found_in),
                         'missing': len(set(resolver.missing))},
        'lumps': r['lumps'], 'unsupported_features': unsupported,
        'warnings': r['warnings'] + resolver.warnings,
    }
    manifest = {
        'package_version': VERSION, 'importer_version': 'source_bsp-0.2.0', 'map_id': identifier, 'display_name': src.stem,
        'source_format': 'Source BSP', 'source_bsp_version': bsp.version, 'source_sha256': source_hash,
        'source_reference': src.name, 'coordinate_transform': TRANSFORM,
        'required_open_halo_runtime': 'external-map-v1',
        'geometry': {'vertices': len(packed), 'triangles': len(indices)//3, 'collision_triangles': collision_triangles,
                     'displacements': r['converted_displacements']},
        'material_paths': mats, 'missing_dependencies': sorted(set(resolver.missing)),
        'placeholder_materials': placeholders, 'non_solid_materials': nonsolid_materials,
        'textures_downsampled': downsampled,
        'supported_features': ['world faces', 'power 2-4 displacement grids', 'brush entities (registry)',
                               f'static prop and model entity models (MDL v44-48, LOD {prop_lod} or the coarsest shipped)', 'player starts with teams (registry)',
                               'albedo VTF (RGBA/BGRA/RGB/BGR/L/LA/A/DXT1/3/5)'],
        'unsupported_features': unsupported, 'conversion_warnings': compat['warnings'],
        'static_props_placed': placed.get('static_prop', 0), 'static_props_unresolved': models_failed,
        'static_prop_models': r['static_props']['models'],
        'entity_translation': r['entities'], 'entities': world.entities, 'spawn_points': world.spawns,
        'flag_points': world.flags,
        'rejected_spawn_points': r['rejected_spawns'],
        'bounds': {'min': lo, 'max': hi}, 'texture_count': len(mats), 'compatibility': compat,
        'source_provenance': 'user supplied; redistribution rights not inferred',
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(manifest_bytes) > 4*1024*1024:
        raise BSPError('runtime manifest exceeds 4 MiB limit')
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('wb') as f:
        f.write(struct.pack(HEADER, MAGIC, VERSION, len(manifest_bytes), len(packed), len(indices), len(groups),
                            len(mats), len(world.spawns), 0, *lo, *hi, 0))
        f.write(manifest_bytes)
        f.write(b''.join(packed))
        for i in indices:
            f.write(struct.pack('<I', i))
        for group in groups:
            f.write(struct.pack('<4I', *group))
        for name in mats:
            w, h, pixels = textures[name]
            f.write(struct.pack('<3I', w, h, len(pixels))); f.write(pixels)
        for sp in world.spawns:
            f.write(struct.pack('<4f', *sp['position'], math.radians(sp['yaw_degrees'])))
    size = out.stat().st_size
    if size > RUNTIME_FILE_CAP:
        compat['warnings'].append(f'package is {size} bytes; Open Halo refuses more than {RUNTIME_FILE_CAP}')
    report = r | {'missing_dependencies': manifest['missing_dependencies'], 'material_warnings': resolver.warnings,
                  'resolved_textures': len(mats)-len(placeholders), 'placeholder_materials': placeholders,
                  'texture_bytes': compat['materials']['texture_bytes'], 'runtime_package_bytes': size,
                  'runtime_package_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                  'static_props_placed': placed.get('static_prop', 0), 'static_props_unresolved': models_failed,
                  'compatibility': compat}
    return manifest, report


def read_manifest(package):
    with Path(package).open('rb') as f:
        h = f.read(64)
        if len(h) != 64:
            raise BSPError('truncated package header')
        magic, version, mlen, vc, ic, gc, tc, sc, flags, *_ = struct.unpack(HEADER, h)
        if magic != MAGIC or version != VERSION:
            raise BSPError('invalid or unsupported package version')
        if mlen > 4*1024*1024 or vc > 5000000 or ic > 15000000 or gc > 100000 or tc > 10000 or sc > 100000:
            raise BSPError('package counts out of range')
        m = f.read(mlen)
        if len(m) != mlen:
            raise BSPError('truncated package manifest')
        return json.loads(m)
