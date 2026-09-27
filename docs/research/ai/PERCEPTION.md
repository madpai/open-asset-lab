# Perception is evidence gathering

**VERIFIED local comparison:** Natural Selection 2's readable `ns2/lua/bots/BrainSenses.lua` evaluates named senses lazily and caches values for a frame. Its `TeamBrain.lua` tracks known entities and sound-related memory. This supports separating *measurement* from decisions; it does not prove MegaMod should copy NS2's timing or Lua structure.

## Proposed host sensor flow

1. Broadphase nearby actors using a spatial index or existing collision query. Filter invalid/dead entities and declared faction/relationship before expensive tests.
2. For sight, test range, horizontal/vertical field of view, then line of sight from eye or muzzle points. Record observation position, host tick, target handle and confidence. Visibility is not permission to shoot: combat checks its own muzzle obstruction and rules.
3. For hearing, consume bounded *gameplay sound events* with origin, radius/intensity, type and source if known. Do not infer hearing from client audio playback. Occlusion may be coarse initially. Damage awareness is an event and may identify an attacker only when the damage system can honestly identify one.
4. Update memory; emit a reasoned stimulus such as `saw_enemy`, `heard_unknown_noise`, `took_damage`. Decision ticks consume these facts at a lower frequency.

**Design bounds:** sight and hearing should have separate sampling rates and budgets; stagger agents by stable ID to avoid a single expensive frame. Immediate damage events can wake a sleeping agent. Never expose hidden players to AI through global entity lists merely because they are networked. A hearing event locates a sound, not an exact target position unless game rules explicitly say so. Teams/factions need an explicit relationship matrix; a team ID alone cannot express neutral, allied, hostile and scripted exceptions.

**Debugging contract:** for any target show the last test time, FOV result, LOS blocker, range result and resulting memory update. The point is to explain *why* an NPC saw or did not see someone. Use original synthetic rooms with walls, glass, a door and noise for validation.
