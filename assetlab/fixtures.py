"""Original test worlds, built in code (assetlab.world). No third-party
content: every box, colour and entity here is ours.

x1_event_lab -- MegaMod's X1 world-event slice. Two rooms split by a wall
with a doorway. The west room has the starts, a button on the wall, and a
raised platform with a teleport destination on it. The doorway is closed by
a sliding door; the east room has a trigger pad.

    button_main --used/activate--> relay_main --fired/open--> door_main
    teleport_trigger --entered/teleport--> teleport_destination

Runtime units: +Z up, 1 wu per unit; the floor's top is z = 0.

    y
    ^   west room                 | east room
    |   [platform + destination]  |
    |                             D (door, slides +y into the wall)
    |   starts      button ->     |        [trigger pad]
    +-----------------------------+----------------------> x
   -5                             0                      5
"""
from __future__ import annotations

from .world import Box, Entity, Link, OriginalWorld

NS = 'x1'


def eid(name):
    return f'{NS}:entity/{name}'


MATERIALS = {
    'floor': (150, 150, 145),
    'wall': (200, 196, 186),
    'door': (220, 120, 40),
    'button': (200, 40, 40),
    'platform': (70, 110, 190),
    'trigger_pad': (60, 190, 90),
    'destination_pad': (160, 80, 200),
}

BUTTON = (-0.14, -1.3, 0.55)
DESTINATION = (-4.25, 2.4, 0.4)
TRIGGER = ((2.5, -0.5, -0.1), (3.5, 0.5, 1.2))
DOOR_MOVE = (0.0, 1.25, 0.0)


def x1_event_lab():
    H = 1.6                                            # wall height
    boxes = [
        Box((-5, -3, -0.2), (5, 3, 0), 'floor'),
        Box((-5.2, 3, -0.2), (5.2, 3.2, H), 'wall'),     # north
        Box((-5.2, -3.2, -0.2), (5.2, -3, H), 'wall'),   # south
        Box((-5.2, -3, -0.2), (-5, 3, H), 'wall'),       # west
        Box((5, -3, -0.2), (5.2, 3, H), 'wall'),         # east
        # The dividing wall, its doorway 1.2 wide and 1.1 high.
        Box((-0.1, -3, 0), (0.1, -0.6, H), 'wall'),
        Box((-0.1, 0.6, 0), (0.1, 3, H), 'wall'),
        Box((-0.1, -0.6, 1.1), (0.1, 0.6, H), 'wall'),
        # The door fills the doorway and slides into the north segment.
        Box((-0.05, -0.6, 0), (0.05, 0.6, 1.1), 'door', owner=eid('door_main')),
        # The button, on the dividing wall's west face.
        Box((-0.18, -1.5, 0.45), (-0.1, -1.1, 0.65), 'button'),
        # The platform the destination stands on, and two floor marks.
        Box((-5, 1.8, 0), (-3.5, 3, 0.4), 'platform'),
        Box((-4.5, 2.15, 0.4), (-4.0, 2.65, 0.42), 'destination_pad', solid=False),
        Box((TRIGGER[0][0], TRIGGER[0][1], 0), (TRIGGER[1][0], TRIGGER[1][1], 0.02), 'trigger_pad', solid=False),
    ]
    entities = [
        Entity(eid('button_main'), 'interactable', position=BUTTON, reach=1.0,
               links=[Link('used', eid('relay_main'), 'activate')]),
        Entity(eid('relay_main'), 'relay', links=[Link('fired', eid('door_main'), 'open')]),
        Entity(eid('door_main'), 'mover', move=DOOR_MOVE, speed=1.0),
        Entity(eid('teleport_trigger'), 'trigger', bounds=TRIGGER,
               links=[Link('entered', eid('teleport_destination'), 'teleport')]),
        Entity(eid('teleport_destination'), 'teleport', position=DESTINATION, yaw_degrees=0.0),
    ]
    spawns = [
        {'position': [-3.5, -1.0, 0.0], 'yaw_degrees': 0.0, 'team': None},
        {'position': [-3.5, 0.5, 0.0], 'yaw_degrees': 0.0, 'team': None},
    ]
    return OriginalWorld(id=f'{NS}:world/event_lab', file_name='x1_event_lab',
                         display_name='X1 Event Lab', materials=dict(MATERIALS),
                         boxes=boxes, spawns=spawns, entities=entities)


FIXTURES = {'x1_event_lab': x1_event_lab}
