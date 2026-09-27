-- x6:script/lockdown (original, Open Asset Lab test content)
-- The X6 world's own script: its lockdown button toggles ONE prefab
-- instance's door. A child of an instance is an ordinary placed entity,
-- named <instance>__<child>, so world.entity finds it like any other.
local south = world.entity('x6:entity/south_door__door')

function on_used(button, player)
  world.send(south, 'toggle', player)
  log('lockdown toggles', tostring(south), 'which was', world.state(south))
end
