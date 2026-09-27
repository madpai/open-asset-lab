# Original worlds and generic world entities

**Status:** implemented 2026-09-26 for MegaMod's X1 slice. The runtime side
is MegaMod's [`docs/WORLD_ENTITIES.md`](https://github.com/madpai/megamod-showdown/blob/main/docs/WORLD_ENTITIES.md).

An original world is authored as data -- boxes, starts, placed entities --
and compiled by the **same packaging stage** as imported maps
(`package.build_groups`, `pack_vertices`, `write_package`, extracted from
`compile_map` without changing a byte of its output). No Source entity
class is involved: entities are one of five generic kinds MegaMod runs
natively.

```
assetlab.world.OriginalWorld (built in code: tests, assetlab.fixtures)
  -> world.validate()          every diagnostic, named by placed ID
  -> world.compile_world()     boxes -> triangles, solid-colour textures,
                               groups (a mover's tagged GROUP_ENTITY),
                               manifest "world_entities", OALMAP v3
```

There is **no public text format** for original worlds yet, on purpose:
X1 needed the compiler seam and the validation, not an authoring language.
A future glTF importer or text format should produce the same
`OriginalWorld` (or its successor) and reuse `validate()`.

## Entities

| Kind | Emits | Accepts | Fields |
|---|---|---|---|
| `interactable` | `used` | - | `position`, `reach` |
| `relay` | `fired` | `activate` | - |
| `mover` | - | `open`, `close`, `toggle` | `move`, `speed`; geometry = the boxes it owns |
| `trigger` | `entered` | - | `bounds` |
| `teleport` | - | `teleport` | `position`, `yaw_degrees` |

Links: `Link(event, target placed ID, input)`.

Placed IDs: `namespace:entity/name` in the world's namespace
(`x1:world/event_lab` owns `x1:entity/door_main`). The `entity` type was
added to the ID registry (`assetlab/ids.py`, [CONTENT_IDS.md](CONTENT_IDS.md))
for this: it names a placement, unique within its world, not a reusable
definition.

## Validation (`world.validate`)

Errors, each naming the placement and link:

- world ID malformed or not type `world`; more than 64 entities;
- placed ID malformed, not type `entity`, not in the world's namespace, duplicate;
- unknown kind; interactable/teleport without a finite position; reach
  outside (0, 4]; non-finite yaw; trigger bounds missing, non-finite, or
  thinner than 0.05 wu; mover move not in [0.01, 64] wu or speed not in
  (0, 64] wu/s; a mover with no geometry; geometry owned by a missing
  entity or by a non-mover;
- more than 8 links on one entity or 256 in all; a link event the source
  does not emit; an unknown input; a missing target
  (`x1:entity/button_main references missing target x1:entity/relay_main`);
  a target that does not accept the input; a self-link;
- a teleport destination inside a trigger (it would fire on arrival);
- a link cycle (all links are zero-delay: a cycle would loop in one tick);
  a chain longer than 16 links; one event able to cause more than 256
  (diamond fan-out), the runtime's per-step budget.

These are the runtime's own limits (MegaMod `src/asset/world_def.h`), and
the runtime checks them again at load.

## The X1 fixture

`assetlab fixture x1_event_lab --output x1_event_lab.oalmap` (see
`assetlab/fixtures.py` for the layout): two rooms, a sliding door in the
dividing wall, a button beside it, a trigger pad, a teleport destination on
a platform. `button_main --used/activate--> relay_main --fired/open-->
door_main`; `teleport_trigger --entered/teleport--> teleport_destination`.
Deterministic (byte-identical builds), original, 22 KB. It is a test
fixture, not shipped content.

`tests/test_world.py` covers the fixture, determinism, reordering (links
follow IDs, the door's group index follows its new position), the audit,
and every diagnostic above.

## Mover definitions and the X2 fixture

A `MoverDefinition` (`assetlab.world`) is a reusable mover: `id`
(`namespace:mover/name`, the world's namespace, a registered ID type since
X2), `size`, `move`, `speed` and `material`. A placed mover names it with
`definition=` and gives only `position` (its box's centre); the compiler
draws it as one box of the definition's material and writes
`world_entities` schema 2 ([RUNTIME_PACKAGE.md](RUNTIME_PACKAGE.md)). The
definition is data, not an object: MegaMod resolves each reference once at
load and keeps each placement's state separate. Definitions exist for
movers only.

Validation adds: a malformed, wrongly typed, foreign-namespace or duplicate
definition ID; bad size/move/speed or unknown material; a reference to a
missing definition (`x2:entity/door_b references missing mover definition
x2:mover/...`), to a placed entity, or with a non-mover ID; a link that
targets a definition; a definition on a non-mover; a mover with a
definition that also has inline parameters or geometry, or no position;
an inline mover in a world that has definitions.

`assetlab fixture x2_definition_lab`: three doorways in a dividing wall,
each closed by a placement of `x2:mover/basic_slide_door`; `button_a ->
relay_a -> door_a`, `button_b -> relay_b -> door_b`, `door_c` unlinked,
plus a trigger -> teleport. Deterministic, original, 30 KB. The world
key's coverage is tested on it (`WorldKeyTests`): geometry, collision,
spawns, placements, definitions, links, trigger and teleport edits change
the key; the display name, a colour and provenance do not.

## Scripts and the X3 fixture

`assetlab.scripts.Script` is host-side gameplay Lua as **content**: `id`
(`namespace:script/name`, a registered ID type since X3), `source`,
declared `callbacks` (`on_used`, `on_ability`) and `api` (`megamod.v1`).
An interactable names one with `script=`; a world names its
`ability_script`. The world is then written as schema 3.

Open Asset Lab **never executes a script**. Validation checks the ID,
namespace, uniqueness, API version, callbacks (declared and defined),
ASCII text, sizes and every reference (missing, not a script, wrong kind,
a link that targets a script); when a Lua **5.4** compiler is on PATH it
also runs `luac5.4 -p` (parse only) and reports syntax errors. A test
builds a package whose script would write a file if run, and checks
nothing ran.

`assetlab fixture x3_script_lab`: the X2 room in the `x3` namespace;
button A is replaced by `button_script` with **no links** and script
`x3:script/button_logic` (opens door A through MegaMod's queue), and the
world's `ability_script` is `x3:script/pulse_ability` (damages players
within 2.5 wu through MegaMod's damage). The two scripts are original
files in `assetlab/data/scripts/x3/`. Deterministic, 32 KB.
`tests/test_scripts.py` covers it, every script diagnostic, the preflight,
no execution, and that one character, a comment or a callback list changes
the world key while the display name does not.

## Packages, dependencies and the X4 fixture

A world may declare itself as a **package** (MegaMod X4, its
`docs/RESOURCES.md`): `OriginalWorld.package = 'x4.resource_lab'` and
`requires = [Requirement('x4.shared', ['x4shared:script/pulse_ability'])]`.
The compiler writes the manifest's `package` member with `provides` derived
from the content (never typed in). A world without `package` is written
exactly as before.

Every reference -- link target, mover definition, script, ability script --
goes through `assetlab.resources.ResourceSet.resolve`, the engine's typed
resolver with its messages: a script field refuses a mover by type ("script
x4:mover/basic_slide_door is a mover definition, expected a script"), a
missing resource names what is missing, an imported script must be listed
in `requires`, a same-package field never reaches another package, and two
providers of one resource are refused. The packages a world requires are
found by package ID (`dependencies.directory_source`, `mapping_source`) and
checked as a graph: each once, no cycles (refused with the path), depth 8,
16 packages, every import provided by the package it is taken from.

A **library** (`dependencies.Library`: a package ID and scripts) compiles
to an OALASSET of kind `library` with `compile_library`. Its scripts may be
in any namespace but a reserved one (`halo_trial`, `megamod`); they are
validated like a world's, and never run.

`assetlab fixture x4_resource_lab --output bundle/x4_resource_lab.oalmap`
writes the world and its library (`bundle/packages/x4.shared.oalasset`):
the X3 room in the `x4` namespace, a declared package whose button runs its
own `x4:script/open_door` and whose `ability_script` is
`x4shared:script/pulse_ability`, imported from `x4.shared` -- a reusable
ability that names no world entity. MegaMod's `scripts/test_x4.sh` builds
it from here, checks the engine refuses every broken variant with the same
message `assetlab resources check` gives, and plays it.

`assetlab resources check PKG... [--packages-dir D] [--json]` checks built
packages as MegaMod loads them (declaration, dependency graph, typed
references, provides) without running anything; `assetlab resources
contract` prints the engine contract Open Asset Lab validates against.

## Prefabs and the X6 fixtures

MegaMod X6 made prefabs real (`assetlab/prefabs.py`; MegaMod
`docs/PREFABS.md`). Author one with the data model, not manifest
dictionaries:

```python
Prefab('x6:prefab/security_door', [
    PrefabChild('button', 'interactable', [PrefabLink('used', 'door', 'toggle')],
                position=(-0.16, -0.7, 0.9), reach=1.2, script='x6:script/security_door_log'),
    PrefabChild('door', 'mover', position=(0, 0, 0.6), size=(0.1, 1.2, 1.2), move=(0, 1.3, 0),
                speed=1.2, sound='x6shared:sound/door_hiss', model='x6shared:model/door_panel'),
    ...])
Library('x6.facility', [script], requires=[Requirement('x6.shared_assets', [...])], prefabs=[door])
world.prefab_instances = [PrefabInstance('north_door', 'x6:prefab/security_door', (0, 3, 0)),
                          PrefabInstance('south_door', 'x6:prefab/security_door', (-3, -2, 0), yaw_degrees=-90)]
```

`validate` checks everything MegaMod will (the engine's words), including
the expansion: generated IDs, the 64-entity limit, scaled limits, links
from the world to a child. `compile_world`'s report lists the expansion
(`expanded`: path, entity, kind, index), and `assetlab resources check
WORLD --packages-dir D` prints it for a built package.

`assetlab fixture x6_prefab_world --output bundle/maps/x6_prefab_world.oalmap
--packages bundle/packages` writes the world and both libraries:
`x6.shared_assets` (door panel, frame post, frame top and button models,
their materials and textures, a hiss -- generated here) and `x6.facility`
(the prefab and its button script). The world: two rooms, north_door in the
x = 0 wall, south_door turned -90 in the y = -2 wall, and a lockdown button
whose world script toggles south's door by its placed ID. `x6_second_world`
places one gate at 45 degrees and 1.25x in an open room. Keys `55b83b8b`
and `f99b737d` (MegaMod agrees; `scripts/test_x6.sh`).

## Event bindings and the X7 fixtures

`OriginalWorld.bindings` and `Prefab.bindings` take
`assetlab.bindings.EventBinding(id, source, event, conditions, actions)`:

```python
EventBinding('toggle_door', 'button', 'used', [Condition('relay_state', 'power', 'active')],
             [Action('toggle', target='door')])
```

`x7_facility_world` places the powered door (`x7:prefab/security_door`)
twice and adds its own bindings: a shock pad (`entered` -> damage 40,
teleport, sound) and a click on the maintenance button, whose Lua script is
the custom logic (every second press opens north's door). `x7_second_world`
places the same prefab once. Build them with
`assetlab fixture x7_facility_world --output ... --packages ...`.

## Asset resources and the X5 fixtures

MegaMod X5 made models, materials, textures and sounds real resources a
library provides (`assetlab/assets.py`; MegaMod `docs/RESOURCES.md` "Asset
resources"). A world places an imported model with
`Entity(eid('crate', ns), 'prop', position=(x, y, z), model='x5shared:model/test_crate')`
-- drawn with the model's materials, solid as its bounds -- and a mover
definition may name a sound (`MoverDefinition(..., sound='x5shared:sound/test_impact')`),
played when a door starts to move. The world only references them; the
bytes stay in the library.

`assetlab fixture x5_resource_world --output bundle/maps/x5_resource_world.oalmap
--packages bundle/packages` writes the world and library `x5.shared_art`
(a 16x16 cyan crate texture, its material, a 0.5 wu box model and a quarter-
second knock, all generated here): the X2 room in the `x5` namespace with
two crates in the west room and knocking doors. `x5_second_world` is a
second consumer (the X1 room, its door a definition, one crate). MegaMod's
`scripts/test_x5.sh` builds both, refuses every broken variant with the same
words as `assetlab resources check`, and plays them.

