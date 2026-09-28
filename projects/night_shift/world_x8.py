"""Harrow Annex with the two security doors cut to fit X7 restored.

The original ``world01`` stays byte for byte fixed. This second package is
the X8 production proof: D2 guards the pump room and D5 the core chamber.
"""
from assetlab.bindings import Action, EventBinding
from assetlab.prefabs import PrefabInstance

import world01


def world():
    w = world01.world()
    w.id = 'nightshift:world/harrow_annex_x8'
    w.file_name = 'night_shift_x8'
    w.package = 'nightshift.world_x8'
    w.display_name = 'Night Shift: Harrow Annex (X8)'
    w.prefab_instances += [
        PrefabInstance('d2', world01.P('security_door'), (-9.0, 1.6, 0.0)),
        PrefabInstance('d5', world01.P('security_door'), (11.0, 16.0, 0.0), yaw_degrees=90.0),
    ]
    # Both doors use the facility prefab's own powered button bindings.
    # The existing power sources supply them without a script or a new kind.
    for b in w.bindings:
        if b.id == 'sec_live':
            b.actions.append(Action('activate', target=world01.child('d2', 'power')))
        elif b.id == 'sec_research':
            b.actions.append(Action('activate', target=world01.child('d5', 'power')))
        elif b.id == 'cool_research':
            b.actions.append(Action('activate', target=world01.child('d5', 'power')))
        elif b.id == 'lockdown_seal':
            b.actions.append(Action('deactivate', target=world01.child('d2', 'power')))
            b.actions.append(Action('deactivate', target=world01.child('d5', 'power')))
    return w
