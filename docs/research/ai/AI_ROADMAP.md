# Research-based AI roadmap

This is a candidate plan for a future implementation owner, **not** authorization to start AI in this research session. The sequence preserves X7 as the common world action seam and the current grid/bot behavior until a measured replacement earns its place.

## Gate 0: contracts after X7

Read the landed X7 executor, update `MEGAMOD_AI_ARCHITECTURE.md` against actual action names and failure behavior, and create one original two-room fixture: a button opens a door, a trigger reports entry, a patrol point sits beyond it. Confirm whether an agent can request exactly the same world action as player, script and declarative X7 graph. Resolve actor handle, reach, cooldown, cancellation and link gating before selecting a behavior formalism.

## Candidate first AI milestone: Navigation + basic agents

**Smallest useful proof:** one OAL-baked navmesh for an original world and one host agent that patrols, observes sight/noise, remembers one last position, investigates and chases. It uses normal movement/input and world interaction paths, reports path/action failure, and replicates transform plus animation intent/state to a joiner. Android hosts the same fixture; late join sees current NPC and door state. If navmesh integration would make the first slice too broad, split it into (A) offline bake/package/query diagnostic and (B) basic agent using the existing grid behind a navigation interface, then connect them. This split should be chosen by benchmark and test evidence, not preference.

**Acceptance evidence:** deterministic OAL output for identical input; runtime rejects mismatched/corrupt nav resource; two radii expose a narrow-door difference; closed/open door link changes route; unreachable target produces reason; sight respects FOV/LOS; noise has uncertain position and expiry; action uses general engine validator; host damage and kill credit remain native; joiner does not think; late join current state works; low-end Android tick and bandwidth counters are recorded. Compare legacy grid and candidate mesh on one imported map without changing the imported-map fallback.

## Later, only on evidence

1. Utility goal scoring when continuous priorities create awkward rules. Require score breakdown and hysteresis tests.
2. Reusable behavior trees when repeated branches and creator authoring justify a serializable graph. Define abort/cancel before editor work.
3. Semantic interactables, authored traversal, then cover/position reservations and squad memory when a two-agent fixture proves a need.
4. GOAP only for a world with several changing object/action dependencies where authored chains become costly. Bound search and show failed preconditions.
5. Crowd/avoidance and AI LOD only after Android profiles show a problem; 3D/flying navigation requires a separate movement model.

## Research questions still open

- Does a packaged Detour tile load identically on supported architectures and versions, or should OAL serialize a more portable intermediate form?
- What does X7 actually expose for async actions, failure and cancellation?
- Can the existing bot input record serve agent movement without new network packet types?
- Which source-world entities can OAL translate into validated generic affordances without guessing?
- What are the measured per-agent CPU and wire costs on the target Android host?

The [local observations](LOCAL_GAME_REVERSE_ENGINEERING.md) and the cited source documents are evidence, while this ordering remains a proposal.
