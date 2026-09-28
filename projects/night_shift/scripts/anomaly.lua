-- nightshift:script/anomaly -- the research wing's cold spot.
--
-- A binding `use`s the hidden hook entity whenever someone walks into the
-- cold spot (cold_spot entered -> use cold_spot_hook); the engine then calls
-- this on_used with that player. What happens depends on something X7
-- cannot read: how many OTHER players stand near the one who walked in.
--
--   in company  the first time only: it stirs (a sound), nothing else
--   alone       it takes them -- to the holding cell -- at most twice a round
--
-- Deterministic: no randomness (the sandbox has none), no clock.
local cell = world.entity('nightshift:entity/holding_cell')
local stir = world.entity('nightshift:entity/anomaly')
local visits, taken = 0, 0

function on_used(entity, player)
  visits = visits + 1
  local company = #game.near(player, 5.0)
  if company > 0 then
    if visits == 1 then world.send(stir, 'activate', player) end
    log('cold spot: ' .. company .. ' nearby, it keeps its distance')
    return
  end
  if taken >= 2 then
    log('cold spot: alone, but it has had its fill')
    return
  end
  taken = taken + 1
  log('cold spot: alone -- taken to the holding cell (' .. taken .. ')')
  world.send(stir, 'activate', player)
  world.send(cell, 'teleport', player)
end
