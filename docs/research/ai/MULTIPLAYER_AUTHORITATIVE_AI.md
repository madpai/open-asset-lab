# Host-authoritative AI and replication

**VERIFIED MegaMod boundary:** X3 gameplay Lua runs only on the host; joiners consume replicated results. World inputs use the host event queue and damage uses the normal combat pipeline. Protocol v10 and the content key already guard imported world content. **VERIFIED external comparison:** [Unreal's networking overview](https://dev.epicgames.com/documentation/unreal-engine/networking-overview-for-unreal-engine) assigns true gameplay state to the server and presentation to clients; it notes that animation graphs are local while their driving variables may need replication. This supports MegaMod's existing authority direction, without requiring Unreal's actor model.

| Host owns | Client receives or derives |
|---|---|
| perception, memory, decisions, nav queries, path repair | no gameplay AI execution |
| action validation, weapon fire, damage, interaction, death | authoritative outcomes and visual/audio cues |
| agent spawn/despawn, position, velocity, facing, health and goal/action state needed for presentation | interpolation, animation graph and effects |

**Proposed wire minimum:** generation-safe agent identity; spawn/archetype reference; transform/velocity/facing; compact locomotion and action/weapon intent; health/death; discrete world effects through existing channels. Goals and blackboard normally stay host-only. Send a small high-level animation intent if movement alone cannot determine it (e.g. reload, use, melee), with start tick/sequence for late join and duplicate protection. Do not stream BT nodes, utility scores, full paths or sensory histories. Interest filtering and update cadence should be measured; reliable ordered state only where missing one change breaks correctness. An action event and durable action state serve different purposes.

**Late join:** load matching content, then current agents and durable world state, including a currently open door and a currently playing long action if needed for visuals. It need not replay the AI's past thoughts. The host must revalidate client-originated use requests and never accept client AI decisions. No lockstep determinism requirement is justified: identical package hashes help content compatibility but floating-point/path/AI logic need not run on clients. Compare snapshots under loss, reorder and correction; preserve X1–X6 content key semantics when adding future resources.

**Open design risk:** MegaMod's existing bot units already replicate through game state. Audit their actual packet fields and update rates before adding an NPC protocol, so the first agent uses the smallest compatible extension rather than a parallel entity network stack.
