-- x3:script/pulse_ability (original, Open Asset Lab test content)
-- A short-range pulse. The script picks the targets; the engine does the
-- damage (shields, health, protection, death, credit and score are its).
local RADIUS = 2.5    -- wu
local DAMAGE = 150

function on_ability(player)
  local hit = 0
  for _, target in ipairs(game.near(player, RADIUS)) do
    game.damage(target, DAMAGE, player)
    hit = hit + 1
  end
  log('pulse by', tostring(player), 'hit', hit)
end
