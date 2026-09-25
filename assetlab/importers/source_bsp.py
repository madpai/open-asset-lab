"""Source 1 BSP reader, version-aware. Format definitions: Valve
source-sdk-2013 public/bspfile.h and bspflags.h.

Everything specific to a BSP version lives in VERSIONS; everything the
package means by an entity or material lives in assetlab.translate; every
position goes through assetlab.coords. The reader reports each non-empty
lump it does not use, and why.
"""
from __future__ import annotations
import io
import lzma
import struct
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .. import translate
from ..coords import (SCALE, RUNTIME_MAX_SPAN, angle_matrix, cross, dot, norm, parse_vector,
                      rotate, sub, to_runtime)

MAX_FILE = 512 * 1024 * 1024


class BSPError(ValueError):
    pass


# BSP versions this reader accepts. v19 (Source 2004-2006) and v20
# (Source 2007+: TF2, CS:S after 2010, GMod, Black Mesa) share the lump
# table and every record this importer reads; v20 adds HDR lumps it does
# not need. v21+ (Left 4 Dead 2, Portal 2, CS:GO) change the lump table
# and records and are refused rather than misread.
VERSIONS = {
    19: {'label': 'Source v19 (2004-2006)'},
    20: {'label': 'Source v20 (2007+)'},
}
FACE_LUMP_VERSION = 1          # dface_t, 56 bytes
# Static prop lump versions whose records begin origin, angles, model
# index, leaves, solid, flags, skin (the only fields read). Later fields
# differ by game -- v11 is CS:GO's uniform scale but something else in
# Black Mesa (always 0) -- so they are not interpreted, and said so.
STATIC_PROP_VERSIONS = range(4, 12)
STATIC_PROP_NOTES = {11: 'static prop lump v11: fields after the v10 layout are game-specific and not interpreted (no prop scale)'}

LUMP_NAMES = {
    0: 'entities', 1: 'planes', 2: 'texdata', 3: 'vertexes', 4: 'visibility', 5: 'nodes',
    6: 'texinfo', 7: 'faces', 8: 'lighting', 9: 'occlusion', 10: 'leafs', 11: 'faceids',
    12: 'edges', 13: 'surfedges', 14: 'models', 15: 'worldlights', 16: 'leaffaces',
    17: 'leafbrushes', 18: 'brushes', 19: 'brushsides', 20: 'areas', 21: 'areaportals',
    22: 'propcollision', 23: 'prophulls', 24: 'prophullverts', 25: 'proptris',
    26: 'dispinfo', 27: 'originalfaces', 28: 'physdisp', 29: 'physcollide',
    30: 'vertnormals', 31: 'vertnormalindices', 32: 'disp_lightmap_alphas',
    33: 'disp_verts', 34: 'disp_lightmap_sample_positions', 35: 'game_lump',
    36: 'leafwaterdata', 37: 'primitives', 38: 'primverts', 39: 'primindices', 40: 'pakfile',
    41: 'clipportalverts', 42: 'cubemaps', 43: 'texdata_string_data',
    44: 'texdata_string_table', 45: 'overlays', 46: 'leafmindisttowater',
    47: 'face_macro_texture_info', 48: 'disp_tris', 49: 'physcollidesurface',
    50: 'wateroverlays', 51: 'leaf_ambient_index_hdr', 52: 'leaf_ambient_index',
    53: 'lighting_hdr', 54: 'worldlights_hdr', 55: 'leaf_ambient_lighting_hdr',
    56: 'leaf_ambient_lighting', 57: 'xzippakfile', 58: 'faces_hdr', 59: 'map_flags',
    60: 'overlay_fades',
}
CONSUMED = {0, 1, 2, 3, 5, 6, 7, 10, 12, 13, 14, 26, 33, 35, 40, 43, 44}
# Lumps that carry things Open Halo builds itself (visibility, its own
# collision grid and nav) or that only matter to Source's compiler/tools.
NOT_NEEDED = {
    4: 'visibility: Open Halo draws everything',
    9: 'occluders', 11: 'editor face ids', 16: 'BSP tree',
    17: 'BSP tree', 20: 'area portals', 21: 'area portals', 27: 'pre-split faces',
    30: 'smoothing normals (flat normals used)', 31: 'smoothing normals', 41: 'area portals',
    46: 'water distance', 47: 'macro textures', 48: 'displacement collision flags',
    51: 'ambient light probes', 52: 'ambient light probes', 55: 'ambient light probes',
    56: 'ambient light probes', 59: 'lightmap scale flags', 36: 'leaf water data',
    28: 'displacement physics (displacement surfaces are collided directly)',
    58: 'HDR copy of faces', 32: 'lightmap blending', 34: 'lightmap sampling',
}
# Lumps whose content the package does not reproduce: reported as unsupported.
UNSUPPORTED = {
    8: 'lightmaps', 53: 'HDR lightmaps', 15: 'light entities', 54: 'HDR light entities',
    18: 'brushes: invisible clip/playerclip collision not imported',
    19: 'brush sides: invisible clip/playerclip collision not imported',
    22: 'prop collision', 23: 'prop hulls', 24: 'prop hulls', 25: 'prop triangles',
    29: 'physics collision models (visible triangles used)', 37: 't-junction fix primitives',
    38: 't-junction fix primitives', 39: 't-junction fix primitives', 42: 'cubemaps',
    45: 'overlays/decals', 49: 'physics surfaces', 50: 'water overlays', 57: 'Xbox pakfile',
    60: 'overlay fades',
}

# Surface flags (bspflags.h) that make a face invisible, and the name the
# report counts them under. SURF_WARP (water) is drawn but does not collide.
SURF_EXCLUDE = {0x2: 'sky2d', 0x4: 'sky', 0x40: 'trigger', 0x80: 'nodraw', 0x100: 'hint', 0x200: 'skip'}
SURF_WARP = 0x8
RECORD_SIZES = {1: 20, 2: 32, 3: 12, 6: 72, 7: 56, 12: 4, 13: 4, 14: 48, 26: 176, 33: 20, 44: 4}


def unpack(fmt, data, off=0):
    size = struct.calcsize(fmt)
    if off < 0 or off + size > len(data):
        raise BSPError(f"read outside lump at {off} ({size} bytes)")
    return struct.unpack_from(fmt, data, off)


def vec3(v):
    return to_runtime(v)


def parse_entities(data):
    """Source's entity lump: `{ "key" "value" ... }` blocks. Values may hold
    braces; Source has no escapes. Keys are case-insensitive (lower-cased);
    a repeated key (entity outputs) keeps its last value."""
    text = data.split(b'\0', 1)[0].decode('utf-8', 'replace')
    out, i, n, cur, key = [], 0, len(text), None, None
    while i < n:
        c = text[i]
        if c in ' \t\r\n':
            i += 1
        elif c == '{':
            if cur is not None:
                raise BSPError(f'entity lump: nested block at {i}')
            cur, key = {}, None
            i += 1
        elif c == '}':
            if cur is None or key is not None:
                raise BSPError(f'entity lump: unbalanced block at {i}')
            out.append(cur)
            cur = None
            i += 1
        elif c == '"':
            end = text.find('"', i + 1)
            if end < 0 or cur is None:
                raise BSPError(f'entity lump: stray or unterminated string at {i}')
            s = text[i + 1:end]
            if key is None:
                key = s.lower()
            else:
                cur[key] = s
                key = None
            i = end + 1
        else:
            raise BSPError(f'entity lump: unexpected {c!r} at {i}')
    if cur is not None:
        raise BSPError('entity lump: unterminated block')
    return out


@dataclass
class World:
    vertices: list  # (pos, normal, uv) in runtime units
    indices: list
    groups: list    # (material, first index, count, solid)
    spawns: list
    materials: list
    entities: list
    report: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)   # [{'team', 'position'}] runtime units
    light_uv: dict = field(default_factory=dict)  # vertex -> (face, luxel s, luxel t)
    light_samples: dict = field(default_factory=dict)  # face -> (width, height, RGBExp32 bytes)
    # Breakable brushes: (record from translate.brush_breakable, entity,
    # first group, end group); their groups hold only their triangles.
    breakable_brushes: list = field(default_factory=list)


class SourceBSP:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.stat().st_size > MAX_FILE:
            raise BSPError("BSP exceeds 512 MiB input limit")
        self.data = self.path.read_bytes()
        b = self.data
        if len(b) < 1036:
            raise BSPError("truncated BSP header")
        if b[:4] != b'VBSP':
            raise BSPError("invalid Source BSP magic (expected VBSP)")
        self.version = unpack('<I', b, 4)[0]
        if self.version not in VERSIONS:
            known = ', '.join(str(v) for v in VERSIONS)
            raise BSPError(f"unsupported BSP version {self.version}; this reader handles v{known}"
                           + (" (v21+ changes the lump table)" if self.version > 20 else ""))
        self.revision = unpack('<I', b, 1032)[0]
        self.lumps = []
        for i in range(64):
            off, length, version, fourcc = unpack('<4I', b, 8 + 16*i)
            if off > len(b) or length > len(b) - off:
                raise BSPError(f"lump {i} outside file (offset={off}, length={length})")
            self.lumps.append((off, length, version, fourcc))
        if self.lumps[7][2] != FACE_LUMP_VERSION:
            raise BSPError(f'unsupported face lump version {self.lumps[7][2]}; dface_t v{FACE_LUMP_VERSION} required')
        self._cache = {}
        for i, size in RECORD_SIZES.items():
            d = self.lump(i)
            if len(d) % size:
                raise BSPError(f"lump {i} ({LUMP_NAMES[i]}) has invalid record size {len(d)} for {size}-byte records")
        self.entities = parse_entities(self.lump(0))
        self.materials = self._materials()

    # ---- lumps -----------------------------------------------------------

    def lump(self, i):
        if i in self._cache:
            return self._cache[i]
        off, n, _, fourcc = self.lumps[i]
        d = self.data[off:off+n]
        if n and (fourcc or d[:4] == b'LZMA'):
            d = self._lzma(d, fourcc, f'lump {i}')
        self._cache[i] = d
        return d

    @staticmethod
    def _lzma(d, expect, what):
        if len(d) < 17 or d[:4] != b'LZMA':
            raise BSPError(f"{what} has unsupported compression")
        raw_n, zipped_n = unpack('<II', d, 4)
        if raw_n > MAX_FILE or zipped_n > len(d) - 17 or (expect and expect != raw_n):
            raise BSPError(f"{what} invalid compressed size")
        p = d[12]
        lc, lp, pb = p % 9, (p // 9) % 5, p // 45
        if pb > 4:
            raise BSPError(f"{what} invalid LZMA properties")
        dictionary = unpack('<I', d, 13)[0]
        if dictionary < 4096 or dictionary > 64*1024*1024:
            raise BSPError(f'{what} invalid LZMA dictionary size')
        try:
            out = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[dict(
                id=lzma.FILTER_LZMA1, dict_size=dictionary, lc=lc, lp=lp, pb=pb)]).decompress(
                d[17:17+zipped_n], max_length=raw_n+1)
        except lzma.LZMAError as e:
            raise BSPError(f"{what} LZMA decompression failed: {e}") from e
        if len(out) < raw_n:
            raise BSPError(f"{what} decompressed length mismatch")
        return out[:raw_n]

    def lump_report(self):
        """Every non-empty lump: consumed, not needed (and why), or unsupported (and what is lost)."""
        rows = {'consumed': [], 'not_needed': {}, 'unsupported': {}, 'unknown': []}
        for i, (_, n, _, _) in enumerate(self.lumps):
            if not n:
                continue
            name = LUMP_NAMES.get(i, f'lump{i}')
            if i in CONSUMED:
                rows['consumed'].append(name)
            elif i in NOT_NEEDED:
                rows['not_needed'][name] = NOT_NEEDED[i]
            elif i in UNSUPPORTED:
                rows['unsupported'][name] = UNSUPPORTED[i]
            else:
                rows['unknown'].append(name)
        return rows

    def _materials(self):
        td = self.lump(2); names = self.lump(43); table = self.lump(44)
        out = []
        for i in range(len(td)//32):
            name_id = unpack('<i', td, i*32+12)[0]
            if name_id < 0 or name_id >= len(table)//4:
                raise BSPError(f"texdata {i} invalid material name index")
            off = unpack('<i', table, name_id*4)[0]
            if off < 0 or off >= len(names):
                raise BSPError(f"texdata {i} material string outside lump")
            end = names.find(b'\0', off)
            if end < 0:
                raise BSPError(f"texdata {i} material string not terminated")
            out.append(names[off:end].decode('utf-8', 'replace').replace('\\', '/').lower())
        return out

    # ---- areas -------------------------------------------------------------

    def area_at(self, point):
        """The BSP area holding a Source-space point: the world model's node
        tree down to a leaf. Nodes (lump 5) and leaves (lump 10) are read
        only for this; a leaf is 56 bytes with its ambient cube (lump
        version 0) and 32 without (version 1). Returns None when the tree
        cannot be walked."""
        nodes, planes, leafs = self.lump(5), self.lump(1), self.lump(10)
        size = 56 if self.lumps[10][2] == 0 else 32
        if not nodes or not leafs or len(nodes) % 32 or len(leafs) % size:
            return None
        n = unpack('<i', self.lump(14), 36)[0]
        for _ in range(len(nodes)//32 + 1):
            if n < 0:
                leaf = -1 - n
                if leaf >= len(leafs)//size:
                    return None
                return unpack('<h', leafs, leaf*size + 6)[0] & 0x1ff
            if n >= len(nodes)//32:
                return None
            plane, front, back = unpack('<iii', nodes, n*32)
            if not 0 <= plane < len(planes)//20:
                return None
            nx, ny, nz, dist = unpack('<4f', planes, plane*20)
            n = front if nx*point[0] + ny*point[1] + nz*point[2] - dist >= 0 else back
        return None

    def skybox_area(self):
        """The 3D skybox's area (the sky_camera's), when it is a room of its
        own: not area 0 (solid) and holding no player start. Open Halo keeps
        its own sky, so this room is left out rather than imported as a
        miniature floating beside the map. None: keep everything."""
        if hasattr(self, '_sky_area'):
            return self._sky_area
        self._sky_area = None
        cams = [parse_vector(e.get('origin', '')) for e in self.entities
                if e.get('classname', '').lower() == 'sky_camera']
        if len(cams) == 1 and cams[0] is not None:
            area = self.area_at(cams[0])
            starts = [parse_vector(e.get('origin', '')) for e in self.entities
                      if translate.spawn_team(e) is not False]
            if area and not any(p is not None and self.area_at(p) == area for p in starts):
                self._sky_area = area
        return self._sky_area

    def in_skybox(self, point):
        area = self.skybox_area()
        return area is not None and self.area_at(point) == area

    def _models(self):
        d = self.lump(14)
        return [(unpack('<i', d, o+40)[0], unpack('<i', d, o+44)[0], unpack('<6f', d, o)) for o in range(0, len(d), 48)]

    # ---- static props ----------------------------------------------------

    def _prop_lump(self):
        """(version, bytes) of the static prop game lump, or (None, b'')."""
        d = self.lump(35)
        if len(d) < 4:
            return None, b''
        n = unpack('<i', d)[0]
        if n < 0 or n > 4096 or 4+n*16 > len(d):
            raise BSPError('invalid game lump directory')
        for i in range(n):
            tag, flags, version, off, length = unpack('<IHHii', d, 4+i*16)
            if tag != int.from_bytes(b'prps', 'little'):
                continue
            # Game lump offsets are absolute file offsets.
            if off < 0 or length < 0 or off+length > len(self.data):
                raise BSPError('static prop game lump outside file')
            p = self.data[off:off+length]
            if flags & 1:
                p = self._lzma(self.data[off:], 0, 'static prop lump')
            return version, p
        return None, b''

    def static_prop_placements(self):
        """Every static prop: (model path, origin, angles, skin, solid). Lump
        versions 4-11 share the leading fields; the record size is whatever
        divides the rest of the lump. Other versions raise, so the caller
        reports them instead of guessing."""
        version, p = self._prop_lump()
        if version is None:
            return []
        if version not in STATIC_PROP_VERSIONS:
            raise BSPError(f'static prop lump version {version} not supported (4-11)')
        model_n = unpack('<i', p)[0]
        if model_n < 0 or model_n > 65536 or 4+model_n*128 > len(p):
            raise BSPError('invalid static prop model dictionary')
        models = [p[4+j*128:4+(j+1)*128].split(b'\0', 1)[0].decode('utf-8', 'replace').replace('\\', '/').lower()
                  for j in range(model_n)]
        pos = 4+model_n*128
        leaf_n = unpack('<i', p, pos)[0]; pos += 4
        if leaf_n < 0:
            raise BSPError('invalid static prop leaf table')
        pos += leaf_n*2
        count = unpack('<i', p, pos)[0]; pos += 4
        if count <= 0:
            return []
        if count > 100000 or (len(p)-pos) % count:
            raise BSPError('static prop records do not divide the lump')
        size = (len(p)-pos)//count
        if size < 36:
            raise BSPError('static prop record too small')
        out = []
        for k in range(count):
            o = pos+k*size
            origin = unpack('<3f', p, o); angles = unpack('<3f', p, o+12); mt = unpack('<H', p, o+24)[0]
            solid = p[o+30]; skin = unpack('<i', p, o+32)[0]
            if mt >= len(models):
                raise BSPError('static prop model index out of range')
            out.append((models[mt], origin, angles, skin, solid))
        return out

    def model_entity_placements(self):
        """Model entities the registry places like static props:
        (model, origin, angles, skin, solid, classname)."""
        out = []
        moved = self.door_offsets()
        for e in self.entities:
            c = e.get('classname', '').lower()
            rule = translate.MODEL_CLASSES.get(c)
            model = e.get('model', '').replace('\\', '/').lower()
            if rule is None or not model.endswith('.mdl'):
                continue
            origin = parse_vector(e.get('origin', '0 0 0')) or (0.0, 0.0, 0.0)
            # A handle or window parented to a door goes where the door went.
            shift = moved.get(e.get('parentname', '').lower())
            if shift:
                origin = tuple(origin[k] + shift[k] for k in range(3))
            angles = parse_vector(e.get('angles', '0 0 0')) or (0.0, 0.0, 0.0)
            try:
                skin = int(e.get('skin', '0'))
            except ValueError:
                skin = 0
            out.append((model, origin, angles, skin, 6 if rule['solid'] else 0, c))
        return out

    def door_offsets(self):
        """{targetname: Source-unit shift} for every door the registry
        imports open."""
        models = self._models(); out = {}
        for e in self.entities:
            rule = translate.BRUSH_CLASSES.get(e.get('classname', '').lower())
            name = e.get('targetname', '').lower(); model = e.get('model', '')
            if not rule or not rule.get('open') or not name or not model.startswith('*'):
                continue
            try:
                box = models[int(model[1:])][2]
            except (ValueError, IndexError):
                continue
            out[name] = translate.door_open_offset(e, (box[:3], box[3:]))
        return out

    # ---- inspection --------------------------------------------------------

    def _pak_names(self):
        pak = self.lump(40)
        if not pak:
            return []
        try:
            with zipfile.ZipFile(io.BytesIO(pak)) as z:
                entries = z.infolist()
                if len(entries) > 10000 or any(x.file_size > 64*1024*1024 for x in entries):
                    raise BSPError('embedded pakfile resource count or size exceeds limit')
                return [x.filename for x in entries]
        except zipfile.BadZipFile:
            raise BSPError('embedded pakfile is invalid ZIP')

    def entity_report(self):
        roles = {'spawn': Counter(), 'brush': Counter(), 'model': Counter(), 'not_geometry': Counter(), 'unsupported': Counter()}
        for e in self.entities:
            c = e.get('classname', '?').lower()
            roles[translate.entity_role(c)][c] += 1
        return {k: dict(sorted(v.items())) for k, v in roles.items()}

    def inspect(self):
        models = self._models()
        prop_version = None
        try:
            prop_version, _ = self._prop_lump()
            props = self.static_prop_placements()
            prop_info = {'version': prop_version, 'count': len(props), 'supported': True,
                         'models': sorted({p[0] for p in props})}
        except BSPError as e:
            prop_info = {'version': prop_version, 'count': None, 'supported': False, 'models': [], 'warning': str(e)}
        embedded = self._pak_names()
        return {'source_format': 'Source BSP', 'bsp_version': self.version,
                'bsp_version_label': VERSIONS[self.version]['label'], 'map_revision': self.revision,
                'source_bytes': len(self.data),
                'world_bounds_source': {'min': models[0][2][:3], 'max': models[0][2][3:6]} if models else None,
                'face_count': len(self.lump(7))//56, 'world_face_count': models[0][1] if models else 0,
                'vertex_count': len(self.lump(3))//12, 'displacement_count': len(self.lump(26))//176,
                'brush_model_count': max(0, len(models)-1), 'material_count': len(set(self.materials)),
                'entity_count': len(self.entities), 'entities': self.entity_report(),
                'static_props': prop_info, 'embedded_resources': len(embedded),
                'embedded_vmt': sum(x.lower().endswith('.vmt') for x in embedded),
                'embedded_vtf': sum(x.lower().endswith('.vtf') for x in embedded),
                'compressed_lumps': [LUMP_NAMES.get(i, str(i)) for i, (o, n, v, f) in enumerate(self.lumps) if n and f],
                'lumps': self.lump_report()}

    # ---- conversion --------------------------------------------------------

    def convert(self):
        vdata = self.lump(3); edges = self.lump(12); surf = self.lump(13); faces = self.lump(7)
        planes = self.lump(1); texinfo = self.lump(6); td = self.lump(2); disp = self.lump(26); dv = self.lump(33)
        models = self._models()
        if not models:
            raise BSPError('world model missing')
        vertices = []; indices = []; groups = []; warnings = []
        light_uv = {}; light_samples = {}; active_light = [None]
        lighting = self.lump(8)
        stats = Counter(); excluded = Counter(); material_tri = Counter()
        split = [False]           # the next triangle starts a group of its own
        breakable_brushes = []

        def point(index):
            if index < 0 or index >= len(vdata)//12:
                raise BSPError(f'invalid vertex index {index}')
            return unpack('<3f', vdata, index*12)

        def addtri(a, b, c, mat, uvfn, normal, solid, xf, fixed=False, light_coords=None):
            pa, pb, pc = (vec3(xf(p)) for p in (a, b, c))
            n = norm(cross(sub(pb, pa), sub(pc, pa)))
            if n == (0., 0., 0.):
                stats['degenerate_triangles'] += 1
                return
            if fixed:
                normal = n
            elif dot(n, normal) < 0:
                b, c = c, b; pb, pc = pc, pb
                if light_coords is not None:
                    light_coords = (light_coords[0], light_coords[2], light_coords[1])
            start = len(vertices)
            for j, (p, rp) in enumerate(((a, pa), (b, pb), (c, pc))):
                if active_light[0] is not None:
                    light_uv[len(vertices)] = light_coords[j] if light_coords else active_light[0](p)
                vertices.append((rp, normal, uvfn(p)))
            indices.extend((start, start+1, start+2)); material_tri[mat] += 1
            key = (mat, solid)
            if split[0]:
                split[0] = False
                groups.append((mat, len(indices)-3, 3, solid))
            elif groups and groups[-1][0] == mat and groups[-1][3] == solid and groups[-1][1]+groups[-1][2] == len(indices)-3:
                m, s, n0, so = groups[-1]; groups[-1] = (m, s, n0+3, so)
            else:
                groups.append((mat, len(indices)-3, 3, solid))

        sky = self.skybox_area()

        def convert_faces(first, count, xf, rot, entity_solid, skip_sky=False):
            if first < 0 or count < 0 or first+count > len(faces)//56:
                raise BSPError('invalid model face range')
            for fi in range(first, first+count):
                o = fi*56
                plane, side, _, firstedge, numedges, ti, di = unpack('<HBBihhh', faces, o)
                if numedges < 3:
                    stats['faces_without_area'] += 1
                    continue
                if firstedge < 0 or firstedge+numedges > len(surf)//4:
                    raise BSPError(f'face {fi} invalid surfedge range')
                if ti < 0 or ti >= len(texinfo)//72:
                    excluded['no_texinfo'] += 1
                    continue
                to = ti*72
                flags, tdi = unpack('<ii', texinfo, to+64)
                if tdi < 0 or tdi >= len(self.materials):
                    raise BSPError(f'face {fi} invalid texdata index')
                hidden = [name for bit, name in SURF_EXCLUDE.items() if flags & bit]
                if hidden:
                    excluded[hidden[0]] += 1
                    continue
                mat = self.materials[tdi]
                solid = entity_solid and not flags & SURF_WARP
                if flags & SURF_WARP:
                    stats['water_faces'] += 1
                uvec = unpack('<4f', texinfo, to); vvec = unpack('<4f', texinfo, to+16)
                width, height = unpack('<ii', td, tdi*32+16)
                if width <= 0 or height <= 0:
                    raise BSPError(f'face {fi} invalid texture dimensions')
                # Texture coordinates come from the source-space vertex (texinfo is
                # defined there), before the entity transform.
                uvfn = lambda p, u=uvec, v=vvec, w=width, h=height: (
                    (p[0]*u[0]+p[1]*u[1]+p[2]*u[2]+u[3])/w, (p[0]*v[0]+p[1]*v[1]+p[2]*v[2]+v[3])/h)
                active_light[0] = None
                lightofs = unpack('<i', faces, o+20)[0]
                mins = unpack('<2i', faces, o+28)
                sizes = unpack('<2i', faces, o+36)
                lw, lh = sizes[0]+1, sizes[1]+1
                if lightofs >= 0 and 0 < lw <= 1022 and 0 < lh <= 1022 and lightofs+lw*lh*4 <= len(lighting):
                    lu = unpack('<4f', texinfo, to+32); lv = unpack('<4f', texinfo, to+48)
                    light_samples[fi] = (lw, lh, lighting[lightofs:lightofs+lw*lh*4])
                    active_light[0] = lambda p, f=fi, u=lu, v=lv, mi=mins: (f,
                        sum(p[k]*u[k] for k in range(3))+u[3]-mi[0],
                        sum(p[k]*v[k] for k in range(3))+v[3]-mi[1])
                elif lightofs >= 0 and lighting:
                    warnings.append(f'face {fi}: invalid or oversized lightmap; unlit fallback')
                polygon = []
                for k in range(numedges):
                    ei = unpack('<i', surf, (firstedge+k)*4)[0]
                    if abs(ei) >= len(edges)//4:
                        raise BSPError(f'face {fi} invalid edge index {ei}')
                    a, b = unpack('<HH', edges, abs(ei)*4)
                    polygon.append(point(a if ei >= 0 else b))
                if skip_sky and self.area_at(tuple(sum(p[k] for p in polygon)/len(polygon) for k in range(3))) == sky:
                    excluded['3d_skybox'] += 1
                    continue
                if plane >= len(planes)//20:
                    raise BSPError(f'face {fi} invalid plane index')
                base = norm(unpack('<3f', planes, plane*20))
                if side:
                    base = tuple(-x for x in base)
                if base == (0., 0., 0.):
                    stats['degenerate_triangles'] += 1
                    continue
                base = rot(base)
                if di >= 0:
                    self._displacement(fi, di, polygon, disp, dv, numedges, mat, uvfn, base, solid, xf, addtri,
                                       sizes if active_light[0] is not None else None)
                    stats['converted_displacements'] += 1
                else:
                    for j in range(1, len(polygon)-1):
                        addtri(polygon[0], polygon[j], polygon[j+1], mat, uvfn, base, solid, xf)

        ident = lambda p: p
        convert_faces(models[0][0], models[0][1], ident, ident, True, sky is not None)

        # Brush entities, by the registry.
        brush_notes = Counter()
        for e in self.entities:
            rule = translate.brush_rule(e)
            model = e.get('model', '')
            if rule is None:
                if e.get('classname', '').lower() in translate.BRUSH_CLASSES:
                    stats['brush_entities_hidden'] += 1  # StartDisabled / rendermode 10
                continue
            if not model.startswith('*'):
                continue
            try:
                mi = int(model[1:])
            except ValueError:
                warnings.append(f"{e.get('classname')}: malformed brush model {model!r}")
                continue
            if mi <= 0 or mi >= len(models):
                warnings.append(f"{e.get('classname')}: brush model {model} out of range")
                continue
            solid, note = rule
            origin = parse_vector(e.get('origin', '0 0 0')) or (0.0, 0.0, 0.0)
            if sky is not None and self.in_skybox(origin):
                excluded['3d_skybox'] += 1
                continue
            angles = parse_vector(e.get('angles', '0 0 0')) or (0.0, 0.0, 0.0)
            if translate.BRUSH_CLASSES[e.get('classname', '').lower()].get('open'):
                box = models[mi][2]
                shift = translate.door_open_offset(e, (box[:3], box[3:]))
                origin = tuple(origin[k] + shift[k] for k in range(3))
                stats['doors_opened'] += any(shift)
            m = angle_matrix(*angles)
            xf = lambda p, m=m, o=origin: tuple(r + oo for r, oo in zip(rotate(m, p), o))
            rot = lambda v, m=m: rotate(m, v)
            brk = translate.brush_breakable(e)
            g0 = len(groups)
            split[0] = brk is not None
            convert_faces(models[mi][0], models[mi][1], xf, rot, solid)
            split[0] = False
            if brk is not None and len(groups) > g0:
                breakable_brushes.append((brk, e, g0, len(groups)))
                # Whatever follows starts afresh too, not inside its groups.
                split[0] = True
            stats['brush_entities'] += 1
            if note:
                brush_notes[f"{e.get('classname', '').lower()}: {note}"] += 1

        if not indices:
            raise BSPError('world geometry is empty')

        # Player starts, by the registry.
        spawns = []
        for e in self.entities:
            team = translate.spawn_team(e)
            if team is False:
                continue
            p = parse_vector(e.get('origin', ''))
            if p is None:
                warnings.append(f"{e.get('classname')}: malformed origin, start skipped")
                continue
            angles = parse_vector(e.get('angles', '')) if 'angles' in e else None
            try:
                yaw = angles[1] if angles else float(e.get('angle', '0'))
            except ValueError:
                yaw = 0.0
            spawns.append({'position': vec3(p), 'yaw_degrees': yaw, 'classname': e['classname'].lower(), 'team': team})
        self._ground_spawns(spawns, vertices, indices, groups, warnings)
        # A start with no floor under it would drop a player into the void:
        # it is reported, not shipped.
        rejected_spawns = [sp for sp in spawns if 'rejected' in sp]
        spawns = [sp for sp in spawns if 'rejected' not in sp]

        bounds_min = [min(v[0][k] for v in vertices) for k in range(3)]
        bounds_max = [max(v[0][k] for v in vertices) for k in range(3)]
        if max(bounds_max[k]-bounds_min[k] for k in range(3)) > RUNTIME_MAX_SPAN:
            raise BSPError('converted bounds exceed Source coordinate limits')
        report = self.inspect()
        unsupported_features = sorted(set(report['lumps']['unsupported'].values()))
        prop_version = report['static_props'].get('version')
        if prop_version in STATIC_PROP_NOTES:
            unsupported_features.append(STATIC_PROP_NOTES[prop_version])
        if sky is not None:
            unsupported_features.append('3D skybox: left out (Open Halo keeps its own sky)')
        elif any(e.get('classname', '').lower() == 'sky_camera' for e in self.entities):
            unsupported_features.append('3D skybox: its geometry is imported unscaled at its build location')
        report.update({
            'converted_vertices': len(vertices), 'converted_triangles': len(indices)//3,
            'converted_displacements': stats['converted_displacements'],
            'degenerate_triangles': stats['degenerate_triangles'],
            'brush_entities_converted': stats['brush_entities'],
            'brush_entities_hidden': stats['brush_entities_hidden'],
            'brush_entity_notes': dict(sorted(brush_notes.items())),
            'water_faces': stats['water_faces'],
            'faces_excluded': dict(sorted(excluded.items())),
            'converted_bounds': {'min': bounds_min, 'max': bounds_max},
            'used_materials': dict(material_tri), 'spawns': spawns, 'rejected_spawns': rejected_spawns,
            'warnings': warnings,
            'unsupported_features': unsupported_features})
        if not spawns:
            warnings.append('no supported player start entity')
        flags = []
        for e in self.entities:
            team = translate.flag_team(e)
            p = parse_vector(e.get('origin', ''))
            if team is not None and p is not None and not any(f['team'] == team for f in flags):
                flags.append({'team': team, 'position': vec3(p)})
        split[0] = False
        return World(vertices, indices, groups, spawns, self.materials, self.entities, report, flags,
                     light_uv=light_uv, light_samples=light_samples, breakable_brushes=breakable_brushes)

    def _displacement(self, fi, di, polygon, disp, dv, numedges, mat, uvfn, base, solid, xf, addtri, light_size=None):
        if di >= len(disp)//176:
            raise BSPError(f'face {fi} invalid displacement index')
        if numedges != 4:
            raise BSPError(f'face {fi} displacement base has {numedges} edges')
        do = di*176
        startpos = unpack('<3f', disp, do); dvstart, _, power = unpack('<iii', disp, do+12)
        if power not in (2, 3, 4):
            raise BSPError(f'face {fi} unsupported displacement power {power}')
        side_n = (1 << power)+1
        if dvstart < 0 or dvstart+side_n*side_n > len(dv)//20:
            raise BSPError(f'face {fi} displacement vertex range invalid')
        corner = min(range(4), key=lambda j: sum((polygon[j][k]-startpos[k])**2 for k in range(3)))
        p0, p1, p2, p3 = (polygon[(corner+j) % 4] for j in range(4))
        # Valve CCoreDispInfo layout: the outer (row) index advances p0->p1
        # and the inner (column) index advances p0->p3.
        grid = []
        for y in range(side_n):
            s = y/(side_n-1); row = []
            for x in range(side_n):
                t = x/(side_n-1)
                basepos = tuple((1-s)*(1-t)*p0[k]+s*(1-t)*p1[k]+s*t*p2[k]+(1-s)*t*p3[k] for k in range(3))
                vv = unpack('<5f', dv, (dvstart+y*side_n+x)*20)
                # Valve's DispMapToCoreDispInfo sets ordered quad corners to
                # (0,0), (0,height), (width,height), (width,0), independent
                # of texinfo projection. The displacement start corner is p0.
                # See Source SDK's vbsp/disp_vbsp.cpp.
                lm = (fi, t*light_size[0], s*light_size[1]) if light_size else None
                row.append((tuple(basepos[k]+vv[k]*vv[3] for k in range(3)), lm))
            grid.append(row)
        # One winding for the whole surface, from the flat base quad.
        flip = dot(cross(sub(p1, p0), sub(p3, p0)), base) < 0
        for y in range(side_n-1):
            for x in range(side_n-1):
                a, b, c, d = grid[y][x], grid[y+1][x], grid[y+1][x+1], grid[y][x+1]
                if flip:
                    b, d = d, b
                # Alternate diagonals like Source to avoid directional creases.
                if (x+y) % 2:
                    pairs = ((a, b, c), (a, c, d))
                else:
                    pairs = ((a, b, d), (b, c, d))
                for tri in pairs:
                    addtri(*(v[0] for v in tri), mat, uvfn, base, solid, xf, True,
                           light_coords=tuple(v[1] for v in tri) if light_size else None)

    @staticmethod
    def _ground_spawns(spawns, vertices, indices, groups, warnings):
        """Put each start on the solid walkable triangle beneath it: Source
        start origins sit a game-specific height above the floor."""
        solid_tris = [t for m, first, count, solid in groups if solid for t in range(first, first+count, 3)]
        for sp in spawns:
            x, y, z = sp['position']; best = None
            for t in solid_tris:
                a, b, c = (vertices[indices[t+j]][0] for j in range(3))
                if x < min(a[0], b[0], c[0]) or x > max(a[0], b[0], c[0]) or y < min(a[1], b[1], c[1]) or y > max(a[1], b[1], c[1]):
                    continue
                det = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(det) < 1e-12:
                    continue
                u = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det
                v = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det
                if u < -.0001 or v < -.0001 or u+v > 1.0001:
                    continue
                if abs(norm(cross(sub(b, a), sub(c, a)))[2]) < .5:
                    continue
                gz = u*a[2]+v*b[2]+(1-u-v)*c[2]
                # Up to 0.2 wu above the origin still counts (an origin inside a ramp).
                if gz <= z+.2 and (best is None or gz > best):
                    best = gz
            sp['source_origin'] = sp['position']
            # 1.5 wu (15 ft) is far more than any Source game's origin-to-feet offset.
            if best is not None and z-best < 1.5:
                sp['position'] = (x, y, best)
                sp['ground_delta'] = z-best
            else:
                sp['rejected'] = 'no walkable ground within 1.5 wu below'
                warnings.append(f"start at {x:.2f},{y:.2f},{z:.2f} rejected: no walkable ground within 1.5 wu below")
