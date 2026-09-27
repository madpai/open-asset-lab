# Entity I/O, affordances and the X7 seam

**VERIFIED:** MegaMod X1's placed world entities have typed IDs, load-resolved links and a bounded host event queue; X3 `world.send` requests an existing input through that queue, while `game.damage` enters the regular damage pipeline. X6 prefab children expand into those ordinary entities. See [world entities](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/WORLD_ENTITIES.md), [scripting](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/SCRIPTING.md) and [prefabs](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/PREFABS.md). The installed Garry's Mod `ttt.fgd` exposes named buttons, doors, inputs, outputs and activators; that is local evidence of practical map I/O, not a license to inherit Source class names.

## Proposed semantic contract

An **affordance** tells an agent what can be attempted, on what target and with which preconditions. `can_use` on a button, `can_open` and `blocks_navigation` on a door, `can_heal` on a station, `provides_cover` on a position, and `is_hazard` on a volume are examples. Treat them as typed capabilities with target handle, interaction point, range, cost and state query, not free-form tags that silently promise executable behavior. OAL can translate Source `func_button` or original editor content into the same capability only when the corresponding MegaMod action exists; otherwise it reports an unsupported or inferred semantic.

The future X7 action executor should be the common seam: **player input / X7 graph / host Lua / NPC request → validated engine action → event queue, movement or damage system → authoritative result**. For `use(button)`, the NPC first reaches the interaction point, faces it if required, requests use through the host's ordinary interaction validator, and waits for a result. For `open(door)`, it requests the existing input with an actor handle and gets accepted/rejected/completed states. Never let a planner mutate mover state directly. The current X3 Lua API has only `world.send` and `game.damage`; this text does not imply a new Lua API has landed.

## Small action vocabulary proposal

| Candidate | Layer | Reason |
|---|---|---|
| `move_to`, `stop`, `face` | agent executor over nav/movement | Motion needs asynchronous progress and failure. |
| `use`, `activate`, `open`, `close`, `toggle` | general engine/X7 action | Same world interaction for humans, graphs and AI; validate actor and target. |
| `attack`, `fire`, `melee` | agent executor requesting ordinary combat | Weapon rules, cooldown, damage and credit stay native. |
| `look_at`, `investigate` | behavior intent | They choose movement/attention; not universal world mutations. |
| `alert`, `share_target`, `reserve_position` | group service | Explicit sharing and lease semantics, not ambient omniscience. |
| complex custom tactics | host script escape hatch, bounded | Scripts compose existing actions; they do not own independent physics or authority. |

**Validation questions:** does every affordance name a real executable action, can a stale target be rejected, can X7 report failure, and can OAL preview interaction points and target reachability? Keep source-specific names in importers.
