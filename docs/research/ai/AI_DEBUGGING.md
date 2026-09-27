# AI debugging as creator tooling

**VERIFIED precedents:** [Recast DebugUtils](https://recastnav.com/DetourDebugDraw_8h.html) draws navmesh tiles, off-mesh links and query nodes. [BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP) logs node transitions. Natural Selection 2's installed `PlayerBrain.lua` writes action and goal weights into a bot debug manager, while `BotMotion.lua` exposes path and stuck handling. These are stronger evidence for *observable reasons* than for any particular decision algorithm.

## Proposed inspector record

For one selected agent, show stable ID/archetype, host tick, current goal and selected reason, active action and elapsed time, target handle, last seen/heard facts with age and provenance, path status/corridor/corners, last failure, and recent event history. For utility show every score's inputs and curve outputs. For a BT show active path and abort reason. For GOAP show plan, rejected preconditions and search budget. Draw vision cone, LOS ray and blocker, hearing radius, navmesh islands/links, path and cover candidates with rejection colors.

Make a bounded host ring buffer of structured events such as `stimulus`, `goal_selected`, `action_started`, `path_failed`, `action_cancelled`, `world_input_rejected`; records carry tick, agent and reason code. Expose through the existing desktop/headless diagnostic channel and an OAL preview where feasible. Keep private memory out of normal gameplay replication. Debug collection must be switchable, rate-limited and cheap when disabled. A creator should be able to answer “why did guard_03 stop at this door?” from one trace and one overlay.

**Acceptance:** synthetic failure fixtures must show the *failed precondition or blocker*, not only “no path.” Save a small sanitized trace for regression tests; never require a proprietary map to exercise the viewer.
