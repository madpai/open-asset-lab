-- x3:script/button_logic (original, Open Asset Lab test content)
-- The scripted button decides; the engine opens. The button has no link
-- of its own: without this script, door A never moves.
local door = world.entity('x3:entity/door_a')
local presses = 0

function on_used(button, player)
  presses = presses + 1
  local state = world.state(door)
  if state == 'closed' then
    world.send(door, 'open', player)
    log('press', presses, 'by', tostring(player), 'asks', tostring(door), 'to open')
  else
    log('press', presses, 'by', tostring(player), 'leaves', tostring(door), state)
  end
end
