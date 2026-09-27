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
