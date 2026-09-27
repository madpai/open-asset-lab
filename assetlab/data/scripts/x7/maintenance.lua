-- x7:script/maintenance (original, Open Asset Lab test content)
-- Custom logic that does not belong in data: the maintenance button
-- counts its presses and, on every second one, opens north_door's door
-- directly -- whatever the door's power says. The door's own bindings
-- (its chime on opened) answer the state change like any other.
local door = world.entity('x7:entity/north_door__door')
local presses = 0

function on_used(button, player)
  presses = presses + 1
  log('maintenance press', presses)
  if presses % 2 == 0 then
    world.send(door, 'open', player)
    log('maintenance override opens', tostring(door), 'which was', world.state(door))
  end
end
