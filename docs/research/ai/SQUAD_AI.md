# Squad coordination

**VERIFIED local example:** Natural Selection 2's installed `TeamBrain.lua` tracks team-known entities, alerts and assignments, while `PlayerBrain.lua` retains individual action/objective decisions. That establishes a practical separation between shared coordination and per-agent execution; it does not validate any specific NS2 strategy for MegaMod.

For MegaMod, a squad service might publish a group goal, last reported target, assigned roles and short leases on cover or interactables. An agent still owns its path and action outcome. Leader-based commands are simple for scripted encounters but create a single failure point; leaderless bidding is flexible but needs deterministic tie breaking and bounded updates. Start with explicit ordered assignments (stable agent ID as tie break) before adding auctions. Communication should be a host event with range/latency/team rules if gameplay requires it; shared memory must not silently grant exact knowledge of unseen enemies.

Useful first coordination fixture: two guards hear one event; one investigates, one holds a doorway; assignments expire if an agent dies or path fails. Keep this later than basic agents. Render squad goal, member role, reservation owner and expiry in debug tools.
