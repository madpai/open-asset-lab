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
