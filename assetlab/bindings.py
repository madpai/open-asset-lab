"""Event bindings (MegaMod X7): simple world behaviour as data.

    EVENT        something happened to a source entity   (button `used`)
    CONDITIONS   read-only engine predicates, all must hold (power `relay_state` is `active`)
    ACTIONS      requests of existing engine capabilities, in order (door `toggle`)

A world lists bindings in its world_entities (schema 6); a prefab lists its
own (prefab schema 2), naming its children by local ID, and every instance
gets its own copy bound to its own children. MegaMod resolves every
reference once, at load, and dispatches through the same bounded queue as
X1 links and Lua's world.send; damage goes through the game's damage
pipeline, play_sound through the X5 world sounds.

    EventBinding('toggle_door', 'button', 'used',
                 [Condition('relay_state', 'power', 'active')],
                 [Action('toggle', target='door')])

Nothing here is a second vocabulary: events, their source kinds, conditions
and their values, actions with their targets and argument schemas, and the
limits all come from MegaMod's contract (data/megamod_resources.json,
"bindings"), and every message is the engine's (src/asset/world_def.c
hta_wbind_parse_text, hta_wbind_check_one; prefab.c; package.c).

One check is Open Asset Lab's own: a cycle of bindings with no condition
(A activates B activates A) is refused -- the engine would load it and stop
it at its chain limit, every time. A cycle with a condition may be a
deliberate design and is allowed; the engine bounds it at run time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import resources as res

B = res.CONTRACT['bindings']
EVENTS = {e['name']: e for e in B['events']}
EVENT_NAMES = tuple(e['name'] for e in B['events'])
CONDITIONS = {c['name']: c for c in B['conditions']}
ACTIONS = {a['name']: a for a in B['actions']}
LIMITS = B['limits']
AFFORDANCES = B['affordances']      # per kind: the actions it affords, events it reports, state readable


def affords(kind, action):
    """Does an entity kind afford `action` (the engine's hta_wdef_affords)."""
    return action in AFFORDANCES.get(kind, {}).get('actions', ())
ARGS = ('target', 'amount', 'sound', 'at')          # the engine's HTA_WARG order
POSITIONED = ('interactable', 'mover', 'trigger', 'teleport', 'prop')
KIND_ORDER = ('interactable', 'relay', 'mover', 'trigger', 'teleport', 'prop')
WORLD_SCHEMA = B['schema']                            # world_entities schema 6
PREFAB_SCHEMA = res.CONTRACT['prefabs']['bindings']['schema']   # prefab schema 2
PLIMITS = res.CONTRACT['prefabs']['bindings']['limits']

# Reference fields (resource.h).
SOURCE = 'world_entities.bindings[].source'
CONDITION_ENTITY = 'world_entities.bindings[].conditions[].entity'
TARGET = 'world_entities.bindings[].actions[].target'
AT = 'world_entities.bindings[].actions[].at'
SOUND = 'world_entities.bindings[].actions[].sound'
PREFAB_SOUND = 'prefabs.prefabs[].bindings[].actions[].sound'


class BindingError(ValueError):
    pass


def _a(noun):
    return ('an ' if noun[0] in 'aeiou' else 'a ') + noun


def _kinds(names):
    return ' or '.join(k for k in KIND_ORDER if k in names)


# ---- the authoring model -------------------------------------------------------------

@dataclass
class Condition:
    condition: str              # mover_state, relay_state
    entity: str                 # placed ID (world) or local child ID (prefab)
    is_: str                    # closed/opening/open/closing, inactive/active

    def record(self):
        return {'condition': self.condition, 'entity': self.entity, 'is': self.is_}


@dataclass
class Action:
    action: str                 # open close toggle activate deactivate teleport damage play_sound
    target: str = None          # open .. teleport: the entity told
    amount: float = None        # damage
    sound: str = None           # play_sound: a sound resource
    at: str = None              # play_sound: where (default the source)

    def record(self):
        r = {'action': self.action}
        if self.amount is not None:
            r['amount'] = float(self.amount)
        for k in ('at', 'sound', 'target'):
            v = getattr(self, k)
            if v is not None:
                r[k] = v
        return r


@dataclass
class EventBinding:
    """source.event -> if every condition holds -> actions, in order."""
    id: str                     # local ID, unique in its world or prefab
    source: str
    event: str
    conditions: list = field(default_factory=list)
    actions: list = field(default_factory=list)

    def record(self):
        return {'actions': [a.record() for a in self.actions], 'conditions': [c.record() for c in self.conditions],
                'event': self.event, 'id': self.id, 'source': self.source}


def records(bindings):
    """Canonical: by ID (byte order)."""
    return [b.record() for b in sorted(bindings, key=lambda b: res._bytes(b.id))]


# ---- reading one binding (hta_wbind_parse_text) -----------------------------------------

def _num_ok(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= 1e6


def _str_ok(v):
    return isinstance(v, str) and len(res._bytes(v)) <= res.LIMITS['total']


def parse_text(obj, pre):
    """A binding record as written: names checked against the vocabulary,
    each action's arguments against its schema. References stay text.
    Returns a dict; raises BindingError with the engine's words."""
    from .prefabs import local_id_error
    idv = obj.get('id') if isinstance(obj, dict) else None
    who = f'{pre} {idv}' if isinstance(idv, str) and 0 < len(res._bytes(idv)) <= 23 else f'{pre} ?'
    if not isinstance(obj, dict):
        raise BindingError(f'{who}: not an object')
    out = {'id': None, 'event': None, 'source': None, 'conditions': [], 'actions': []}
    for key, v in obj.items():
        if key == 'actions':
            if not isinstance(v, list):
                raise BindingError(f'{who}: actions is not a list')
            for a in v:
                out['actions'].append(_action(a, who, len(out['actions'])))
        elif key == 'conditions':
            if not isinstance(v, list):
                raise BindingError(f'{who}: conditions is not a list')
            for c in v:
                out['conditions'].append(_condition(c, who, len(out['conditions'])))
        elif key == 'event':
            if not isinstance(v, str) or len(v) > 63:
                raise BindingError(f'{who}: malformed event')
            if v not in EVENTS:
                raise BindingError(f"{who}: unknown event '{v}' (a binding listens to {', '.join(EVENT_NAMES)})")
            out['event'] = v
        elif key == 'id':
            if not isinstance(v, str) or len(res._bytes(v)) > 63:
                raise BindingError(f'{who}: malformed id')
            why = local_id_error(v, 'binding id')
            if why:
                raise BindingError(f"{pre} '{v}': {why}")
            out['id'] = v
        elif key == 'source':
            if not _str_ok(v):
                raise BindingError(f'{who}: malformed source')
            out['source'] = v
        else:
            raise BindingError(f"{who}: unknown field '{key}' (a binding has actions, conditions, event, id, source)")
    if not all(k in obj for k in ('actions', 'conditions', 'event', 'id', 'source')):
        raise BindingError(f'{who}: a binding needs actions, conditions, event, id and source')
    if not out['actions']:
        raise BindingError(f'{who}: has no actions')
    return out


def _condition(c, who, i):
    if i >= LIMITS['conditions_per_binding']:
        raise BindingError(f"{who}: more than {LIMITS['conditions_per_binding']} conditions")
    if not isinstance(c, dict):
        raise BindingError(f'{who}: condition {i} is not an object')
    out = {}
    for k, v in c.items():
        if not _str_ok(v):
            raise BindingError(f'{who}: condition {i}: malformed field')
        if k == 'condition':
            if v not in CONDITIONS:
                raise BindingError(f"{who}: unknown condition '{v}' ({', '.join(CONDITIONS)})")
            out['condition'] = v
        elif k == 'entity':
            out['entity'] = v
        elif k == 'is':
            out['is'] = v
        else:
            raise BindingError(f"{who}: condition {i}: unknown field '{k}' (a condition has condition, entity, is)")
    if len(out) != 3:
        raise BindingError(f'{who}: condition {i}: a condition needs condition, entity and is')
    ci = CONDITIONS[out['condition']]
    if out['is'] not in ci['values']:
        raise BindingError(f"{who}: condition {ci['name']}: unknown value '{out['is']}' ({', '.join(ci['values'])})")
    return out


def _action(a, who, i):
    if i >= LIMITS['actions_per_binding']:
        raise BindingError(f"{who}: more than {LIMITS['actions_per_binding']} actions")
    if not isinstance(a, dict):
        raise BindingError(f'{who}: action {i} is not an object')
    out = {}
    for k, v in a.items():
        if k == 'action':
            if not _str_ok(v):
                raise BindingError(f"{who}: action {i}: malformed '{k}'")
            if v not in ACTIONS:
                raise BindingError(f"{who}: unknown action '{v}' ({', '.join(ACTIONS)})")
            out['action'] = v
        elif k == 'amount':
            if not _num_ok(v):
                raise BindingError(f"{who}: action {i}: malformed '{k}'")
            out['amount'] = v
        elif k in ('target', 'sound', 'at'):
            if not _str_ok(v):
                raise BindingError(f"{who}: action {i}: malformed '{k}'")
            out[k] = v
        else:
            raise BindingError(f"{who}: action {i}: unknown field '{k}' (an action has action, amount, at, sound, target)")
    if 'action' not in out:
        raise BindingError(f'{who}: action {i} has no action')
    ai = ACTIONS[out['action']]
    for arg in ARGS:
        if arg in out and arg not in ai['takes']:
            raise BindingError(f"{who}: action {ai['name']} does not take '{arg}'")
        if arg not in out and arg in ai['needs']:
            raise BindingError(f"{who}: action {ai['name']} needs '{arg}'")
    if out['action'] == 'damage' and not 0 < out['amount'] <= _max_damage():
        raise BindingError(f'{who}: action damage: amount must be in (0, {_max_damage():g}]')
    return out


def _max_damage():
    return float(LIMITS['damage_max'])


# ---- one binding's rules against kinds (hta_wbind_check_one) ------------------------------

def check_one(who, b, kind_of, name_of):
    """`b` a parse_text dict whose entity references are keys `kind_of`
    knows (placed IDs, or local child IDs); `name_of` how a message names
    one. Raises BindingError with the engine's words."""
    ev = EVENTS[b['event']]
    sk = kind_of(b['source'])
    if sk not in ev['sources']:
        raise BindingError(f"{who}: event '{ev['name']}' is not supported by {sk} entity {name_of(b['source'])} "
                           f"({_kinds(ev['sources'])} emits it)")
    for c in b['conditions']:
        ci = CONDITIONS[c['condition']]
        k = kind_of(c['entity'])
        if k not in ci['entity']:
            ks = _kinds(ci['entity'])
            raise BindingError(f"{who}: condition {ci['name']} reads {name_of(c['entity'])}, {_a(k)} "
                               f"({ci['name']} applies to {_a(ks)})")
    for a in b['actions']:
        ai = ACTIONS[a['action']]
        if ai['targets']:
            k = kind_of(a['target'])
            if k not in ai['targets']:
                ks = _kinds(ai['targets'])
                raise BindingError(f"{who}: action {ai['name']} targets {name_of(a['target'])}, {_a(k)}, which does not "
                                   f"afford {ai['name']} ({ai['name']} needs {_a(ks)})")
        if a['action'] == 'play_sound':
            at = a.get('at', b['source'])
            k = kind_of(at)
            if k not in POSITIONED:
                raise BindingError(f"{who}: action play_sound at {name_of(at)}: {_a(k)} has no position (name one with 'at')")
        if ai['subject'] == "the event's actor" and ev['actor'] == 'never':
            raise BindingError(f"{who}: action {ai['name']} acts on the event's actor, and '{ev['name']}' never carries one")


def entity_refs(b):
    """Every entity reference of a binding, in the engine's resolution
    order: source, conditions, then per action its target and at."""
    out = [(SOURCE, b['source'])] + [(CONDITION_ENTITY, c['entity']) for c in b['conditions']]
    for a in b['actions']:
        if 'target' in a:
            out.append((TARGET, a['target']))
        if 'at' in a:
            out.append((AT, a['at']))
    return out


# ---- a world's own bindings --------------------------------------------------------------

def world_errors(recs, rs, kind_of, schema):
    """The engine's refusals of world_entities.bindings (records as written):
    parse, order, then every reference resolved through `rs` (typed, the
    world's own entities and prefab children, imported sounds) and the
    rules. `kind_of(placed id)` gives an entity's kind. Returns (parsed,
    errors)."""
    errs, parsed = [], []
    if recs and schema < WORLD_SCHEMA:
        return [], [f'world_entities: bindings need schema {WORLD_SCHEMA}']
    if len(recs) > LIMITS['bindings']:
        return [], [f"world_entities: more than {LIMITS['bindings']} bindings"]
    nc = na = 0
    for r in recs:
        try:
            b = parse_text(r, 'binding')
        except BindingError as e:
            errs.append(str(e))
            continue
        nc += len(b['conditions'])
        na += len(b['actions'])
        if nc > LIMITS['conditions'] or na > LIMITS['actions']:
            errs.append(f"binding {b['id']}: the world's bindings exceed {LIMITS['conditions']} conditions or "
                        f"{LIMITS['actions']} actions")
            break
        if parsed:
            x, y = res._bytes(parsed[-1]['id']), res._bytes(b['id'])
            if x == y:
                errs.append(f"binding {b['id']} appears twice")
                continue
            if x > y:
                errs.append(f"world_entities: bindings are not in canonical (byte) order of id at {b['id']}")
                continue
        parsed.append(b)
    if errs:
        return parsed, errs
    for b in parsed:
        who = f"binding {b['id']}"
        try:
            for f, ref in entity_refs(b):
                rs.resolve(f, who, ref)
            for a in b['actions']:
                if 'sound' in a:
                    rs.resolve(SOUND, who, a['sound'])
            check_one(who, b, kind_of, lambda x: x)
        except (res.ResourceError, BindingError) as e:
            errs.append(str(e))
    return parsed, errs


# ---- a prefab's bindings (prefab.c parse_bindings, link_bindings) -------------------------------

def prefab_parse(pid, recs):
    """A prefab's "bindings" as written: parsed, counted, canonical order.
    References stay local IDs until the children are known."""
    out, nc, na = [], 0, 0
    for r in recs:
        if len(out) >= PLIMITS['bindings']:
            raise BindingError(f"prefab {pid} has more than {PLIMITS['bindings']} bindings")
        b = parse_text(r, f'prefab {pid} binding')
        nc += len(b['conditions'])
        na += len(b['actions'])
        if nc > PLIMITS['conditions'] or na > PLIMITS['actions']:
            raise BindingError(f"prefab {pid}: its bindings exceed {PLIMITS['conditions']} conditions or "
                               f"{PLIMITS['actions']} actions")
        if out:
            x, y = res._bytes(out[-1]['id']), res._bytes(b['id'])
            if x == y:
                raise BindingError(f"prefab {pid} contains duplicate binding id '{b['id']}'")
            if x > y:
                raise BindingError(f"prefab {pid}: bindings are not in canonical (byte) order of id at '{b['id']}'")
        out.append(b)
    return out


def prefab_link(p):
    """A prefab's bindings against its children: each local reference names
    a child; then the rules (the engine's words: children as 'door')."""
    kinds = {c['id']: c['kind'] for c in p['children']}
    for b in p.get('bindings', []):
        who = f"prefab {p['id']} binding {b['id']}"
        for _, ref in entity_refs(b):
            if ref not in kinds:
                raise BindingError(f"{who} references missing child '{ref}'")
        check_one(who, b, kinds.get, lambda x: f"'{x}'")


def expand(namespace, inst, prefab):
    """Instance `inst`'s copies of the prefab's bindings: each local child
    becomes that instance's own placed entity (engine: expand_prefabs)."""
    from .prefabs import child_entity_id
    ent = lambda x: child_entity_id(namespace, inst['id'], x)
    out = []
    for b in prefab.get('bindings', []):
        e = {'id': b['id'], 'instance': inst['id'], 'prefab': prefab['id'], 'event': b['event'], 'source': ent(b['source']),
             'conditions': [dict(c, entity=ent(c['entity'])) for c in b['conditions']], 'actions': []}
        for a in b['actions']:
            a2 = dict(a)
            for k in ('target', 'at'):
                if k in a2:
                    a2[k] = ent(a2[k])
            e['actions'].append(a2)
        out.append(e)
    return out


# ---- Open Asset Lab's own static check: cycles no condition can break -----------------------------

def cycle_errors(bindings, kind_of):
    """Bindings (parsed dicts with placed IDs, the world's and every
    instance's) that form a cycle through zero-delay relay events with no
    condition anywhere on it. A mover's opened/closed comes a step later,
    so a door that reopens itself is an oscillator, not a runaway: those
    edges are not followed."""
    edges = {}
    for b in bindings:
        if b['conditions']:
            continue
        node = (b['source'], b['event'])
        for a in b['actions']:
            if a['action'] in ('activate', 'deactivate') and kind_of(a.get('target')) == 'relay':
                nxt = (a['target'], 'activated' if a['action'] == 'activate' else 'deactivated')
                edges.setdefault(node, []).append((nxt, b))
    errs, state = [], {}

    def visit(n, path):
        state[n] = 1
        for m, b in edges.get(n, []):
            if state.get(m) == 1:
                i = next(k for k, (x, _) in enumerate(path) if x == m) if any(x == m for x, _ in path) else 0
                loop = [bb['id'] for _, bb in path[i + 1:]] + [b['id']]
                errs.append('binding cycle with no condition: ' + ' -> '.join(loop) + f" -> {loop[0]} (it would run "
                            f"until the engine's chain limit of {LIMITS['chain_depth']} stops it, every time)")
            elif m not in state:
                visit(m, path + [(m, b)])
        state[n] = 2

    for n in list(edges):
        if n not in state:
            visit(n, [(n, None)])
    return errs[:1]
