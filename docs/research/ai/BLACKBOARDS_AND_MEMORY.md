# Blackboard and AI memory

A blackboard is a typed exchange between sensors, decisions and action execution. Memory is a subset with time and uncertainty. **Recommendation:** begin with an explicit fixed schema in host state, not an unbounded bag of strings.

| Fact | Minimum fields | Expiry / correction |
|---|---|---|
| visible target | generation-checked handle, observed position, tick, LOS | clear visibility promptly; retain a separate last-seen record |
| last seen target | handle if valid, position, time, confidence | confidence decays; invalid handle cannot point to a new occupant |
| sound | position, type, tick, uncertainty radius | short expiry; no invented precise source identity |
| threat | source, strength, last damage tick | decay and bound count |
| current goal/action | ID, selected tick, progress, failure | explicit completion or interruption |
| path | goal position, corridor revision, next corner | invalidate on world/link/profile change |

**VERIFIED local comparison:** Natural Selection 2's installed `TeamBrain.lua` contains known-entity, alert and threat tracking with assignments, while `PlayerBrain.lua` validates active goal actions. This suggests a useful *per-agent/private versus squad/shared* split. It does not prove the original game has perfect information safeguards. MegaMod should permit sharing only observations or deliberate alerts; copying every private fact into a squad board creates instant omniscience.

**Representation:** store host ticks or simulation time, provenance (`seen`, `heard`, `damage`, `teammate_report`) and an uncertainty radius. Keep stable content IDs for authored targets, generation-checked handles for live instances. A dead or despawned target invalidates its handle; a last position may remain as historical information. Bound entries and expire deterministically. For late join, only gameplay-visible consequences need replication; the host blackboard stays private unless a deliberate debug channel is active.

**First milestone:** one current target, one last seen position, one last noise, current goal and failure reason. Add shared squad memory only after a concrete coordination fixture needs it.
