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

Mover definitions (MegaMod X2): a mover's reusable, immutable behaviour --
the size of its box, how far and which way it slides, how fast, what it
is made of -- can be a `MoverDefinition` with its own ID
`namespace:mover/name`, and any number of placed movers name it and give
only their position. The package then carries world_entities schema 2: a
`mover_definitions` list, and movers with `definition` + `position` instead
of inline `bounds`/`move`/`speed`. The runtime resolves each reference to
the definition once, at load; each placed door keeps its own state. A world
with no definitions is written exactly as before (schema 1).

Scripts (MegaMod X3): a world may carry host-side Lua scripts
(`assetlab.scripts.Script`, `namespace:script/name`). An interactable may
name one (`script=`): when used, MegaMod calls its `on_used`, which may
request engine actions; the world may name one `ability_script` for a
player's ability press (`on_ability`). Such a world is world_entities
schema 3. Scripts are content: never executed here.

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

Asset resources (MegaMod X5): a `prop` places a MODEL resource
(`namespace:model/name`, assetlab.assets) imported from a library package
where it stands -- drawn with the model's materials, solid as its bounds --
and a mover definition may name the SOUND resource it makes when it starts
to move. Both are typed references the engine resolves once, like a
script's. Such a world is world_entities schema 4. The world never copies
the library's bytes: MegaMod loads the library beside it, by package ID.

Prefab instances (MegaMod X6): a world may place instances of PREFABS it
imports from a library (assetlab.prefabs): `PrefabInstance(id, prefab,
position, yaw_degrees, scale)`. MegaMod expands each, at load, into ordinary
placed entities named `<ns>:entity/<instance>__<child>`; world links (and
scripts) may name those like any placed ID. Such a world is world_entities
schema 5, and so is one whose props carry `yaw_degrees` or `scale`. A schema 5
world's own placed IDs may not hold "__".

Event bindings (MegaMod X7): `bindings` lists assetlab.bindings.EventBinding
records -- an event of a placed entity (or a prefab child, by its placed
ID), conditions, actions -- so simple behaviour needs no Lua: button used ->
if the power relay is active -> toggle the door. Such a world is
world_entities schema 6. Prefabs carry their own (assetlab.prefabs).

There is deliberately no text format for this yet: tests and
`assetlab fixture` build worlds in code (docs/ORIGINAL_WORLDS.md).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from . import bindings as bindlib, dependencies as deplib, ids, prefabs as prefablib, racing as racinglib, resources as res, scripts as scriptlib, worldkey, world_state
from .package import (GROUP_NO_COLLISION, build_groups, manifest_json, pack_vertices,
                      write_package)

# OALMAP v3: the v2 layout plus a manifest `world_entities` section the
# runtime must implement. A runtime that does not know v3 refuses the
# package instead of loading the world without its behaviour.
VERSION = 3
GROUP_ENTITY = 8        # a world entity's triangles; its index + 1 in bits 8..23
ENTITY_SCHEMA = 1          # inline movers (X1)
DEFINITION_SCHEMA = 2      # adds mover_definitions (X2)
SCRIPT_SCHEMA = 3          # adds scripts, an interactable's script, ability_script (X3)
ASSET_SCHEMA = 4           # adds props (a model) and a mover definition's sound (X5)
PREFAB_SCHEMA = 5          # adds prefab_instances and a prop's yaw_degrees/scale (X6)
BINDING_SCHEMA = 6         # adds bindings (X7)
VISUAL_SCHEMA = 7          # adds environment and bounded local lights (X9)
RACING_SCHEMA = 8          # adds original race route, pads and vehicle tuning (X10)
MAX_MOVER_DEFINITIONS = world_state.LIMITS['mover_definitions']

# The runtime's limits (MegaMod src/asset/world_def.h); a package that
# passes here passes there.
MAX_ENTITIES = world_state.LIMITS['runtime_objects']
MAX_LINKS_PER_ENTITY = 8
MAX_LINKS = world_state.LIMITS['links']
MAX_CHAIN = 16          # links from a root event to the last one it causes
MAX_EVENTS_PER_ROOT = 256
MAX_REACH = 4.0         # wu
MAX_MOVE = 64.0         # wu
MAX_SPEED = 64.0        # wu/s
WORLD_LIMIT = 4096.0    # |coordinate|, wu

KINDS = ('interactable', 'relay', 'mover', 'trigger', 'teleport', 'prop')
EMITS = {'interactable': ('used',), 'relay': ('fired',), 'trigger': ('entered',),
         'mover': (), 'teleport': (), 'prop': ()}
ACCEPTS = {'relay': ('activate',), 'mover': ('open', 'close', 'toggle'),
           'teleport': ('teleport',), 'interactable': (), 'trigger': (), 'prop': ()}
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
    definition: str = None      # mover: a MoverDefinition's ID (then only `position`: its box's centre)
    script: str = None          # interactable: a Script's ID (its on_used runs when used)
    model: str = None           # prop (X5): a model resource ID, imported from a library
    scale: float = None         # prop (X6, schema 5): uniform; yaw_degrees turns a prop too


@dataclass
class MoverDefinition:
    """A reusable mover. Immutable data: every placement that names it gets
    this size, travel and speed, and its own state at runtime."""
    id: str                     # namespace:mover/name
    size: tuple                 # the closed box's extent, wu
    move: tuple                 # offset when open
    speed: float                # wu/s
    material: str               # how a placement is drawn (one box of it)
    sound: str = None           # X5: a sound resource ID it makes starting to move


@dataclass
class Box:
    min: tuple
    max: tuple
    material: str
    solid: bool = True
    owner: str = None           # the placed ID of the mover this box is


@dataclass
class Quad:
    """One planar four-corner original surface, counter-clockwise from its
    visible/colliding side. Useful for ramps and banked track ribbons."""
    corners: tuple
    material: str
    solid: bool = True


@dataclass
class Triangle:
    corners: tuple              # counter-clockwise from the visible/colliding side
    material: str
    solid: bool = True


@dataclass
class Environment:
    ambient: tuple             # linear RGB illumination, 0..2
    clear: tuple               # clear/background RGB, 0..1
    fog_color: tuple           # atmospheric RGB, 0..1
    fog_density: float = 0.0   # exponential squared, per world unit
    fog_start: float = 0.0     # clear air before fog

    def record(self):
        return dict(ambient=list(self.ambient), clear=list(self.clear), fog_color=list(self.fog_color),
                    fog_density=self.fog_density, fog_start=self.fog_start)


@dataclass
class Light:
    id: str                    # local ID in the world
    type: str                  # point | spot
    position: tuple
    color: tuple               # linear RGB, 0..1
    intensity: float
    range: float
    relay: str = None          # placed relay ID, including a prefab child
    direction: tuple = None   # spot: unit vector, world axes
    inner_degrees: float = None
    outer_degrees: float = None

    def record(self):
        r = dict(id=self.id, type=self.type, position=list(self.position), color=list(self.color),
                 intensity=self.intensity, range=self.range)
        if self.relay is not None:
            r['relay'] = self.relay
        if self.type == 'spot':
            r.update(direction=list(self.direction), inner=math.cos(math.radians(self.inner_degrees)),
                     outer=math.cos(math.radians(self.outer_degrees)))
        return r


@dataclass
class OriginalWorld:
    id: str                      # namespace:world/name
    file_name: str               # the runtime looks packages up by this (maps/<name>.oalmap)
    display_name: str
    materials: dict              # name -> (r, g, b) 0..255
    boxes: list
    spawns: list                 # {'position', 'yaw_degrees', 'team'}
    entities: list
    mover_definitions: list = field(default_factory=list)
    scripts: list = field(default_factory=list)       # assetlab.scripts.Script
    ability_script: str = None                        # a Script's ID with on_ability (its own or imported)
    # X4: a package ID makes the world declare itself ("package" member):
    # what it provides (derived: its world, mover definitions, own scripts)
    # and what it requires -- resources.Requirement(package, [imported IDs]).
    # A world without one is written exactly as before (an implicit package).
    package: str = None
    requires: list = field(default_factory=list)
    prefab_instances: list = field(default_factory=list)   # X6: prefabs.PrefabInstance
    bindings: list = field(default_factory=list)           # X7: bindings.EventBinding
    environment: Environment = None                         # X9: schema 7
    lights: list = field(default_factory=list)               # X9: Light placements
    texture_style: str = 'legacy'                              # X9 worlds opt into procedural surfaces
    quads: list = field(default_factory=list)                 # original sloped geometry; no schema change
    triangles: list = field(default_factory=list)
    racing: racinglib.RaceConfig = None


def _prop_transform(e):
    return e.kind == 'prop' and (e.scale is not None or bool(e.yaw_degrees))


def schema_of(world):
    """The world_entities schema the world needs."""
    if world.racing is not None:
        return RACING_SCHEMA
    if world.environment is not None or world.lights:
        return VISUAL_SCHEMA
    if world.bindings:
        return BINDING_SCHEMA
    if world.prefab_instances or any(_prop_transform(e) for e in world.entities):
        return PREFAB_SCHEMA
    if any(e.kind == 'prop' for e in world.entities) or any(d.sound for d in world.mover_definitions):
        return ASSET_SCHEMA
    if world.scripts or world.ability_script or any(e.script for e in world.entities):
        return SCRIPT_SCHEMA
    return DEFINITION_SCHEMA if world.mover_definitions else ENTITY_SCHEMA


def instance_records(world):
    return [i.record() for i in sorted(world.prefab_instances, key=lambda i: res._bytes(i.id))]


def _finite(v, n=3):
    return (isinstance(v, (tuple, list)) and len(v) == n and
            all(isinstance(x, (int, float)) and math.isfinite(x) and abs(x) <= WORLD_LIMIT for x in v))


def _a(kind):
    return ('an ' if kind[0] in 'aeiou' else 'a ') + kind


def _inside(p, lo, hi):
    return all(lo[k] <= p[k] <= hi[k] for k in range(3))


def definition_box(world, e):
    """A placed mover's box from its definition, or None."""
    d = next((m for m in world.mover_definitions if m.id == e.definition), None)
    if d is None or not _finite(e.position) or not _finite(d.size):
        return None
    return Box(tuple(e.position[k] - d.size[k] / 2 for k in range(3)),
               tuple(e.position[k] + d.size[k] / 2 for k in range(3)), d.material, owner=e.id)


def owned_bounds(world, eid):
    boxes = [b for b in world.boxes if b.owner == eid]
    if not boxes:
        return None
    return (tuple(min(b.min[k] for b in boxes) for k in range(3)),
            tuple(max(b.max[k] for b in boxes) for k in range(3)))


def declaration(world):
    """The world's resources.PackageDecl (X4), or None for an implicit
    package. Provides is derived from the content, never typed in."""
    if world.package is None:
        return None
    provides = [world.id] + [d.id for d in world.mover_definitions] + [s.id for s in world.scripts]
    return res.PackageDecl(world.package, sorted(set(provides), key=str.encode), list(world.requires))


def _resources(world, by_id, defs, fetch, errs):
    """The ResourceSet the world's references resolve against -- its own
    resources, then everything it imports from the packages it requires --
    and the imported scripts by ID. The engine's rules (resource.h)."""
    decl = declaration(world)
    imported = {}
    deps = []
    if decl is not None:
        try:
            res.parse_decl({'package': decl.record()})
        except res.ResourceError as e:
            errs.append(str(e))
            decl = None
    if decl is not None and decl.requires:
        try:
            deps = deplib.load_set(decl, fetch, world.id)
        except deplib.PackageError as e:
            errs.append(f'package: {e.diagnostics[0]}')
            deps = []
            decl = res.PackageDecl(decl.id, decl.provides, [])
    rs = deplib.resource_set(decl, deps)
    try:
        for i, e in enumerate(world.entities):
            if res.is_id(e.id, 'entity') and e.id in by_id and by_id[e.id] is e:
                rs.add(e.id, 'entity', 0, i)
        for i, d in enumerate(world.mover_definitions):
            if d.id in defs:
                rs.add(d.id, 'mover', 0, i)
        seen = set()
        for i, sc in enumerate(world.scripts):
            if res.is_id(sc.id, 'script') and sc.id not in seen:
                seen.add(sc.id)
                rs.add(sc.id, 'script', 0, i)
        if decl is not None and res.is_id(world.id, 'world'):
            rs.add(world.id, 'world', 0, 0)
        deplib.add_dependencies(rs, deps)
    except res.ResourceError as e:
        errs.append(str(e))
    for i, d in enumerate(deps):
        for sc in d.scripts:
            if (i + 1, sc.id) in rs.imports:
                imported[sc.id] = sc
    return rs, imported, deps


def validate(world, fetch=None):
    """Diagnostics (errors) for the world's entities and links; [] when it
    compiles. Each names the placement, and the link, it is about.
    `fetch` finds the packages the world requires (dependencies.
    directory_source / mapping_source); none are needed when it requires
    none. Every reference resolves through the engine's typed rules
    (assetlab.resources): a script field never takes a mover, a link never
    reaches another package, an import must be declared."""
    errs = []
    if world.package is not None:
        why = res.package_id_error(world.package)
        if why:
            errs.append(f"package '{world.package}': {why}")
    ok, why = ids.valid_id(world.id)
    ns = world.id.partition(':')[0]
    if not ok:
        errs.append(f'world id {world.id!r}: {why}')
    elif world.id.partition(':')[2].partition('/')[0] != 'world':
        errs.append(f'world id {world.id!r}: type must be world')
    if len(world.entities) > MAX_ENTITIES:
        errs.append(f'{len(world.entities)} entities; the runtime takes at most {MAX_ENTITIES}')
    defs = {}
    if len(world.mover_definitions) > MAX_MOVER_DEFINITIONS:
        errs.append(f'{len(world.mover_definitions)} mover definitions; the runtime takes at most {MAX_MOVER_DEFINITIONS}')
    for d in world.mover_definitions:
        ok, why = ids.valid_id(d.id)
        if not ok:
            errs.append(f'{d.id!r}: malformed mover definition ID: {why}')
            continue
        d_ns, _, rest = d.id.partition(':')
        if rest.partition('/')[0] != 'mover':
            errs.append(f'{d.id}: a mover definition ID has type mover')
            continue
        if d_ns != ns:
            errs.append(f'{d.id}: mover definitions belong to the world\'s namespace {ns!r}')
        if d.id in defs:
            errs.append(f'{d.id}: duplicate mover definition ID')
            continue
        defs[d.id] = d
        if not (_finite(d.size) and all(x >= 0.01 for x in d.size)):
            errs.append(f'{d.id}: size must be finite, at least 0.01 wu on each axis')
        if not _finite(d.move) or not (0.01 <= math.sqrt(sum(x*x for x in d.move)) <= MAX_MOVE):
            errs.append(f'{d.id}: move must be finite, between 0.01 and {MAX_MOVE} wu')
        if not (isinstance(d.speed, (int, float)) and math.isfinite(d.speed) and 0 < d.speed <= MAX_SPEED):
            errs.append(f'{d.id}: speed must be in (0, {MAX_SPEED}] wu/s')
        if d.material not in world.materials:
            errs.append(f'{d.id}: unknown material {d.material!r}')

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
    schema = schema_of(world)
    if schema >= PREFAB_SCHEMA:
        for e in world.entities:
            if e.id in by_id and '__' in e.id.partition('/')[2]:
                errs.append(f"{e.id}: '__' is reserved for prefab children (<instance>__<child>)")
    rs, imported, deps = _resources(world, by_id, defs, fetch, errs)
    if world.racing is not None:
        errs += racinglib.errors(world.racing)
        if isinstance(world.racing.model,str):
            try:
                rs.resolve(res.PROP_MODEL, 'racing vehicle', world.racing.model)
            except res.ResourceError as x:
                errs.append(str(x))
    # X6: instances expand into ordinary entities before any link resolves,
    # so a world link may name a child (the engine's order).
    records = instance_records(world)
    errs += prefablib.instances_errors(records)
    expanded = []
    own_b = bindlib.records(world.bindings)
    inst_bindings = []
    if records and world.package is None:
        errs.append('world_entities: prefab instances need a declared world package (its namespace names their children)')
    elif records and not prefablib.instances_errors(records):
        expanded, e2 = prefablib.expand_instances(records, world.id, rs, deps, len(world.entities),
                                                  sum(len(e.links) for e in world.entities),
                                                  len(world.mover_definitions) + sum(1 for e in world.entities
                                                                                    if e.kind == 'mover' and e.definition is None),
                                                  inst_bindings, (len(own_b), sum(len(b['conditions']) for b in own_b),
                                                                  sum(len(b['actions']) for b in own_b)))
        errs += e2
    for c in expanded:
        by_id[c['id']] = Entity(c['id'], c['kind'], links=[Link(ln['event'], ln['target'], ln['input']) for ln in c['links']])
    if world.lights and world.environment is None:
        errs.append('world_entities: lights need an environment')
    if world.environment is not None:
        env = world.environment
        for name, value, hi in [('ambient', env.ambient, 2), ('clear', env.clear, 1), ('fog_color', env.fog_color, 1)]:
            if not _finite(value) or any(x < 0 or x > hi for x in value):
                errs.append(f'environment: {name} must be three finite values in 0..{hi}')
        if not (isinstance(env.fog_density, (int, float)) and math.isfinite(env.fog_density) and
                0 <= env.fog_density <= 2 and isinstance(env.fog_start, (int, float)) and
                math.isfinite(env.fog_start) and 0 <= env.fog_start <= 4096):
            errs.append('environment: fog density/start out of range')
    if len(world.lights) > 32:
        errs.append('lights: more than 32 authored lights')
    last = ''
    for light in world.lights:
        why = prefablib.local_id_error(light.id, 'light id') if isinstance(light.id, str) else 'malformed light id'
        if why: errs.append(f'light {light.id!r}: {why}')
        if last and light.id <= last: errs.append(f'lights: IDs must be unique and canonical at {light.id}')
        last = light.id
        if light.type not in ('point', 'spot'): errs.append(f'light {light.id}: type must be point or spot')
        if not _finite(light.position) or not _finite(light.color) or any(x < 0 or x > 1 for x in light.color):
            errs.append(f'light {light.id}: invalid position or color')
        if not (isinstance(light.intensity, (int, float)) and math.isfinite(light.intensity) and
                0 < light.intensity <= 16 and isinstance(light.range, (int, float)) and
                math.isfinite(light.range) and 0.05 < light.range <= 64):
            errs.append(f'light {light.id}: intensity or range out of bounds')
        if light.relay is not None and (light.relay not in by_id or by_id[light.relay].kind != 'relay'):
            errs.append(f'light {light.id}: relay {light.relay!r} is missing or not a relay')
        if light.type == 'spot' and (not _finite(light.direction) or
                sum(x*x for x in light.direction) < 0.0001 or
                not isinstance(light.inner_degrees, (int, float)) or
                not isinstance(light.outer_degrees, (int, float)) or
                not math.isfinite(light.inner_degrees) or not math.isfinite(light.outer_degrees) or
                not (0 <= light.inner_degrees < light.outer_degrees <= 90)):
            errs.append(f'light {light.id}: invalid spot direction or cone')
    world._expanded = expanded
    if all(e.kind in KINDS for e in world.entities):
        errs += world_state.errors([e.kind for e in world.entities] + [c['kind'] for c in expanded])
    for d in world.mover_definitions:
        if d.sound is not None and d.id in defs:
            try:
                rs.resolve(res.MOVER_SOUND, d.id, d.sound)
            except res.ResourceError as x:
                errs.append(str(x))
    total = 0
    for e in world.entities:
        if e.kind not in KINDS:
            errs.append(f'{e.id}: unknown kind {e.kind!r} (one of {", ".join(KINDS)})')
            continue
        if e.scale is not None and e.kind != 'prop':
            errs.append(f'{e.id}: only a prop takes a scale (it is {_a(e.kind)})')
        if _prop_transform(e):
            sc = 1.0 if e.scale is None else e.scale
            if not (isinstance(sc, (int, float)) and math.isfinite(sc) and 0.25 <= sc <= 4.0):
                errs.append(f'{e.id}: scale {sc:g} out of range (uniform, 0.25 to 4)')
            if not (isinstance(e.yaw_degrees, (int, float)) and abs(e.yaw_degrees) <= 360):
                errs.append(f'{e.id}: yaw_degrees out of range (|yaw| <= 360)')
        if e.kind == 'prop':
            if not _finite(e.position):
                errs.append(f'{e.id}: a prop needs a finite position inside the world')
            if e.model is None:
                errs.append(f'{e.id}: a prop needs a model')
            else:
                try:
                    rs.resolve(res.PROP_MODEL, e.id, e.model)
                except res.ResourceError as x:
                    errs.append(str(x))
            if e.links:
                errs.append(f'{e.id}: a prop emits nothing, so it has no links')
        elif e.model is not None:
            errs.append(f'{e.id}: only a prop takes a model (it is {_a(e.kind)})')
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
        if e.definition is not None and e.kind != 'mover':
            errs.append(f'{e.id}: only a mover takes a definition (it is {_a(e.kind)})')
        if e.kind == 'mover' and e.definition is not None:
            try:
                rs.resolve(res.MOVER_DEF, e.id, e.definition)
            except res.ResourceError as x:
                errs.append(str(x))
            if not _finite(e.position):
                errs.append(f'{e.id}: a mover with a definition needs a finite position (its box\'s centre)')
            if e.move is not None or e.speed is not None or owned_bounds(world, e.id) is not None:
                errs.append(f'{e.id}: a mover with a definition takes its size, move, speed and geometry from it')
        elif e.kind == 'mover' and world.mover_definitions:
            errs.append(f'{e.id}: in a world with mover definitions every mover names one')
        elif e.kind == 'mover' and (any(x.kind == 'prop' for x in world.entities) or
                                    any(d.sound for d in world.mover_definitions)):
            errs.append(f'{e.id}: a world with props or mover sounds (world_entities schema 4) gives every mover a '
                        f'definition; inline movers are schema 1 only')
        elif e.kind == 'mover':
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
            try:
                rs.resolve(res.LINK_TARGET, e.id, ln.target)
            except res.ResourceError as x:
                errs.append(str(x))
                continue
            t = by_id[ln.target]
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
    errs += _script_errors(world, ns, rs, imported, expanded)
    # X7: the world's own bindings, against every entity (children too).
    kinds = {k: v.kind for k, v in by_id.items()}
    parsed, e3 = bindlib.world_errors(own_b, rs, kinds.get, schema)
    errs += e3
    if not errs:
        errs += _graph_errors(list(world.entities) + [by_id[c['id']] for c in expanded], by_id)
    if not errs:
        errs += bindlib.cycle_errors(parsed + inst_bindings, kinds.get)
    world._bindings = parsed + inst_bindings
    return errs


def _script_errors(world, ns, rs, imported, expanded=()):
    errs = scriptlib.validate(world.scripts, ns)
    by_script = {s.id: s for s in world.scripts}
    by_script.update({k: v for k, v in imported.items() if k not in by_script})

    def ref(field_name, who, sid, cb):
        try:
            rs.resolve(field_name, who, sid)
        except res.ResourceError as x:
            errs.append(str(x))
            return
        if cb not in by_script[sid].callbacks:
            errs.append(f'{who}: script {sid} does not declare {cb}')

    for e in world.entities:
        if e.script is not None and e.kind != 'interactable':
            errs.append(f'{e.id}: only an interactable takes a script (it is {_a(e.kind)})')
        elif e.script is not None:
            ref(res.SCRIPT, e.id, e.script, 'on_used')
    if world.ability_script is not None:
        ref(res.ABILITY_SCRIPT, 'ability_script', world.ability_script, 'on_ability')
    # X6: a prefab child's script joins the world's table (once) too.
    extra = {c['script'] for c in expanded if 'script' in c and c['script'] not in by_script}
    n = len(world.scripts) + len(imported) + len(extra)
    if n > scriptlib.MAX_SCRIPTS:
        errs.append(f'{n} scripts with its imports; the runtime takes at most {scriptlib.MAX_SCRIPTS}')
    size = sum(len(s.source.encode('ascii', 'replace')) for s in list(world.scripts) + list(imported.values()))
    if size > scriptlib.MAX_POOL:
        errs.append(f"the world's scripts with its imports are {size} bytes; at most {scriptlib.MAX_POOL}")
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
        if e.script is not None:
            r['script'] = e.script
    if e.kind == 'teleport':
        r['yaw_degrees'] = float(e.yaw_degrees)
    if e.kind == 'trigger':
        r['bounds'] = {'min': [float(x) for x in e.bounds[0]], 'max': [float(x) for x in e.bounds[1]]}
    if e.kind == 'prop':
        r['model'] = e.model
        r['position'] = [float(x) for x in e.position]
        if e.scale is not None:
            r['scale'] = float(e.scale)
        if e.yaw_degrees:
            r['yaw_degrees'] = float(e.yaw_degrees)
    if e.kind == 'mover' and e.definition is not None:
        r['definition'] = e.definition
        r['position'] = [float(x) for x in e.position]
    elif e.kind == 'mover':
        lo, hi = owned_bounds(world, e.id)
        r['bounds'] = {'min': [float(x) for x in lo], 'max': [float(x) for x in hi]}
        r['move'] = [float(x) for x in e.move]
        r['speed'] = float(e.speed)
    return r


def _definition_record(d):
    r = {'id': d.id, 'size': [float(x) for x in d.size], 'move': [float(x) for x in d.move],
         'speed': float(d.speed)}
    if d.sound is not None:
        r['sound'] = d.sound
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


def _quad_triangles(q, vertices, indices):
    p=q.corners
    u=[p[1][k]-p[0][k] for k in range(3)]
    v=[p[2][k]-p[0][k] for k in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    length=math.sqrt(sum(x*x for x in n))
    n=tuple(x/length for x in n)
    base=len(vertices)
    for i,c in enumerate(p):
        uv=((0,0),(1,0),(1,1),(0,1))[i]
        vertices.append((tuple(float(x) for x in c),n,uv))
    indices += [base,base+1,base+2,base,base+2,base+3]


def _triangle(t, vertices, indices):
    p=t.corners
    u=[p[1][k]-p[0][k] for k in range(3)]
    v=[p[2][k]-p[0][k] for k in range(3)]
    n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    length=math.sqrt(sum(x*x for x in n))
    n=tuple(x/length for x in n)
    base=len(vertices)
    for i,c in enumerate(p):
        vertices.append((tuple(float(x) for x in c),n,((0,0),(1,0),(0,1))[i]))
    indices += [base,base+1,base+2]


def _texture(rgb):
    """16x16 RGBA: the colour with a faint 4-texel check, so motion shows."""
    px = bytearray()
    for y in range(16):
        for x in range(16):
            d = 0.9 if ((x // 4) + (y // 4)) % 2 else 1.0
            px += bytes((int(rgb[0] * d), int(rgb[1] * d), int(rgb[2] * d), 255))
    return 16, 16, bytes(px)


def _industrial_texture(name, rgb):
    """Original deterministic painted/concrete/metal detail, tiled one wu.

    No resource download or random seed. The dark seams and sparse wear give
    large authored boxes a surface rhythm without the X1 diagnostic check.
    """
    px = bytearray()
    seed = sum((i + 1) * ord(c) for i, c in enumerate(name))
    metal = name in ('metal', 'grate', 'bars', 'pipe', 'truck', 'generator', 'tower', 'fence')
    floorish = name.startswith('floor') or name in ('ground', 'grate', 'water')
    for y in range(64):
        for x in range(64):
            h = (x * 374761393 + y * 668265263 + seed * 2246822519) & 0xffffffff
            h = ((h ^ (h >> 13)) * 1274126177) & 0xffffffff
            grain = ((h >> 24) - 128) / 128.0
            d = 1.0 + grain * (0.055 if metal else 0.085)
            if floorish:
                if x in (0, 1, 63) or y in (0, 1, 63): d *= 0.65
                if x in (4, 59) and y in (4, 59): d *= 1.4
                if name == 'grate' and (x % 12 < 3 or y % 12 < 3): d *= 0.72
            elif metal:
                if x in (0, 1, 31, 32, 62, 63): d *= 0.68
                if y in (0, 1, 62, 63): d *= 0.82
                if x in (5, 58) and y in (5, 58): d *= 1.5
                if 27 <= x <= 29: d *= 1.12
            else:
                if x in (0, 1, 62, 63): d *= 0.76
                if y in (0, 1, 63): d *= 0.88
                if y in (16, 17): d *= 0.9
                if h % 173 == 0: d *= 0.72
            px += bytes(max(0, min(255, round(c * d))) for c in rgb) + b'\xff'
    return 64, 64, bytes(px)


def compile_world(world, output, fetch=None):
    """Validate and write `world` as an OALMAP. Raises WorldError with every
    diagnostic when it does not validate. Returns (manifest, report).
    `fetch` finds the packages it requires (X4); their content is not
    copied in -- MegaMod loads them beside the world, by package ID."""
    errs = validate(world, fetch)
    if world.texture_style not in ('legacy', 'industrial'):
        errs.append(f'unknown texture_style {world.texture_style!r}')
    for b in world.boxes:
        if not (_finite(b.min) and _finite(b.max) and all(b.max[k] > b.min[k] for k in range(3))):
            errs.append(f'box {b.min}..{b.max}: empty or not finite')
        if b.material not in world.materials:
            errs.append(f'box {b.min}..{b.max}: unknown material {b.material!r}')
    for i,q in enumerate(world.quads):
        if q.material not in world.materials:
            errs.append(f'quad {i}: unknown material {q.material!r}')
        if len(q.corners)!=4 or any(not _finite(p) for p in q.corners):
            errs.append(f'quad {i}: needs four finite corners')
            continue
        p=q.corners
        u=[p[1][k]-p[0][k] for k in range(3)]
        v=[p[2][k]-p[0][k] for k in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        length=math.sqrt(sum(x*x for x in n))
        if length<0.001 or abs(sum(n[k]*(p[3][k]-p[0][k]) for k in range(3)))>0.01*length:
            errs.append(f'quad {i}: degenerate or non-planar')
        v2=[p[3][k]-p[0][k] for k in range(3)]
        n2=(v[1]*v2[2]-v[2]*v2[1],v[2]*v2[0]-v[0]*v2[2],v[0]*v2[1]-v[1]*v2[0])
        if sum(n[k]*n2[k] for k in range(3))<=0:
            errs.append(f'quad {i}: twisted or reversed winding')
    for i,t in enumerate(world.triangles):
        if t.material not in world.materials:
            errs.append(f'triangle {i}: unknown material {t.material!r}')
        if len(t.corners)!=3 or any(not _finite(p) for p in t.corners):
            errs.append(f'triangle {i}: needs three finite corners')
            continue
        p=t.corners
        u=[p[1][k]-p[0][k] for k in range(3)]
        v=[p[2][k]-p[0][k] for k in range(3)]
        n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        if sum(x*x for x in n)<1e-6:
            errs.append(f'triangle {i}: degenerate')
    if not world.spawns:
        errs.append('the world has no player start')
    if errs:
        raise WorldError(errs)
    index_of = {e.id: i for i, e in enumerate(world.entities)}
    defs = {d.id: d for d in world.mover_definitions}
    # A placed mover with a definition is drawn as one box of it where it
    # stands (the runtime's collision is the same box).
    boxes = list(world.boxes) + [definition_box(world, e) for e in world.entities
                                 if e.kind == 'mover' and e.definition is not None]
    vertices, src_indices, runs = [], [], []
    for b in boxes:
        first = len(src_indices)
        _box_triangles(b, vertices, src_indices)
        owner = (GROUP_ENTITY, index_of[b.owner]) if b.owner else None
        # A mover's triangles are its own collision, not the world's.
        runs.append((b.material, first, len(src_indices) - first, b.solid and not b.owner, owner))
    for q in world.quads:
        first=len(src_indices)
        _quad_triangles(q,vertices,src_indices)
        runs.append((q.material,first,len(src_indices)-first,q.solid,None))
    for t in world.triangles:
        first=len(src_indices)
        _triangle(t,vertices,src_indices)
        runs.append((t.material,first,len(src_indices)-first,t.solid,None))
    mats = sorted(world.materials)
    tex_index = {m: i for i, m in enumerate(mats)}
    indices, groups, collision_triangles = build_groups(runs, src_indices, tex_index, lambda m: False,
                                                        {}, len(mats), VERSION)
    packed = pack_vertices(indices, vertices, {})
    lo = [min(v[0][k] for v in vertices) for k in range(3)]
    hi = [max(v[0][k] for v in vertices) for k in range(3)]
    for e in world.entities:            # a mover's open position counts too
        if e.kind == 'mover':
            if e.definition is not None:
                b = definition_box(world, e)
                blo, bhi, move = b.min, b.max, defs[e.definition].move
            else:
                (blo, bhi), move = owned_bounds(world, e.id), e.move
            lo = [min(lo[k], blo[k] + min(0.0, move[k])) for k in range(3)]
            hi = [max(hi[k], bhi[k] + max(0.0, move[k])) for k in range(3)]
    entities = [_entity_record(world, e) for e in world.entities]
    section = {'schema': ENTITY_SCHEMA, 'entities': entities}
    if world.mover_definitions:
        section = {'schema': DEFINITION_SCHEMA, 'entities': entities,
                   'mover_definitions': [_definition_record(d) for d in world.mover_definitions]}
    if world.scripts or world.ability_script or any(e.script for e in world.entities):
        section['schema'] = SCRIPT_SCHEMA
        section['scripts'] = [scriptlib.record(s) for s in world.scripts]
        if world.ability_script:
            section['ability_script'] = world.ability_script
    if any(e.kind == 'prop' for e in world.entities) or any(d.sound for d in world.mover_definitions):
        section['schema'] = ASSET_SCHEMA
    if schema_of(world) >= PREFAB_SCHEMA:
        section['schema'] = schema_of(world)
        if world.prefab_instances:
            section['prefab_instances'] = instance_records(world)
    if world.bindings:
        section['bindings'] = bindlib.records(world.bindings)
    if world.environment is not None:
        section['environment'] = world.environment.record()
    if world.lights:
        section['lights'] = [light.record() for light in world.lights]
    if world.racing is not None:
        section['racing'] = world.racing.record()
    kinds = {k: sum(e.kind == k for e in world.entities) for k in KINDS}
    manifest = {
        'package_version': VERSION, 'importer_version': 'original_world-0.1.0',
        'id': world.id, 'namespace': world.id.partition(':')[0],
        'map_id': world.file_name, 'display_name': world.display_name,
        'source_format': 'original world (Open Asset Lab)',
        'required_open_halo_runtime': f'external-map-v{VERSION}',
        'geometry': {'vertices': len(packed), 'triangles': len(indices) // 3,
                     'collision_triangles': collision_triangles, 'boxes': len(boxes), **({'quads': len(world.quads)} if world.quads else {}),
                     **({'triangles_authored': len(world.triangles)} if world.triangles else {})},
        'material_paths': mats, 'spawn_points': world.spawns, 'flag_points': [], 'breakables': [],
        'world_entities': section,
        # X1-X4 worlds list the five kinds they always did (their bytes are
        # pinned); a world with props says so.
        'supported_features': ['boxes', 'player starts', 'world entities: ' + ', '.join(
            k for k in KINDS if k != 'prop' or any(e.kind == 'prop' for e in world.entities))],
        'unsupported_features': [],
        'bounds': {'min': lo, 'max': hi}, 'texture_count': len(mats),
        'source_provenance': 'original content built by Open Asset Lab; no third-party assets',
    }
    decl = declaration(world)
    if decl is not None:
        manifest['package'] = decl.record()
    manifest_bytes = manifest_json(manifest)
    write_package(output, VERSION, manifest_bytes, packed, indices, groups,
                  [(_industrial_texture(m, world.materials[m]) if world.texture_style == 'industrial' else
                    _texture(world.materials[m])) for m in mats], world.spawns, lo, hi)
    with open(output, 'rb') as f:
        data = f.read()
    digest = worldkey.world_digest(data, fetch)
    report = {'world': world.id, 'entities': len(entities), 'kinds': kinds,
              'mover_definitions': len(world.mover_definitions), 'entity_schema': section['schema'],
              'scripts': [s.id for s in world.scripts],
              'props': {e.id: e.model for e in world.entities if e.kind == 'prop'},
              'mover_sounds': {d.id: d.sound for d in world.mover_definitions if d.sound},
              'package': world.package, 'requires': {q.package: list(q.resources) for q in world.requires},
              'links': sum(len(e.links) for e in world.entities),
              'prefab_instances': {i.id: i.prefab for i in world.prefab_instances},
              'bindings': [{'id': b['id'], 'instance': b.get('instance'), 'source': b['source'], 'event': b['event'],
                            'conditions': len(b['conditions']), 'actions': [a['action'] for a in b['actions']]}
                           for b in getattr(world, '_bindings', [])],
              'expanded': [{'path': c['path'], 'entity': c['id'], 'kind': c['kind'], 'index': c['index']}
                           for c in getattr(world, '_expanded', [])],
              'triangles': len(indices) // 3, 'package_bytes': len(data),
              'package_sha256': hashlib.sha256(data).hexdigest(),
              'world_digest': f'{digest:016x}', 'world_key': f'{worldkey.fold(digest):08x}'}
    report['world_state'] = world_state.count([e.kind for e in world.entities] +
                                               [c['kind'] for c in getattr(world, '_expanded', [])])
    return manifest, report
