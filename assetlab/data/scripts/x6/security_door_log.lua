-- x6:script/security_door_log (original, Open Asset Lab test content)
-- The security door prefab's button script, provided by the x6.facility
-- library beside the prefab. It is ordinary megamod.v1: on_used receives
-- the INSTANTIATED button -- north_door's or south_door's, never "the
-- prefab" -- and the player. The button's own link (used -> its sibling
-- door, toggle) moves the door; this only says which instance was pressed.
local uses = 0

function on_used(button, player)
  uses = uses + 1
  log('security door button', tostring(button), 'use', uses, 'by', tostring(player))
end
