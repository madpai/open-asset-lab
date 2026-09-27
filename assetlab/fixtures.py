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

from .scripts import Script, load_source
from .world import Box, Entity, Link, MoverDefinition, OriginalWorld

NS = 'x1'


def eid(name, ns=NS):
    return f'{ns}:entity/{name}'


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


# ---- x2_definition_lab ---------------------------------------------------
# x2_definition_lab -- MegaMod's X2 slice: ONE reusable mover definition,
# `x2:mover/basic_slide_door`, placed three times. Each door keeps its own
# state: opening A leaves B and C shut.
#
#     button_a --used/activate--> relay_a --fired/open--> door_a
#     button_b --used/activate--> relay_b --fired/open--> door_b
#     door_c: the same definition, nothing opens it
#     teleport_trigger --entered/teleport--> teleport_destination
#
#     y
#     ^  [platform + destination]  |          [trigger pad]
#     |                            C door_c (y 3)
#     |  start                     B door_b (y 0)   east room
#     |  start      button_b ->    |
#     |                            A door_a (y -3)
#     |             button_a ->    |
#     +----------------------------+-----------------------> x
#    -5                            0                       5
#
# Every door slides +y by 1.25 into the dividing wall at 1 wu/s.

X2 = 'x2'
X2_DOOR = f'{X2}:mover/basic_slide_door'
X2_DOORS = {'door_a': -3.0, 'door_b': 0.0, 'door_c': 3.0}      # doorway centres (y)
X2_BUTTONS = {'button_a': (-0.14, -4.2, 0.55), 'button_b': (-0.14, -1.3, 0.55)}
X2_TRIGGER = ((2.5, 3.2, -0.1), (3.5, 4.2, 1.2))
X2_DESTINATION = (-4.25, 4.1, 0.4)


def x2_definition_lab():
    H, W = 1.6, 0.6                                    # wall height; half a doorway's width
    e = lambda name: eid(name, X2)
    boxes = [
        Box((-5, -5, -0.2), (5, 5, 0), 'floor'),
        Box((-5.2, 5, -0.2), (5.2, 5.2, H), 'wall'),     # north
        Box((-5.2, -5.2, -0.2), (5.2, -5, H), 'wall'),   # south
        Box((-5.2, -5, -0.2), (-5, 5, H), 'wall'),       # west
        Box((5, -5, -0.2), (5.2, 5, H), 'wall'),         # east
    ]
    # The dividing wall at x = 0: solid between the three doorways, each
    # 1.2 wide and 1.1 high with a lintel above.
    ys = sorted(X2_DOORS.values())
    edges = [-5.0] + [v for y in ys for v in (y - W, y + W)] + [5.0]
    for lo, hi in zip(edges[0::2], edges[1::2]):
        boxes.append(Box((-0.1, lo, 0), (0.1, hi, H), 'wall'))
    for y in ys:
        boxes.append(Box((-0.1, y - W, 1.1), (0.1, y + W, H), 'wall'))
    for name, (x, y, z) in X2_BUTTONS.items():
        boxes.append(Box((-0.18, y - 0.2, z - 0.1), (-0.1, y + 0.2, z + 0.1), 'button'))
    boxes += [
        Box((-5, 3.3, 0), (-3.5, 5, 0.4), 'platform'),
        Box((-4.5, 3.85, 0.4), (-4.0, 4.35, 0.42), 'destination_pad', solid=False),
        Box((X2_TRIGGER[0][0], X2_TRIGGER[0][1], 0), (X2_TRIGGER[1][0], X2_TRIGGER[1][1], 0.02), 'trigger_pad', solid=False),
    ]
    definitions = [MoverDefinition(X2_DOOR, size=(0.1, 1.2, 1.1), move=(0.0, 1.25, 0.0), speed=1.0, material='door')]
    entities = [
        Entity(e('button_a'), 'interactable', position=X2_BUTTONS['button_a'], reach=1.0,
               links=[Link('used', e('relay_a'), 'activate')]),
        Entity(e('relay_a'), 'relay', links=[Link('fired', e('door_a'), 'open')]),
        Entity(e('door_a'), 'mover', definition=X2_DOOR, position=(0.0, X2_DOORS['door_a'], 0.55)),
        Entity(e('button_b'), 'interactable', position=X2_BUTTONS['button_b'], reach=1.0,
               links=[Link('used', e('relay_b'), 'activate')]),
        Entity(e('relay_b'), 'relay', links=[Link('fired', e('door_b'), 'open')]),
        Entity(e('door_b'), 'mover', definition=X2_DOOR, position=(0.0, X2_DOORS['door_b'], 0.55)),
        Entity(e('door_c'), 'mover', definition=X2_DOOR, position=(0.0, X2_DOORS['door_c'], 0.55)),
        Entity(e('teleport_trigger'), 'trigger', bounds=X2_TRIGGER,
               links=[Link('entered', e('teleport_destination'), 'teleport')]),
        Entity(e('teleport_destination'), 'teleport', position=X2_DESTINATION, yaw_degrees=0.0),
    ]
    spawns = [
        {'position': [-3.5, -3.0, 0.0], 'yaw_degrees': 0.0, 'team': None},
        {'position': [-3.5, 0.0, 0.0], 'yaw_degrees': 0.0, 'team': None},
    ]
    return OriginalWorld(id=f'{X2}:world/definition_lab', file_name='x2_definition_lab',
                         display_name='X2 Definition Lab', materials=dict(MATERIALS),
                         boxes=boxes, spawns=spawns, entities=entities, mover_definitions=definitions)


# ---- x3_script_lab ---------------------------------------------------------
# x3_script_lab -- MegaMod's X3 slice: host-side Lua. The X2 room in the x3
# namespace, with two changes:
#
#   button_script (where X2's button A was, purple) has NO links; it names
#   x3:script/button_logic, whose on_used asks the engine to open door_a.
#   Without the script, door_a never opens.
#
#   The world's ability_script is x3:script/pulse_ability: a player with no
#   native ability pressing ability damages players within 2.5 wu through
#   the engine's own damage.
#
# button_b -> relay_b -> door_b and trigger -> teleport stay authored links
# (X1/X2 composition next to the scripts); door_c stays shut. The scripts
# are original files in assetlab/data/scripts/x3/.

X3 = 'x3'
X3_DOOR = f'{X3}:mover/basic_slide_door'


def x3_script_lab():
    w = x2_definition_lab()
    ren = lambda s: s.replace(f'{X2}:', f'{X3}:', 1) if isinstance(s, str) else s
    w.id, w.file_name, w.display_name = f'{X3}:world/script_lab', 'x3_script_lab', 'X3 Script Lab'
    for d in w.mover_definitions:
        d.id = ren(d.id)
    entities = []
    for e in w.entities:
        e.id, e.definition = ren(e.id), ren(e.definition)
        for ln in e.links:
            ln.target = ren(ln.target)
        if e.id == eid('relay_a', X3):
            continue                                   # the script replaces button A's chain
        if e.id == eid('button_a', X3):
            e.id, e.links, e.script = eid('button_script', X3), [], f'{X3}:script/button_logic'
        entities.append(e)
    w.entities = entities
    w.materials['script_button'] = (150, 60, 210)
    x, y, z = X2_BUTTONS['button_a']
    for b in w.boxes:
        if b.material == 'button' and b.min[1] < y < b.max[1]:
            b.material = 'script_button'
    w.scripts = [
        Script(f'{X3}:script/button_logic', load_source('x3/button_logic.lua'), ['on_used']),
        Script(f'{X3}:script/pulse_ability', load_source('x3/pulse_ability.lua'), ['on_ability']),
    ]
    w.ability_script = f'{X3}:script/pulse_ability'
    return w


FIXTURES = {'x1_event_lab': x1_event_lab, 'x2_definition_lab': x2_definition_lab, 'x3_script_lab': x3_script_lab}
