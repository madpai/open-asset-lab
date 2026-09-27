# NPC and entity intelligence research

Research date: 2026-09-27. MegaMod Showdown/Engine `2eae9df` (X6 code `9b45e85`) and Open Asset Lab `c420f2a` (X6 code `10aaafa`) were fetched and inspected before this corpus was written. **This is research and a proposal, not a description of implemented AI.** X7 may change the event/action seam; recheck its landed contract before implementation.

Evidence labels: **VERIFIED** means directly observed in current repository code, locally installed readable files, or a cited primary source. **STRONGLY INDICATED** means multiple observations support a conclusion but no execution trace proves it. **SPECULATIVE** marks a design hypothesis or incomplete reverse engineering. A MegaMod recommendation is a proposal even when its inputs are verified.

## Reading map

| Question | Document |
|---|---|
| Current architecture and proposed layers | [MegaMod AI architecture](MEGAMOD_AI_ARCHITECTURE.md) |
| Bake, package, query and dynamic links | [Recast/Detour navigation](NAVIGATION_RECAST_DETOUR.md) |
| Source NPC lessons | [Source NPC architecture](SOURCE_NPC_ARCHITECTURE.md) |
| Interaction semantics and X7 | [Entity I/O and affordances](ENTITY_IO_AND_AFFORDANCES.md) |
| Sensing and knowledge | [Perception](PERCEPTION.md), [memory](BLACKBOARDS_AND_MEMORY.md) |
| Decision choices | [behavior trees](BEHAVIOR_TREES.md), [utility](UTILITY_AI.md), [GOAP](GOAP.md) |
| Movement and combat space | [steering](STEERING_AND_CROWD.md), [cover](COVER_AND_TACTICAL_POSITIONING.md), [squads](SQUAD_AI.md) |
| Multiplayer, tools, cost | [authority](MULTIPLAYER_AUTHORITATIVE_AI.md), [debugging](AI_DEBUGGING.md), [mobile cost](MOBILE_AI_PERFORMANCE.md) |
| Local evidence and next work | [local systems](LOCAL_GAME_REVERSE_ENGINEERING.md), [roadmap](AI_ROADMAP.md) |

## Current boundary

**VERIFIED:** MegaMod's existing multiplayer bots live in `src/game/brain.c` and use `src/game/nav.c`'s collision-derived grid. The later X1–X6 world content has typed IDs, X3 host-only Lua, X4 dependency resolution, X5 asset resources, and X6 prefabs expanded into ordinary entities. Prefabs do not establish a separate runtime. The engine vision's older “Scripting: None” snapshot predates X3; use [SCRIPTING.md](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/SCRIPTING.md), [RESOURCES.md](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/RESOURCES.md), and [PREFABS.md](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/PREFABS.md) for the current contract. OAL's [runtime package contract](../../RUNTIME_PACKAGE.md) describes the compiler side.

## License boundary

Recast/Detour is [zlib licensed](https://github.com/recastnavigation/recastnavigation/blob/main/License.txt); BehaviorTree.CPP is [MIT licensed](https://github.com/BehaviorTree/BehaviorTree.CPP/blob/master/LICENSE), though its C++17 implementation is not an automatic fit for MegaMod's C runtime. Godot engine code is [MIT licensed](https://github.com/godotengine/godot/blob/master/COPYRIGHT.txt), with separate third-party notices; its [documentation has a different license](https://github.com/godotengine/godot-docs/blob/master/LICENSE.txt). Valve's [Source 1 SDK license](https://github.com/ValveSoftware/source-sdk-2013/blob/master/LICENSE) limits code use to specified Source game modifications. Treat Source as architecture evidence, not a code donor. Unreal documentation was used for comparison, not as a code source. Locally installed commercial game material remains outside the repository. No GOAP library was selected; review the exact license of any future candidate.
