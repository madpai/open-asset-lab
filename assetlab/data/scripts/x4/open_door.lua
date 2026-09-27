-- x4:script/open_door (original, Open Asset Lab test content)
-- The X4 world's own script: the scripted button asks the engine to open
-- door A. The button has no link of its own: without this script, door A
-- never moves. (X3's button_logic, in the x4 namespace.)
local door = world.entity('x4:entity/door_a')
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
