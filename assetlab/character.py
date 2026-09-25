"""Characters and weapons from Source models, into OALASSET v1 packages.

The same rules as maps: files come through the configured search path,
what a Source sequence means comes from the translation registry, every
position goes through coords, and whatever cannot be reproduced is
reported. One code path for any model the registry's families cover.

OALASSET v1 (little-endian):
  header  '<4sIIII' + 12 zero bytes: 'OALA', version 1, manifest bytes, model count, 0
  manifest JSON
  per model:
    '<8I' vertex, index, group, texture, bone, attachment, clip counts, 0
    vertices  48 bytes: pos 3f, normal 3f, uv 2f, bone 4B (3 used), weight 3f... packed
              as pos3 nrm3 uv2 (32) + bones 4B (4) + weights 3f (12)
    indices   u32
    groups    '<4I' first, count, texture, flags
    textures  '<3I' w, h, bytes + RGBA
    bones     64-byte name, '<i' parent, 12f bind-inverse (3x4 row-major,
              runtime units), 3f bind position, 4f bind rotation (x,y,z,w)  = 144 bytes
    attachments 64-byte name, '<i' bone, 12f local 3x4                     = 116 bytes
    clips     16-byte role, '<fII' fps, frames, loop, then frames x bones x
              (4f rotation + 3f position)
  then per sound (weapons): 16-byte role, '<III' rate, channels, frames + int16
Names are NUL-padded ASCII; the manifest repeats them for people.
"""
from __future__ import annotations
import array
import hashlib
import io
import json
import math
import re
import struct
import wave
from pathlib import Path

from . import translate
from .coords import SCALE, TRANSFORM
from .importers.source_bsp import BSPError
from .importers.source_studio import Skinned, Studio, q_mul, q_norm, q_slerp
from .package import Resolver, fit_textures

MAGIC = b'OALA'
VERSION = 1
HEADER = '<4sIIII12x'   # 32 bytes
CHARACTER_TEXTURE_BUDGET = 32 * 1024 * 1024


class _Rig:
    """A model plus the files it includes, with bone maps onto the model's skeleton."""

    def __init__(self, resolver, path):
        self.resolver = resolver
        self.main = self._load(path)
        self.files = [self.main]
        seen = {path.lower()}
        for inc in self.main.includes:
            if inc in seen:
                continue
            seen.add(inc)
            try:
                self.files.append(self._load(inc))
            except BSPError as e:
                resolver.warnings.append(f'{inc}: {e}')
        self.maps = []
        for f in self.files:
            self.maps.append([self.main.bone_index.get(b['name'].lower(), -1) for b in f.bones])

    def _load(self, path):
        data = self.resolver.read(path)
        if data is None:
            self.resolver.missing.append(path)
            raise BSPError(f'{path} not found')
        st = Studio(data, name=path)
        if st.ani_name:
            ani = self.resolver.read(st.ani_name)
            if ani is None:
                self.resolver.missing.append(st.ani_name)
            st.ani = ani
        return st

    def find_sequences(self, activity=None, label=None):
        out = []
        for fi, f in enumerate(self.files):
            for s in f.sequences:
                if activity and s['activity'] == activity.upper():
                    out.append((fi, s))
                elif label and s['label'].lower() == label.lower():
                    out.append((fi, s))
        return out

    def pick_cell(self, fi, seq, move):
        """The blend-grid anim for a direction: by root motion, else by
        move_x / move_y pose parameters, else the grid's centre."""
        f = self.files[fi]
        grid = seq['grid']
        if len(grid) == 1 or move is None:
            return grid[len(grid)//2] if move is None and len(grid) > 1 else grid[0]
        want = math.atan2(move[1], move[0])
        best, best_d = None, None
        for a in grid:
            if not 0 <= a < len(f.anims):
                continue
            m = f.movement(f.anims[a])
            if m is None or math.hypot(m[0], m[1]) < 1.0:
                continue
            d = abs((math.atan2(m[1], m[0]) - want + math.pi) % (2*math.pi) - math.pi)
            if best_d is None or d < best_d:
                best, best_d = a, d
        if best is not None:
            return best
        # No root motion: read the pose parameters by name.
        gs = seq['groupsize']; value = {'move_x': move[0], 'move_y': move[1]}
        idx = [gs[0]//2, gs[1]//2]
        for axis in range(2):
            p = seq['param'][axis]
            if 0 <= p < len(f.pose_params) and f.pose_params[p]['name'] in value and gs[axis] > 1:
                lo, hi = seq['param_start'][axis], seq['param_end'][axis]
                t = (value[f.pose_params[p]['name']] - lo) / (hi - lo) if hi != lo else .5
                idx[axis] = max(0, min(gs[axis]-1, round(t*(gs[axis]-1))))
        return grid[idx[0] + idx[1]*gs[0]]

    def bind(self):
        return [(b['pos'], b['quat']) for b in self.main.bones]

    def frames(self, fi, anim_i):
        return max(1, self.files[fi].anims[anim_i]['frames'])

    def pose(self, fi, anim_i, frame, base=None, weights=None):
        """Main-skeleton local transforms for one frame of an anim, laid
        over `base` (the bind pose when None) with per-bone weights."""
        pose = list(base) if base is not None else self.bind()
        f, bmap = self.files[fi], self.maps[fi]
        for lb, (pos, q, delta) in f.sample(anim_i, frame).items():
            mb = bmap[lb] if lb < len(bmap) else -1
            if mb < 0:
                continue
            w = 1.0 if weights is None else (weights[lb] if lb < len(weights) else 0.0)
            if w <= 0.0:
                continue
            bp, bq = pose[mb]
            if not delta and fi != 0:
                # Included clips store locals from their own skeleton. A
                # citizen neck is a few inches; this body's may be a foot.
                # Keep the motion, measure it from this bone's bind.
                src, dst = f.bones[lb], self.main.bones[mb]
                sq, sp = src['quat'], src['pos']
                inv = (-sq[0], -sq[1], -sq[2], sq[3])
                q = q_norm(q_mul(dst['quat'], q_norm(q_mul(inv, q))))
                pos = tuple(dst['pos'][k] + (pos[k] - sp[k]) for k in range(3))
            if delta:
                nq = q_norm(q_mul(bq, q_slerp((0, 0, 0, 1), q, w)))
                npos = tuple(bp[k] + pos[k]*w for k in range(3))
            else:
                nq = q_slerp(bq, q, w)
                npos = tuple(bp[k] + (pos[k]-bp[k])*w for k in range(3))
            pose[mb] = (npos, nq)
        return pose


def _clip_from_recipe(rig, recipe, hold):
    """Frames of main-skeleton local transforms, and a note of what was used."""
    fill = lambda n: n.replace('{hold}', hold).replace('{HOLD}', hold.upper())
    base = None
    for act in recipe.get('activity', []):
        found = rig.find_sequences(activity=fill(act))
        if found:
            base = found[0]; break
    if base is None:
        return None, None
    fi, seq = base
    anim_i = rig.pick_cell(fi, seq, recipe.get('move'))
    if not 0 <= anim_i < len(rig.files[fi].anims):
        return None, None
    layer = None
    for name in recipe.get('layer', []):
        found = rig.find_sequences(label=fill(name))
        if found:
            layer = found[0]; break
    for act in recipe.get('layer_activity', []):
        found = rig.find_sequences(activity=fill(act))
        if found:
            layer = found[0]; break
    if recipe.get('gesture') and layer is None:
        return None, None
    base_n = rig.frames(fi, anim_i)
    n = base_n
    if recipe.get('gesture') and layer:
        lfi, lseq = layer
        n = rig.frames(lfi, lseq['grid'][len(lseq['grid'])//2])
    anim = rig.files[fi].anims[anim_i]
    frames = []
    for k in range(n):
        pose = rig.pose(fi, anim_i, k % base_n)
        if layer:
            lfi, lseq = layer
            la = lseq['grid'][len(lseq['grid'])//2]
            ln = rig.frames(lfi, la)
            pose = rig.pose(lfi, la, int(k * ln / n), base=pose, weights=lseq['weights'])
        frames.append(pose)
    note = f"{seq['label']} ({seq['activity']}, anim {anim['name']})" + (f" + layer {layer[1]['label']}" if layer else '')
    return {'fps': anim['fps'] or 30.0, 'frames': frames}, note


def _viewmodel_clip(rig, activities):
    for act in activities:
        if act.startswith('seq:'):
            found = rig.find_sequences(label=act[4:])
        else:
            found = rig.find_sequences(activity=act)
        if found:
            fi, seq = found[0]
            a = seq['grid'][0]
            n = rig.frames(fi, a)
            anim = rig.files[fi].anims[a]
            return {'fps': anim['fps'] or 30.0, 'frames': [rig.pose(fi, a, k) for k in range(n)]}, f"{seq['label']} ({act})"
    return None, None


def _mat34_mul(a, b):
    """3x4 row-major affine product a*b."""
    out = []
    for r in range(3):
        for c in range(4):
            v = sum(a[r*4+k]*b[k*4+c] for k in range(3))
            if c == 3:
                v += a[r*4+3]
            out.append(v)
    return out


def _model_entry(resolver, path, clips_spec, kind, hold='ak', skin=0):
    """Build one model: mesh, skeleton, attachments, clips. `clips_spec` is
    'character', 'viewmodel' or None (static)."""
    rig = _Rig(resolver, path)
    main = rig.main
    base = path.removesuffix('.mdl')
    vvd, vtx = resolver.read(base + '.vvd'), resolver.read(base + '.dx90.vtx')
    if vvd is None or vtx is None:
        raise BSPError(f'{path}: .vvd/.dx90.vtx missing')
    mesh = Skinned(main, vvd, vtx, exists=resolver.has_material, skin=skin)
    clips, notes, missing_roles = [], {}, []
    if clips_spec == 'character':
        for role, recipes in translate.CHARACTER_ROLES.items():
            got = None
            for recipe in recipes:
                clip, note = _clip_from_recipe(rig, recipe, hold)
                if clip:
                    got = clip; notes[role] = note; break
            if got:
                got['role'] = role; got['loop'] = role != 'death'; clips.append(got)
            else:
                missing_roles.append(role)
        # Bake real weapon stances, not one rifle pose for every item.
        for prefix, stance in (('f', 'fist'), ('m', 'melee'), ('p', 'pistol'), ('r', 'ar2')):
            gmod = bool(rig.find_sequences(activity=f'ACT_HL2MP_IDLE_{stance.upper()}'))
            tfhold = 'MELEE' if prefix in ('f', 'm') else 'SECONDARY' if prefix == 'p' else 'PRIMARY'
            tf = bool(rig.find_sequences(activity=f'ACT_MP_STAND_{tfhold}'))
            if not gmod and not tf:
                continue
            for role, recipes in translate.CHARACTER_ROLES.items():
                if role == 'death':
                    continue
                recipe = dict(recipes[0] if gmod else recipes[2])
                recipe['activity'] = recipe['activity'][:1]
                clip, note = _clip_from_recipe(rig, recipe, stance if gmod else tfhold)
                if clip:
                    clip['role'] = f'{prefix}_{role}'; clip['loop'] = True
                    clips.append(clip); notes[clip['role']] = note
            if gmod:
                recipe = {'activity': [f'ACT_HL2MP_IDLE_{stance.upper()}'],
                          'layer_activity': [f'ACT_HL2MP_GESTURE_RANGE_ATTACK_{stance.upper()}'], 'gesture': True}
                clip, note = _clip_from_recipe(rig, recipe, stance)
                if clip:
                    clip['role'] = f'{prefix}_attack'; clip['loop'] = False
                    clips.append(clip); notes[clip['role']] = note
        lacking = [r for r in translate.CHARACTER_REQUIRED if r in missing_roles]
        if lacking:
            raise BSPError(f'{path}: no animation for {", ".join(lacking)} (hold type {hold!r})')
    elif clips_spec == 'viewmodel':
        for role, acts in translate.VIEWMODEL_ROLES.items():
            clip, note = _viewmodel_clip(rig, acts)
            if clip:
                clip['role'] = role; clip['loop'] = role == 'idle'; clips.append(clip); notes[role] = note
            else:
                missing_roles.append(role)
        lacking = [r for r in translate.VIEWMODEL_REQUIRED if r in missing_roles]
        if lacking:
            raise BSPError(f'{path}: no viewmodel animation for {", ".join(lacking)}')
    attachments = [(a['name'], a['bone'], a['local']) for a in main.attachments if 0 <= a['bone'] < len(main.bones)]
    synth = []
    for grip in translate.SYNTH_GRIPS:
        on = main.bone_index.get(grip['on'].lower())
        if grip['name'].lower() not in main.bone_index and on is not None and \
                not any(n.lower() == grip['name'].lower() for n, _, _ in attachments):
            attachments.append((grip['name'], on, grip['local'])); synth.append(grip['name'])
    if synth:
        notes['synthesized_attachments'] = synth
    return {'path': path, 'kind': kind, 'studio': main, 'mesh': mesh, 'clips': clips, 'notes': notes,
            'missing_roles': missing_roles, 'attachments': attachments,
            'includes': [f.name for f in rig.files[1:]]}


def _name(text, n):
    raw = text.encode('ascii', 'replace')[:n-1]
    return raw + b'\0'*(n-len(raw))


def _write_empty_model(f):
    """A model with nothing to see: one zero-area triangle, a 1x1 clear
    texture, one bone. A weapon with no world model (fists) carries this
    in its first slot."""
    f.write(struct.pack('<8I', 3, 3, 1, 1, 1, 0, 0, 0))
    f.write(struct.pack('<8f4B3f', 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1.0, 0.0, 0.0) * 3)
    f.write(struct.pack('<3I', 0, 1, 2))
    f.write(struct.pack('<4I', 0, 3, 0, 0))
    f.write(struct.pack('<3I', 1, 1, 4) + bytes(4))
    f.write(struct.pack('<64si12f3f4f', _name('root', 64), -1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                        0, 0, 0, 0, 0, 0, 1))
    return {'path': None, 'kind': 'world', 'vertices': 3, 'triangles': 1, 'bones': ['root'], 'attachments': [],
            'clips': [], 'missing_roles': [], 'includes': [], 'materials': [], 'alpha_materials': [],
            'placeholder_materials': [], 'textures_downsampled': {}, 'texture_bytes': 4, 'empty': True}


def _write_model(f, entry, resolver, budget):
    main, mesh = entry['studio'], entry['mesh']
    mats = sorted(mesh.groups)
    textures, placeholders, alpha, outlines = {}, [], set(), set()
    for m in mats:
        decoded, params = resolver.material(m)
        if translate.material_outline(m, params or {}, decoded):
            outlines.add(m)                  # see translate.material_outline: not drawn
        textures[m] = decoded if decoded else translate.placeholder(m, params)
        if translate.material_alpha(params or {}):
            alpha.add(m)                     # hair cards, lace: see-through where the texture is
        if not decoded:
            placeholders.append(m)
    downsampled = fit_textures(textures, budget)
    verts, remap, indices, groups = [], {}, [], []
    for ti, m in enumerate(mats):
        first = len(indices)
        tris = mesh.groups[m] if m not in outlines else []
        for t in range(0, len(tris) - len(tris) % 3, 3):
            for pos, nrm, uv, bones in tris[t:t+3]:
                b = [bi for bi, _ in bones] + [0, 0, 0]
                w = [wi for _, wi in bones] + [0.0, 0.0, 0.0]
                s = sum(w[:3]) or 1.0
                key = struct.pack('<8f4B3f', *(p*SCALE for p in pos), *nrm, *uv, b[0], b[1], b[2], 0,
                                  w[0]/s, w[1]/s, w[2]/s)
                j = remap.get(key)
                if j is None:
                    j = remap[key] = len(verts); verts.append(key)
                indices.append(j)
        if len(indices) > first:
            groups.append((first, len(indices)-first, ti, 2 if m in alpha else 0))   # bit 1: alpha
    bones = main.bones
    f.write(struct.pack('<8I', len(verts), len(indices), len(groups), len(mats), len(bones),
                        len(entry['attachments']), len(entry['clips']), 0))
    f.write(b''.join(verts))
    f.write(struct.pack(f'<{len(indices)}I', *indices))
    for g in groups:
        f.write(struct.pack('<4I', *g))
    for m in mats:
        w, h, px = textures[m]
        f.write(struct.pack('<3I', w, h, len(px))); f.write(px)
    for b in bones:
        p2b = list(b['pose_to_bone'])
        for r in range(3):
            p2b[r*4+3] *= SCALE
        f.write(struct.pack('<64si12f3f4f', _name(b['name'], 64), b['parent'], *p2b, *(x*SCALE for x in b['pos']), *b['quat']))
    for an, bone, local in entry['attachments']:
        loc = list(local)
        for r in range(3):
            loc[r*4+3] *= SCALE
        f.write(struct.pack('<64si12f', _name(an, 64), bone, *loc))
    for c in entry['clips']:
        f.write(struct.pack('<16sfII', _name(c['role'], 16), c['fps'], len(c['frames']), 1 if c['loop'] else 0))
        f.write(b''.join(struct.pack('<4f3f', *q, *(x*SCALE for x in pos)) for frame in c['frames'] for pos, q in frame))
    return {'path': entry['path'], 'kind': entry['kind'], 'vertices': len(verts), 'triangles': len(indices)//3,
            'bones': [b['name'] for b in bones], 'attachments': [a[0] for a in entry['attachments']],
            'clips': [{'role': c['role'], 'fps': c['fps'], 'frames': len(c['frames']), 'loop': c['loop'],
                       'source': entry['notes'].get(c['role'])} for c in entry['clips']],
            'missing_roles': entry['missing_roles'], 'includes': entry['includes'],
            'materials': mats, 'alpha_materials': sorted(alpha), 'placeholder_materials': placeholders, 'textures_downsampled': downsampled,
            'outline_materials_dropped': sorted(outlines),
            'texture_bytes': sum(len(t[2]) for t in textures.values())}


def decode_wav(data):
    """(rate, channels, int16 samples) from an uncompressed WAV."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise BSPError(f'unsupported WAV: {e}') from e
    if width == 1:
        pcm = array.array('h', ((b - 128) << 8 for b in raw))
    elif width == 2:
        pcm = array.array('h', raw)
    else:
        raise BSPError(f'unsupported WAV sample width {width}')
    return rate, ch, pcm


def build(output, kind, name, models, resolver, extra=None, budget=CHARACTER_TEXTURE_BUDGET, sounds=()):
    """Write an OALASSET. `models` are _model_entry dicts; `sounds` are
    (role, rate, channels, int16 array)."""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    infos = [_write_empty_model(buf) if m is None else _write_model(buf, m, resolver, budget) for m in models]
    for role, rate, ch, pcm in sounds:
        buf.write(struct.pack('<16sIII', _name(role, 16), rate, ch, len(pcm)//ch)); buf.write(pcm.tobytes())
    manifest = {'sounds': [{'role': r, 'rate': rate, 'channels': ch, 'seconds': round(len(pcm)/ch/rate, 3)}
                           for r, rate, ch, pcm in sounds],'asset_version': VERSION, 'kind': kind, 'name': name, 'coordinate_transform': TRANSFORM,
                'models': infos, 'missing_dependencies': sorted(set(resolver.missing)),
                'warnings': resolver.warnings, 'search_path': resolver.search_path(),
                'source_provenance': 'user supplied; redistribution rights not inferred', **(extra or {})}
    mb = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    with out.open('wb') as f:
        f.write(struct.pack(HEADER, MAGIC, VERSION, len(mb), len(models), 0))
        f.write(mb)
        f.write(buf.getvalue())
    manifest['package_bytes'] = out.stat().st_size
    manifest['package_sha256'] = hashlib.sha256(out.read_bytes()).hexdigest()
    return manifest


BODY_STATS = {'health': 'body_health', 'shield': 'body_shield', 'damage': 'body_damage',
              'speed': 'body_speed', 'fly': 'can_fly', 'fly_speed': 'fly_speed', 'fly_damage': 'fly_damage',
              'ability': 'ability_name', 'ability_base': 'ability_base', 'ability_damage': 'ability_damage',
              'ability_cooldown': 'ability_cooldown', 'ability_beam': 'ability_beam',
              **{k: k for k in ('ability_duration', 'ability_interval', 'ability_radius', 'ability_force', 'ability_cone', 'ability_color')},
              'group': 'hero_group', 'unique': 'unique_limit'}
TEXT_STATS = ('ability', 'ability_base', 'group')
BOOL_STATS = ('fly', 'ability_beam')


def build_character(model_path, output, roots=(), vpks=(), hold='ak', name=None, skin=0,
                    display=None, loadout=None, stats=None):
    """A character. `display` is its name in menus; `loadout` its default
    class, [primary, secondary], by the weapon names the game shows (an
    imported weapon's display_name, or a Halo weapon's own, e.g. "pistol")."""
    resolver = Resolver(None, roots, vpks)
    entry = _model_entry(resolver, model_path.replace('\\', '/').lower(), 'character', 'body', hold, skin)
    name = name or re.sub('[^a-z0-9_-]+', '_', Path(model_path).stem.lower())
    extra = {'hold_type': hold, 'hand_points': list(translate.HAND_POINTS)}
    if display:
        extra['display_name'] = display
    for k, v in (stats or {}).items():
        if k not in BODY_STATS:
            raise BSPError(f'unknown character stat {k!r} (known: {", ".join(BODY_STATS)})')
        extra[BODY_STATS[k]] = str(v) if k in TEXT_STATS else bool(float(v)) if k in BOOL_STATS else float(v)
    if loadout:
        if len(loadout) != 2 or not all(isinstance(w, str) and w for w in loadout):
            raise BSPError('a loadout is two weapon names')
        extra['loadout'] = list(loadout)
    return build(output, 'character', name, [entry], resolver, extra)


def add_world_grip(entry, grip):
    """A definition's `world_grip`: an attachment (default name
    ValveBiped.weapon_bone) on bone `on` (default the root) at `local`, a
    3x4 row-major transform in that bone's space."""
    bone = entry['studio'].bone_index.get(str(grip.get('on', '')).lower(), 0)
    local = tuple(float(x) for x in grip.get('local', (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0)))
    if len(local) != 12:
        raise BSPError('world_grip.local must be 12 numbers (3x4 row-major)')
    name = grip.get('name', 'ValveBiped.weapon_bone')
    entry['attachments'].append((name, bone, local))
    entry['notes']['synthesized_attachments'] = [name]


def build_weapon(definition, output, roots=(), vpks=()):
    """A weapon from a JSON definition: its world and view models and the
    numbers it plays by (see assetlab/data/weapons/)."""
    d = json.loads(Path(definition).read_text()) if not isinstance(definition, dict) else definition
    for key in ('name', 'base', 'world_model', 'view_model'):
        if key not in d:
            raise BSPError(f'weapon definition lacks {key!r}')
    resolver = Resolver(None, roots, vpks)
    resolver.aliases = {k.lower().removesuffix('.vmt'): v.lower().removesuffix('.vmt')
                        for k, v in d.get('material_overrides', {}).items()}
    # "none": nothing in the hand (fists); an empty model keeps the slot.
    world = None if str(d['world_model']).lower() == 'none' else _model_entry(resolver, d['world_model'].lower(), None, 'world')
    # A world model with no weapon bone (a pickup nobody was animated
    # holding, like HL2's .357) takes one from its definition: an
    # attachment the body's weapon bone can merge with.
    if d.get('world_grip') and world is not None:
        add_world_grip(world, d['world_grip'])
    models = [world,
              _model_entry(resolver, d['view_model'].lower(), 'viewmodel', 'view')]
    extra = {k: v for k, v in d.items() if k not in ('world_model', 'view_model', 'sounds')}
    extra['sound_sources'] = d.get('sounds', {})
    sounds = []
    for role, path in sorted(d.get('sounds', {}).items()):
        data = resolver.read(path)
        if data is None:
            resolver.missing.append(path)
            continue
        try:
            sounds.append((role, *decode_wav(data)))
        except BSPError as e:
            resolver.warnings.append(f'{path}: {e}')
    return build(output, 'weapon', d['name'], models, resolver, extra, sounds=sounds)


def build_sounds(definition, output, roots=(), vpks=()):
    """A sound pack (kind "sounds"): no models, only sounds by role -- the
    hit and kill dings. See assetlab/data/sounds/."""
    d = json.loads(Path(definition).read_text()) if not isinstance(definition, dict) else definition
    if 'name' not in d or not d.get('sounds'):
        raise BSPError('sound pack definition needs a name and sounds')
    resolver = Resolver(None, roots, vpks)
    sounds = []
    for role, path in sorted(d['sounds'].items()):
        data = resolver.read(path)
        if data is None:
            resolver.missing.append(path)
            continue
        sounds.append((role, *decode_wav(data)))
    if not sounds:
        raise BSPError('no sound in the pack could be read')
    extra = {k: v for k, v in d.items() if k != 'sounds'}
    extra['sound_sources'] = d['sounds']
    return build(output, 'sounds', d['name'], [], resolver, extra, sounds=sounds)
