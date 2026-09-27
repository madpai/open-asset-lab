# Proposed MegaMod agent architecture

**Status: proposal only.** Baseline: MegaMod Engine/Showdown `2eae9df`, OAL `c420f2a`, fetched 2026-09-27. Recheck X7 before implementing an action seam. X3 host-only Lua, X4 typed identities/imports, X5 asset resources and X6 load-expanded prefabs are implemented. The existing `brain.c` bot uses player-like input, LOS, last-seen position and `nav.c`'s multi-layer collision grid. That grid has A*, precomputed fields, smoothing, prop blocking and keyed disk caching; it must be treated as a real existing system, not a placeholder. See [MegaMod's nav and brain headers](https://github.com/madpai/megamod-showdown/tree/2eae9df/src/game) and current [resource contract](https://github.com/madpai/megamod-showdown/blob/2eae9df/docs/RESOURCES.md).

## Layers and contracts

| Layer | Input | Output | Owner |
|---|---|---|---|
| navigation | walkable data, profile, current/goal positions, link state | corridor/corners or failure reason | host |
| perception | spatial candidates, LOS, gameplay sounds, damage | timestamped observations | host |
| memory | observations, expiry rules | bounded known facts and uncertainty | host |
| decision | facts, goals, action outcomes | goal and task request | host |
| action execution | task request, resolved target, actor handle | running/success/failure through normal engine systems | host |
| animation/presentation | transform and compact action intent | pose, sound and FX | client and host renderer |
| networking | authoritative durable state and events | snapshots and corrections | host publishes, client consumes |
| debugging | reason codes, bounded trace | inspector and overlays | host trace, OAL/runtime view |

The agent is an ordinary authoritative game actor with a bounded AI controller. A prefab may compose an agent placement and its surroundings later, but prefab expansion remains load-time composition. Nothing here requires a prefab runtime. Agent logic should not live in a game-specific unit subclass or in a client Lua VM.

## Twelve implementation decisions to test

1. **OAL offline:** normalize collision geometry, author/check semantic traversal links, bake and validate navmeshes for actual agent profiles, preview islands/reachability/links, compile versioned data with provenance and world key inclusion. OAL may suggest affordances from imported content but must label inferences and reject unresolved actions.
2. **Future package content:** one world-referenced navmesh per necessary profile, a small agent descriptor, optional authored patrol points and semantic interaction/cover candidates. `namespace:navmesh/name` and `namespace:agent/name` are candidate IDs only. Keep package identity distinct from resource identity; use X4 dependency visibility and load-time resolution. Split `perception`, `navagent` or `behavior` into reusable resources only when at least two real agents share them and independent versioning/authoring helps more than it costs.
3. **Host owns:** agent lifecycle, sensors, memory, decision, path queries, world action requests, combat and durable state. Prefer using existing player-like movement/input and damage paths where semantics match; do not create an NPC-only teleport or damage route.
4. **Client owns:** interpolation, pose selection, audio/FX and local debug visualization of authorized traces. No client decision logic is required for correctness.
5. **Navigation:** keep `nav.c` for legacy worlds while comparing Recast/Detour on a synthetic world. Offline bake versus runtime grid should be benchmarked on Android. Host queries route, steers and validates dynamic link state; closed doors and lifts need action-aware transitions. Use a versioned portable wrapper if Detour tile payloads are packaged.
6. **Perception:** spatial filter → range/FOV → LOS; bounded gameplay sound events and damage stimuli; explicit faction relationships. Stagger costly tests and retain reasons for rejected sightings.
7. **Memory:** fixed typed facts with source, time, uncertainty and generation-safe handles. Separate current visibility from last-known position. Shared squad facts require deliberate communication.
8. **First decision model:** a tiny explicit state/task chooser for patrol, investigate and chase, with action completion/failure and limited interrupt rules. This proves the seams. Utility scoring can later choose among goals; BTs can later orchestrate reusable branches; GOAP only after multiple systemic action chains justify search. No single model needs to own everything.
9. **X7 connection:** route AI `use/open/activate` into the same validated general action path that X7 graphs and user interactions use. A path only gets an NPC into range; it does not open the door. The action executor reports accepted/running/completed/rejected and sends actor identity through the existing event machinery. X7's actual landed API is the contract, not the hypothetical names here.
10. **Scripts:** host Lua may issue bounded high-level orders or customize decisions after a concrete need arises; it should call the same action seam, never directly mutate nav, health, mover position or network state. Current X3 API stays as-is until such a use case is designed and versioned.
11. **Mandatory debugging:** selectable agent inspector; navmesh/path/link overlays; sensor test reasons; last-seen/heard provenance; current goal/action and failure; event history. Decision-model-specific traces (scores, active BT path, plan) arrive with that model. OAL preview must show offline bake warnings and mismatched links.
12. **Defer from first milestone:** general BT/GOAP runtimes, nested agents in prefab runtime, crowd simulation, generated cover, squad bidding, advanced 3D flight, full animation graph authoring, scripting API expansion and broad network protocol redesign. Add only what the first vertical slice can prove.

## Candidate resources and ownership

| Candidate | Proposed content | Why separate only later |
|---|---|---|
| `facility:navmesh/main` | world-space polygons/tiles, profile and links | Can be built/validated offline and shared by agents in one world. |
| `facility:agent/guard` | body/character reference, nav/perception parameters, faction, decision config, action set | A reusable archetype independent of placement. `agent` is clearer than `npc` if non-humanoids or bots use it. |
| `facility:behavior/guard` | decision graph if authoring reuse emerges | Avoid type proliferation for a three-state first agent. |
| `facility:perception/humanoid` | sight/hearing profile | Split only if several agents genuinely share and edit it. |
| `facility:navagent/humanoid` | radius, height, slope/climb and movement limits | Reuse may be useful, but must match baked profile. |

**Action and animation contract:** an action has target (if any), start, progress, cancel and result. The host may publish a compact action/locomotion intent; the client chooses local poses. For a hit, the combat pipeline and host snapshot decide damage, while animation conveys the result. Scripted interactions can temporarily claim control with an explicit release/failure path. See [affordances](ENTITY_IO_AND_AFFORDANCES.md) and [multiplayer](MULTIPLAYER_AUTHORITATIVE_AI.md).

## Explicitly avoid

Avoid treating collision triangles as semantic doors, treating a navmesh edge as a completed traversal, trusting client AI, replicating full blackboards, running every planner each frame, naming foreign classes in generic packages, looking resource IDs up every tick, silently inferring affordances, making BT or GOAP universal, and copying Source SDK or local commercial-game code. Each is a concrete failure mode exposed by the evidence in this corpus.
