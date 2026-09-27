# Cover and tactical positions

Cover is a relation among an agent, threat, stance and obstacle. A point behind geometry is not automatically good cover: it may be unreachable, too exposed from another angle, block allies, lack line of fire or sit inside a hazard. Use cover *candidates* with explicit threat-facing, stance, quality and validity; score them at decision time.

**Proposed sources:** creator-authored cover anchors, OAL-generated candidates at suitable collision/navmesh boundaries, or a hybrid. A generated edge point is only a candidate until ray tests confirm protection at expected eye/chest heights. OAL can precompute static geometry geometry and preview it; the host must recheck dynamic movers, current threats and occupation. Candidate identity should survive package compilation without depending on Detour polygon references. Reserve a position with a short lease and release on death, goal change or path failure.

**First AI milestone:** omit cover. The initial proof needs to distinguish reachable from blocked and visible from hidden. Add cover when the combat fixture can test at least two threats, a moving door, several agents and reservation conflicts. Debug view should show rejected candidates and scores, not just the chosen one.
