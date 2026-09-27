"""Prefabs (MegaMod X6): reusable compositions of existing resources and
world-entity kinds, provided by a LIBRARY package and placed by worlds as
INSTANCES that expand, when the world loads, into ordinary placed entities.

A prefab is an authoring and world-construction abstraction, not a second
runtime: MegaMod expands every instance once, at load, into the same
entities a world could have placed by hand (buttons, relays, movers,
triggers, teleports, props), and plays those. Open Asset Lab builds,
validates, packages and inspects them:

  Prefab            x6:prefab/security_door    a resource a library provides
  PrefabChild       'door'                     a local child: one entity kind, its
                                               parameters in prefab space
  PrefabLink        used -> door.toggle        between siblings, by local ID
  PrefabInstance    'north_door'               a placement in a world: an instance
                                               ID, the prefab, a transform

Identity. The prefab is a RESOURCE (namespace:prefab/name). An instance is a
PLACEMENT, named by a LOCAL ID in its world; so is a child in its prefab. A
local ID is [a-z][a-z0-9]*(_[a-z0-9]+)* (no "__", no trailing "_"), at most
23 bytes. Child `button` of instance `north_door` becomes the placed entity

    <world namespace>:entity/north_door__button

-- an ordinary entity ID, unique by construction (neither half may hold
"__"; a schema 5 world's own entities may not either).

References. A child's model, sound and script are typed resource references
resolved from the PROVIDER's point of view: its own resources and what it
imports. A world that places the prefab imports the prefab, nothing else;
it does not gain the prefab's implementation dependencies (the package set
still loads them, and their digests are in the world key).

Transforms. position (wu), yaw_degrees (about +z, counter-clockwise seen
from above), and, on an instance, a uniform scale. A child's world
transform is instance x child: pos = I.pos + I.scale * Rz(I.yaw) * c.pos,
yaw = I.yaw + c.yaw, scale = I.scale.

No nesting (schema 1), no inheritance, no per-instance overrides.

MegaMod is the authority: the rules and limits come from its contract
(data/megamod_resources.json, "prefabs"), local IDs are checked against its
own verdicts (data/megamod_id_conformance.json, "local_ids"), and every
message here is the engine's (src/asset/prefab.c, world_def.c).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import resources as res

P = res.CONTRACT['prefabs']
SCHEMA = P['schema']
LIMITS = P['limits']
LOCAL = P['local_id']
CHILD = P['children']
KINDS = tuple(CHILD['kinds'])
SEP = P['child_entity']['separator']
EVENTS = ('used', 'fired', 'entered')
INPUTS = ('activate', 'open', 'close', 'toggle', 'teleport')
EMITS = {'interactable': ('used',), 'relay': ('fired',), 'trigger': ('entered',)}
ACCEPTS = {'relay': ('activate',), 'mover': ('open', 'close', 'toggle'), 'teleport': ('teleport',)}
# Engine numbers (world_def.h) the prefab checks share.
MAX_REACH, MAX_MOVE, MAX_SPEED, MAX_CHAIN, WORLD_LIMIT = 4.0, 64.0, 64.0, 16, 4096.0
# A child's fields, in the engine's table order (prefab.c FIELDS): which
# kind takes and needs which comes from the contract.
FIELDS = ('position', 'reach', 'script', 'size', 'move', 'speed', 'yaw_degrees', 'sound', 'model', 'bounds')
TAKES = {k: set(CHILD['fields'][k]['takes']) for k in KINDS}
NEEDS = {k: set(CHILD['fields'][k]['needs']) for k in KINDS}

# Reference fields (resource.h), by the engine's names.
CHILD_MODEL = 'prefabs.prefabs[].children[].model'
CHILD_SOUND = 'prefabs.prefabs[].children[].sound'
CHILD_SCRIPT = 'prefabs.prefabs[].children[].script'
INSTANCE_PREFAB = 'world_entities.prefab_instances[].prefab'


class PrefabError(ValueError):
    pass


def _a(noun):
    return ('an ' if noun[0] in 'aeiou' else 'a ') + noun


def local_id_error(text, what='local child id'):
    """None, or why `text` is not a local ID (the engine's words)."""
    b = res._bytes(text)
    if not b:
        return f'empty {what}'
    if b'\x00' in b:
        b = b[:b.index(b'\x00')]
        if not b:
            return f'empty {what}'
    if len(b) > LOCAL['max_bytes']:
        return f"{what} longer than {LOCAL['max_bytes']} bytes"
    for i, c in enumerate(b):
        ok = 0x61 <= c <= 0x7A or (i and (0x30 <= c <= 0x39 or c == 0x5F))
        if not ok:
            if 0x41 <= c <= 0x5A:
                return f'{what} has capital {res._shown(c)} (IDs are lowercase; nothing is folded)'
            if not i:
                return f'{what} starts with {res._shown(c)}, not a lowercase letter'
            return f'{what} has {res._shown(c)}, not [a-z0-9_]'
        if c == 0x5F and i + 1 < len(b) and b[i + 1] == 0x5F:
            return f"{what} has '__' (reserved: a child's entity is <instance>__<child>)"
    if b[-1] == 0x5F:
        return f"{what} ends with '_'"
    return None


def child_entity_id(namespace, instance, child):
    return f'{namespace}:entity/{instance}{SEP}{child}'


# ---- the authoring model ---------------------------------------------------------

@dataclass
class PrefabLink:
    event: str
    target: str                 # a sibling's local ID
    input: str


@dataclass
class PrefabChild:
    """One local child: an entity kind with its parameters in prefab space."""
    id: str                     # local ID
    kind: str                   # interactable, relay, mover, trigger, teleport, prop
    links: list = field(default_factory=list)
    position: tuple = None
    yaw_degrees: float = None   # mover, prop: its own rotation; teleport: facing
    reach: float = None         # interactable
    script: str = None          # interactable: a script resource (its on_used)
    size: tuple = None          # mover
    move: tuple = None
    speed: float = None
    sound: str = None           # mover: a sound resource
    model: str = None           # prop (needed), mover (optional: what draws it)
    bounds: tuple = None        # trigger: (min, max)

    def record(self):
        r = {'id': self.id, 'kind': self.kind,
             'links': [{'event': ln.event, 'input': ln.input, 'target': ln.target} for ln in self.links]}
        vec = lambda v: [float(x) for x in v]
        for name in ('position', 'size', 'move'):
            v = getattr(self, name)
            if v is not None:
                r[name] = vec(v)
        for name in ('reach', 'speed', 'yaw_degrees'):
            v = getattr(self, name)
            if v is not None:
                r[name] = float(v)
        for name in ('script', 'sound', 'model'):
            v = getattr(self, name)
            if v is not None:
                r[name] = v
        if self.bounds is not None:
            r['bounds'] = {'max': vec(self.bounds[1]), 'min': vec(self.bounds[0])}
        return r


@dataclass
class Prefab:
    """A prefab resource: children in any order (written canonically)."""
    id: str                     # namespace:prefab/name
    children: list = field(default_factory=list)
    provenance: dict = None     # never played (the library's "provenance" member)

    def record(self):
        return {'children': [c.record() for c in sorted(self.children, key=lambda c: res._bytes(c.id))], 'id': self.id}


@dataclass
class PrefabInstance:
    """A placement of a prefab in a world: identity and transform only."""
    id: str                     # instance ID (a local ID)
    prefab: str                 # namespace:prefab/name, imported by the world
    position: tuple = (0.0, 0.0, 0.0)
    yaw_degrees: float = 0.0
    scale: float = 1.0

    def record(self):
        r = {'id': self.id, 'position': [float(x) for x in self.position], 'prefab': self.prefab}
        if self.yaw_degrees:
            r['yaw_degrees'] = float(self.yaw_degrees)
        if self.scale != 1.0:
            r['scale'] = float(self.scale)
        return r


def member(prefabs):
    """The library's "prefabs" member (canonical: prefabs by ID)."""
    return {'prefabs': [p.record() for p in sorted(prefabs, key=lambda p: res._bytes(p.id))], 'schema': SCHEMA}


def validate(prefabs, pkg='this package'):
    """Diagnostics for prefabs before they are written: the engine's parse of
    the member it would be. [] when good."""
    try:
        parse({'prefabs': member(prefabs)}, f'package {pkg}' if pkg != 'this package' else pkg)
    except PrefabError as e:
        return [str(e)]
    return []


# ---- reading (the engine's hta_prefab_parse) ---------------------------------------

def _num(v, lim):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= lim


def _vec3(v, lim):
    return isinstance(v, list) and len(v) == 3 and all(_num(x, lim) for x in v)


def _child(p, c, i, links):
    pid = p['id']
    if len(p['children']) >= LIMITS['children']:
        raise PrefabError(f"prefab {pid} has more than {LIMITS['children']} children")
    who = f'prefab {pid} child {i}'
    if not isinstance(c, dict):
        raise PrefabError(f'{who}: not an object')
    pre = c.get('id')
    if isinstance(pre, str) and 0 < len(res._bytes(pre)) <= LOCAL['max_bytes']:
        who = f"prefab {pid} child '{pre}'"
    out = {'id': None, 'kind': None, 'links': [], 'first_link': len(links)}
    got, nested = set(), False
    have = {'id': False, 'kind': False, 'links': False}
    for key, v in c.items():
        if key == 'id':
            if not isinstance(v, str) or len(res._bytes(v)) > 63:
                raise PrefabError(f'{who}: malformed id')
            why = local_id_error(v)
            if why:
                raise PrefabError(f"prefab {pid} child '{v}': {why}")
            out['id'] = v
            who = f"prefab {pid} child '{v}'"
            have['id'] = True
        elif key == 'kind':
            if not isinstance(v, str) or len(v) > 23:
                raise PrefabError(f'{who}: malformed kind')
            have['kind'] = True
            if v == 'prefab':
                nested = True
            elif v not in KINDS:
                raise PrefabError(f"{who}: unknown kind '{v}' (a prefab child is interactable, relay, mover, trigger, "
                                  f"teleport or prop)")
            else:
                out['kind'] = v
        elif key == 'links':
            if not isinstance(v, list):
                raise PrefabError(f'{who}: malformed links')
            have['links'] = True
            for ln in v:
                if len(out['links']) >= LIMITS['links_per_child']:
                    raise PrefabError(f"{who}: more than {LIMITS['links_per_child']} links")
                if len(links) >= LIMITS['links']:
                    raise PrefabError(f"{who}: more than {LIMITS['links']} links in the prefab")
                if not isinstance(ln, dict) or not all(isinstance(x, str) and len(x) < 64 for x in ln.values()):
                    raise PrefabError(f'{who}: malformed link')
                for k2, x in ln.items():
                    if k2 == 'event' and x not in EVENTS:
                        raise PrefabError(f"{who}: unknown event '{x}'")
                    if k2 == 'input' and x not in INPUTS:
                        raise PrefabError(f"{who}: unknown input '{x}'")
                    if k2 == 'target' and len(res._bytes(x)) > LOCAL['max_bytes']:
                        raise PrefabError(f"{who} references missing child '{x}'")
                    if k2 not in ('event', 'input', 'target'):
                        raise PrefabError(f"{who}: unknown link field '{k2}'")
                if not all(k2 in ln for k2 in ('event', 'input', 'target')):
                    raise PrefabError(f'{who}: a link needs event, input and target')
                links.append(dict(ln))
                out['links'].append(dict(ln))
        elif key == 'prefab':
            nested = True
        elif key in FIELDS:
            got.add(key)
            ok = True
            if key == 'position':
                ok = _vec3(v, LIMITS['local_position'])
            elif key in ('size', 'move'):
                ok = _vec3(v, 1e6)
            elif key in ('reach', 'yaw_degrees', 'speed'):
                ok = _num(v, 1e6)
            elif key in ('script', 'sound', 'model'):
                ok = isinstance(v, str) and len(res._bytes(v)) <= res.LIMITS['total']
            elif key == 'bounds':
                ok = (isinstance(v, dict) and set(v) == {'min', 'max'} and _vec3(v['min'], LIMITS['local_position'])
                      and _vec3(v['max'], LIMITS['local_position']))
            if not ok:
                raise PrefabError(f"{who}: malformed or out-of-range '{key}'")
            out[key] = v
        else:
            raise PrefabError(f"{who}: unknown field '{key}'")
    if nested:
        raise PrefabError(f"prefab {pid} child '{out['id'] or '?'}' contains a nested prefab reference, which is not "
                          f'supported in prefab schema {SCHEMA}')
    if not have['id']:
        raise PrefabError(f'{who}: has no id')
    if not have['kind']:
        raise PrefabError(f'{who}: has no kind')
    if not have['links']:
        raise PrefabError(f'{who}: has no links (write [] for none)')
    kind = out['kind']
    for f in FIELDS:
        if f in got and f not in TAKES[kind]:
            raise PrefabError(f"{who}: {_a(kind)} does not take '{f}'")
        if f not in got and f in NEEDS[kind]:
            raise PrefabError(f"{who}: {_a(kind)} needs '{f}'")
    if 'yaw_degrees' in got and not abs(out['yaw_degrees']) <= LIMITS['yaw_degrees']:
        raise PrefabError(f"{who}: yaw_degrees out of range (|yaw| <= {LIMITS['yaw_degrees']:g})")
    if kind == 'interactable' and not 0 < out['reach'] <= MAX_REACH:
        raise PrefabError(f'{who}: reach out of range (0, {MAX_REACH:g}] wu')
    if kind == 'mover':
        if not all(0.01 <= x <= LIMITS['local_position'] for x in out['size']):
            raise PrefabError(f"{who}: mover size must be at least 0.01 wu and at most {LIMITS['local_position']:g}")
        if not 0.01 <= math.sqrt(sum(x * x for x in out['move'])) <= MAX_MOVE:
            raise PrefabError(f'{who}: mover move out of range (0.01 to {MAX_MOVE:g} wu)')
        if not 0 < out['speed'] <= MAX_SPEED:
            raise PrefabError(f'{who}: mover speed out of range (0, {MAX_SPEED:g}] wu/s')
    if kind == 'trigger' and not all(out['bounds']['max'][k] - out['bounds']['min'][k] >= 0.05 for k in range(3)):
        raise PrefabError(f'{who}: trigger bounds are empty or thinner than 0.05 wu')
    return out


def _link_children(p, links):
    kids = p['children']
    at = {c['id']: i for i, c in enumerate(kids)}
    for i, c in enumerate(kids):
        for ln in c['links']:
            t = ln['target']
            j = at.get(t)
            if j is None:
                raise PrefabError(f"prefab {p['id']} child '{c['id']}' references missing child '{t}'")
            if j == i:
                raise PrefabError(f"prefab {p['id']} child '{c['id']}' links to itself")
            if ln['event'] not in EMITS.get(c['kind'], ()):
                raise PrefabError(f"prefab {p['id']} child '{c['id']}': {_a(c['kind'])} does not emit '{ln['event']}'")
            tk = kids[j]['kind']
            if ln['input'] not in ACCEPTS.get(tk, ()):
                raise PrefabError(f"prefab {p['id']} child '{c['id']}' links to child '{t}', and {_a(tk)} does not "
                                  f"accept '{ln['input']}'")
            ln['target_index'] = j
    # Longest chain from each child; a grey child reached again is a cycle
    # (the engine's iterative walk, the same order).
    state, depth = [0] * len(kids), [0] * len(kids)
    for root in range(len(kids)):
        if state[root]:
            continue
        stack = [[root, 0]]
        state[root] = 1
        while stack:
            v, k = stack[-1]
            c = kids[v]
            if k < len(c['links']):
                stack[-1][1] += 1
                w = c['links'][k]['target_index']
                if state[w] == 1:
                    frm = next(i for i, f in enumerate(stack) if f[0] == w)
                    path = ' -> '.join(kids[f[0]]['id'] for f in stack[frm:]) + f" -> {kids[w]['id']}"
                    raise PrefabError(f"prefab {p['id']}: link cycle: {path} (links are zero-delay: a cycle would loop "
                                      f'in one tick)')
                if not state[w]:
                    state[w] = 1
                    stack.append([w, 0])
                continue
            best = max((depth[ln['target_index']] + 1 for ln in c['links']), default=0)
            depth[v] = best
            if best > MAX_CHAIN:
                raise PrefabError(f"prefab {p['id']} child '{c['id']}': a chain of {best} links starts here; at most "
                                  f'{MAX_CHAIN}')
            state[v] = 2
            stack.pop()


def _prefab(v, pkg):
    if not isinstance(v, dict):
        raise PrefabError(f'{pkg}: a prefab is not an object')
    pid = v.get('id') if isinstance(v.get('id'), str) else '?'
    for key in v:
        if key not in ('children', 'id'):
            raise PrefabError(f"{pkg}: prefab {pid}: unknown field '{key}' (a prefab has children, id)")
    p = {'id': pid, 'children': []}
    links = []
    for key, x in v.items():
        if key == 'id':
            if not isinstance(x, str) or len(res._bytes(x)) > res.LIMITS['total']:
                raise PrefabError(f'{pkg}: malformed prefab id')
            code, why, rid = res.parse_id(x)
            if code == res.OK and rid.type != 'prefab':
                raise PrefabError(f"{pkg}: prefab '{x}' is {_a(res.noun(rid.type))} ID, expected namespace:prefab/name")
            if code != res.OK:
                raise PrefabError(f"{pkg}: prefab '{x}' is not a resource ID: {why} (expected namespace:prefab/name)")
            if res.reserved_namespace(rid.namespace):
                raise PrefabError(f"{pkg}: {x}: namespace '{rid.namespace}' is reserved for built-in content")
        elif key == 'children':
            if not isinstance(x, list):
                raise PrefabError(f'{pkg}: prefab {pid}: malformed children')
            for i, c in enumerate(x):
                p['children'].append(_child(p, c, i, links))
    if 'id' not in v or 'children' not in v:
        raise PrefabError(f'{pkg}: a prefab needs children and id')
    if not p['children']:
        raise PrefabError(f'prefab {pid} has no children')
    kids = p['children']
    for i in range(1, len(kids)):
        a, b = res._bytes(kids[i - 1]['id']), res._bytes(kids[i]['id'])
        if a == b:
            raise PrefabError(f"prefab {pid} contains duplicate local child id '{kids[i]['id']}'")
        if a > b:
            raise PrefabError(f"prefab {pid}: children are not in canonical (byte) order of local id at '{kids[i]['id']}'")
    _link_children(p, links)
    return p


def parse(manifest, pkg):
    """The compiled prefabs of a library manifest (dict): a list of prefab
    dicts in canonical order; [] when it has no "prefabs" member. Raises
    PrefabError with the engine's words. References stay unresolved."""
    if 'prefabs' not in manifest:
        return []
    m = manifest['prefabs']
    if not isinstance(m, dict):
        raise PrefabError(f'{pkg}: prefabs is not an object')
    for key in m:
        if key not in ('prefabs', 'schema'):
            raise PrefabError(f"{pkg}: prefabs: unknown field '{key}' (schema {SCHEMA} has prefabs, schema)")
    out = []
    for key, v in m.items():
        if key == 'schema':
            if not _num(v, 1e300):
                raise PrefabError(f'{pkg}: malformed prefab schema')
            if v != SCHEMA:
                raise PrefabError(f'{pkg}: unsupported prefab schema {v:g} (this engine has {SCHEMA})')
        elif key == 'prefabs':
            if not isinstance(v, list):
                raise PrefabError(f'{pkg}: prefabs.prefabs is not a list')
            for x in v:
                if len(out) >= LIMITS['per_library']:
                    raise PrefabError(f"{pkg} provides more than {LIMITS['per_library']} prefabs")
                p = _prefab(x, pkg)
                if out:
                    a, b = res._bytes(out[-1]['id']), res._bytes(p['id'])
                    if a == b:
                        raise PrefabError(f"{pkg}: {p['id']} is declared twice")
                    if a > b:
                        raise PrefabError(f"{pkg}: prefabs are not in canonical (byte) order at {p['id']}")
                out.append(p)
    if 'schema' not in m or 'prefabs' not in m:
        raise PrefabError(f'{pkg}: prefabs needs prefabs and schema')
    return out


# ---- transforms ------------------------------------------------------------------

def cossin(deg):
    """cos and sin of `deg` degrees; exact at every multiple of 90 (the engine's)."""
    r = math.fmod(deg, 360.0)
    if r < 0:
        r += 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    if r in exact:
        return exact[r]
    return math.cos(math.radians(r)), math.sin(math.radians(r))


def xform_vector(scale, cs, v):
    c, s = cs
    return (scale * (c * v[0] - s * v[1]), scale * (s * v[0] + c * v[1]), scale * v[2])


def xform_point(pos, scale, cs, p):
    v = xform_vector(scale, cs, p)
    return tuple(pos[k] + v[k] for k in range(3))


def axis_aligned(deg):
    return math.isfinite(deg) and math.fmod(deg, 90.0) == 0.0


# ---- expansion (the engine's, world_def.c) -------------------------------------------

def instance_error(inst):
    """None, or why an instance's own fields are refused (the engine's words)."""
    why = local_id_error(inst.get('id'), 'instance id') if isinstance(inst.get('id'), str) else 'malformed instance id'
    if why:
        return f"prefab instance '{inst.get('id')}': {why}"
    who = f"prefab instance {inst['id']}"
    if not _vec3(inst.get('position'), WORLD_LIMIT):
        return f'{who}: position must be finite and inside the world'
    yaw = inst.get('yaw_degrees', 0.0)
    if not _num(yaw, LIMITS['yaw_degrees']):
        return f"{who}: yaw_degrees out of range (|yaw| <= {LIMITS['yaw_degrees']:g})"
    s = inst.get('scale', 1.0)
    if not (_num(s, 1e6) and P['transform']['scale']['min'] <= s <= P['transform']['scale']['max']):
        return (f"{who}: scale {s:g} out of range (uniform, "
                f"{P['transform']['scale']['min']:g} to {P['transform']['scale']['max']:g})")
    return None


def expand(namespace, inst, prefab):
    """The entities instance `inst` (a record dict) of compiled `prefab`
    becomes, in expansion order (canonical local-ID order): dicts with the
    placed ID, path, kind and world-space parameters. Raises PrefabError
    with the engine's words for what only a placement can get wrong."""
    who = f"prefab instance {inst['id']} ({prefab['id']})"
    pos = tuple(float(x) for x in inst['position'])
    yaw = float(inst.get('yaw_degrees', 0.0))
    scale = float(inst.get('scale', 1.0))
    out = []
    for c in prefab['children']:
        cid = child_entity_id(namespace, inst['id'], c['id'])
        e = {'id': cid, 'path': f"{inst['id']}/{c['id']}", 'kind': c['kind'], 'child': c['id'],
             'links': [{'event': ln['event'], 'input': ln['input'],
                        'target': child_entity_id(namespace, inst['id'], ln['target'])} for ln in c['links']]}
        cyaw = yaw + float(c.get('yaw_degrees', 0.0))
        if 'position' in c:
            e['position'] = xform_point(pos, scale, cossin(yaw), c['position'])
        if c['kind'] == 'interactable':
            e['reach'] = c['reach'] * scale
            if e['reach'] > MAX_REACH:
                raise PrefabError(f"{who} child '{c['id']}': reach {e['reach']:g} after scale {scale:g} exceeds "
                                  f'{MAX_REACH:g} wu')
            if 'script' in c:
                e['script'] = c['script']
        if c['kind'] == 'mover':
            e['size'] = tuple(x * scale for x in c['size'])
            e['move'] = xform_vector(scale, cossin(yaw), c['move'])
            e['speed'] = c['speed'] * scale
            e['yaw_degrees'] = cyaw
            if math.sqrt(sum(x * x for x in e['move'])) > MAX_MOVE or e['speed'] > MAX_SPEED:
                raise PrefabError(f"{who} child '{c['id']}': mover move or speed exceeds the world's limit after "
                                  f'scale {scale:g}')
            for k in ('sound', 'model'):
                if k in c:
                    e[k] = c[k]
        if c['kind'] == 'prop':
            e['model'] = c['model']
            e['yaw_degrees'] = cyaw
            e['scale'] = scale
        if c['kind'] == 'teleport':
            e['yaw_degrees'] = cyaw
        if c['kind'] == 'trigger':
            if not axis_aligned(yaw):
                raise PrefabError(f"{who} child '{c['id']}': a trigger is an axis-aligned box, so the instance's "
                                  f'yaw must be a multiple of 90 degrees (is {yaw:g})')
            corners = [xform_point(pos, scale, cossin(yaw), (x, y, z)) for x in (c['bounds']['min'][0], c['bounds']['max'][0])
                       for y in (c['bounds']['min'][1], c['bounds']['max'][1])
                       for z in (c['bounds']['min'][2], c['bounds']['max'][2])]
            e['bounds'] = (tuple(min(p[k] for p in corners) for k in range(3)),
                           tuple(max(p[k] for p in corners) for k in range(3)))
        out.append(e)
    return out


MAX_ENTITIES, MAX_LINKS, MAX_MOVER_DEFS = LIMITS['expanded_entities'], 256, LIMITS['expanded_mover_definitions']


def instances_errors(records):
    """The engine's parse-time refusals of a world's instance records:
    each instance's own fields, then canonical order, each once."""
    errs = []
    if len(records) > LIMITS['instances_per_world']:
        errs.append(f"world_entities: more than {LIMITS['instances_per_world']} prefab instances")
    prev = None
    for r in records:
        why = instance_error(r)
        if why:
            errs.append(why)
            continue
        if prev is not None:
            a, b = res._bytes(prev), res._bytes(r['id'])
            if a == b:
                errs.append(f"prefab instance {r['id']} appears twice")
            elif a > b:
                errs.append(f"world_entities: prefab_instances are not in canonical (byte) order of id at {r['id']}")
        prev = r['id']
    return errs


def expand_instances(records, world_id, rs, deps, authored, links=0, movers=0):
    """Every instance (record dicts, canonical order) expanded as the engine
    does it: its prefab resolved through `rs` (the world must import it),
    the limits checked before anything is added, each child added to `rs` as
    a placed entity (so world links may name it). Returns (expanded entity
    dicts in engine order, errors). `authored`, `links` and `movers` are the
    world's own counts."""
    errs, out = [], []
    ns = world_id.partition(':')[0]
    ents = authored
    for r in records:
        who = f"prefab instance {r['id']}"
        try:
            e = rs.resolve(INSTANCE_PREFAB, who, r['prefab'])
        except res.ResourceError as x:
            errs.append(str(x))
            continue
        p = next((q for q in deps[e.provider - 1].prefabs if q['id'] == r['prefab']), None) if e.provider else None
        if p is None:
            errs.append(f"{who}: prefab {r['prefab']} was not loaded")
            continue
        n = len(p['children'])
        nl = sum(len(c['links']) for c in p['children'])
        nm = sum(c['kind'] == 'mover' for c in p['children'])
        if ents + n > MAX_ENTITIES:
            errs.append(f'prefab instance {r["id"]} expands the world to {ents + n} entities, exceeding limit {MAX_ENTITIES}')
            break
        if links + nl > MAX_LINKS:
            errs.append(f'prefab instance {r["id"]} expands the world to {links + nl} links, exceeding limit {MAX_LINKS}')
            break
        if movers + nm > MAX_MOVER_DEFS:
            errs.append(f'prefab instance {r["id"]} expands the world to {movers + nm} mover definitions, exceeding limit '
                        f'{MAX_MOVER_DEFS}')
            break
        try:
            kids = expand(ns, r, p)
        except PrefabError as x:
            errs.append(str(x))
            continue
        for i, c in enumerate(kids):
            c['index'] = ents + i
            c['instance'], c['prefab'], c['provider'] = r['id'], p['id'], deps[e.provider - 1].decl.id
            if 'script' in p['children'][i]:
                c['script_provider'] = p['children'][i].get('script_provider')
            try:
                if c['id'] in rs.entries:
                    raise res.ResourceError(f"prefab instance {r['id']} ({p['id']}) child '{c['child']}' makes {c['id']}, "
                                            f'which the world already has')
                rs.add(c['id'], 'entity', 0, ents + i)
            except res.ResourceError as x:
                errs.append(str(x))
        ents += n
        links += nl
        movers += nm
        out += kids
    return out, errs
