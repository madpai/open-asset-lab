"""nightshift.facility -- Night Shift's reusable prefab library. Authored once
here, placed by the world (and by any later Night Shift world). Behaviour
that belongs to the object is its own bindings; how objects are wired to
each other (which power feeds which door) is the world's.

Prefab space: +z up, the floor at z = 0. A wall-mounted prefab stands in
the plane x = 0 with its FRONT toward -x (a player at negative x faces it);
turn the instance to face another way. Wall thickness assumed: 0.2 wu
(x in -0.1..0.1).

  security_door   6 entities  a powered sliding door, a button on both faces
                              of the wall, a through-wall button plate, its
                              own power relay and a green lamp that drops
                              out of the lintel while it has power
  breaker_panel   2           a lever and its box (a wall breaker)
  console         2           a desk terminal
  valve           2           a wall valve wheel
  status_lamp     1           a green lamp that slides out of the wall
  ceiling_light   1           a strip light that drops out of the ceiling
  alarm_light     1           a red beacon strip that drops out of the ceiling
  shutter         1           a heavy sliding shutter (grinds)
  data_core       2           the core and its socket; used -> it unlatches
  steam_vent      2           a plume in the ceiling and the scald zone under it
  pump            1           a piston that thumps and returns (the world restarts it)
"""
from __future__ import annotations

from assetlab import prefabs as prefablib
from assetlab.bindings import Action, Condition, EventBinding
from assetlab.dependencies import Library
from assetlab.resources import Requirement

import art

PACKAGE = 'nightshift.facility'
C = prefablib.PrefabChild
M = art.model_id
S = art.sound_id


def pid(name):
    return f'{art.NS}:prefab/{name}'


def prov(what):
    return dict(art.ORIGIN, made_by=f'projects/night_shift/facility.py:{what}')


def security_door():
    """IF power: either button toggles the door. ELSE: either button buzzes.
    The world feeds `power` (activate/deactivate); the door never decides."""
    return prefablib.Prefab(pid('security_door'), [
        C('door', 'mover', position=(0.0, 0.0, 0.6), size=(0.1, 1.2, 1.2), move=(0.0, 1.3, 0.0), speed=1.4,
          sound=S('door_servo'), model=M('door_panel')),
        C('button', 'interactable', position=(-0.16, -0.78, 0.85), reach=1.2),
        C('button_back', 'interactable', position=(0.16, -0.78, 0.85), reach=1.2),
        C('plate', 'prop', position=(0.0, -0.78, 0.85), model=M('door_button')),
        C('power', 'relay'),
        C('lamp', 'mover', position=(0.0, 0.0, 1.26), size=(0.16, 1.0, 0.08), move=(0.0, 0.0, -0.1), speed=0.5,
          model=M('door_lamp')),
    ], provenance=prov('security_door'), bindings=[
        EventBinding('locked', 'button', 'used', [Condition('relay_state', 'power', 'inactive')],
                     [Action('play_sound', sound=S('locked'), at='plate')]),
        EventBinding('locked_back', 'button_back', 'used', [Condition('relay_state', 'power', 'inactive')],
                     [Action('play_sound', sound=S('locked'), at='plate')]),
        EventBinding('powered', 'power', 'activated', [],
                     [Action('open', target='lamp'), Action('play_sound', sound=S('power_on'), at='plate')]),
        EventBinding('toggle', 'button', 'used', [Condition('relay_state', 'power', 'active')],
                     [Action('toggle', target='door')]),
        EventBinding('toggle_back', 'button_back', 'used', [Condition('relay_state', 'power', 'active')],
                     [Action('toggle', target='door')]),
        EventBinding('unpowered', 'power', 'deactivated', [],
                     [Action('close', target='lamp'), Action('close', target='door'),
                      Action('play_sound', sound=S('power_down'), at='plate')]),
    ])


def breaker_panel():
    return prefablib.Prefab(pid('breaker_panel'), [
        C('lever', 'interactable', position=(-0.14, 0.0, 0.8), reach=1.2),
        C('box', 'prop', position=(-0.06, 0.0, 0.8), model=M('breaker_box')),
    ], provenance=prov('breaker_panel'), bindings=[
        EventBinding('clunk', 'lever', 'used', [], [Action('play_sound', sound=S('click'), at='box')]),
    ])


def console():
    """A freestanding desk; its front (the screen) toward -x."""
    return prefablib.Prefab(pid('console'), [
        C('terminal', 'interactable', position=(-0.4, 0.0, 0.6), reach=1.2),
        C('desk', 'prop', position=(0.0, 0.0, 0.36), model=M('console_desk')),
    ], provenance=prov('console'), bindings=[
        EventBinding('beep', 'terminal', 'used', [], [Action('play_sound', sound=S('click'), at='desk')]),
    ])


def valve():
    return prefablib.Prefab(pid('valve'), [
        C('wheel', 'interactable', position=(-0.14, 0.0, 0.75), reach=1.2),
        C('body', 'prop', position=(-0.07, 0.0, 0.75), model=M('valve_wheel')),
    ], provenance=prov('valve'), bindings=[
        EventBinding('turn', 'wheel', 'used', [], [Action('play_sound', sound=S('click'), at='body')]),
    ])


def status_lamp():
    """Recessed in a 0.2 wu wall (hidden); `open` slides it out of the front."""
    return prefablib.Prefab(pid('status_lamp'), [
        C('lamp', 'mover', position=(0.02, 0.0, 0.0), size=(0.08, 0.18, 0.14), move=(-0.1, 0.0, 0.0), speed=0.4,
          model=M('status_lamp')),
    ], provenance=prov('status_lamp'))


def ceiling_light():
    """Hidden in a ceiling slab at least 0.1 thick above z = 0; `open` drops it."""
    return prefablib.Prefab(pid('ceiling_light'), [
        C('light', 'mover', position=(0.0, 0.0, 0.04), size=(1.4, 0.14, 0.06), move=(0.0, 0.0, -0.08), speed=0.3,
          model=M('ceiling_light')),
    ], provenance=prov('ceiling_light'))


def alarm_light():
    return prefablib.Prefab(pid('alarm_light'), [
        C('light', 'mover', position=(0.0, 0.0, 0.05), size=(1.0, 0.16, 0.08), move=(0.0, 0.0, -0.1), speed=0.6,
          model=M('alarm_light')),
    ], provenance=prov('alarm_light'))


def shutter():
    """A doorway closed by a shutter that grinds sideways into the wall (+y)."""
    return prefablib.Prefab(pid('shutter'), [
        C('shutter', 'mover', position=(0.0, 0.0, 0.6), size=(0.1, 1.2, 1.2), move=(0.0, 1.3, 0.0), speed=0.45,
          sound=S('door_servo'), model=M('shutter')),
    ], provenance=prov('shutter'))


def data_core():
    """The core sits in a pedestal whose top is at z = 0.9. Used while seated:
    it unlatches and rises (slowly: its `opened` comes ~1.7 s later -- the
    world hangs the escalation on that)."""
    return prefablib.Prefab(pid('data_core'), [
        C('core', 'mover', position=(0.0, 0.0, 1.05), size=(0.28, 0.28, 0.6), move=(0.0, 0.0, 0.5), speed=0.3,
          model=M('data_core')),
        C('socket', 'interactable', position=(0.0, 0.0, 1.0), reach=1.4),
    ], provenance=prov('data_core'), bindings=[
        EventBinding('unlatch', 'socket', 'used', [Condition('mover_state', 'core', 'closed')],
                     [Action('open', target='core'), Action('play_sound', sound=S('core_release'), at='core')]),
    ])


def steam_vent():
    """The plume hides in a ceiling slab (its bottom at z = 1.4, the slab at
    least 0.6 thick) and drops to 0.85 -- above a 0.7 wu body, since movers
    never push or stop on players. The world tells `plume` to open; it
    closes itself. Walking into the zone while the plume is out scalds.
    Conditions have no OR: one binding per scalding phase."""
    scald = [Action('damage', amount=30.0), Action('play_sound', sound=S('steam'), at='zone')]
    return prefablib.Prefab(pid('steam_vent'), [
        C('plume', 'mover', position=(0.0, 0.0, 1.7), size=(0.9, 1.0, 0.6), move=(0.0, 0.0, -0.55), speed=1.1,
          model=M('steam_plume')),
        C('zone', 'trigger', bounds=((-0.55, -0.6, 0.0), (0.55, 0.6, 1.0))),
    ], provenance=prov('steam_vent'), bindings=[
        EventBinding('scald_closing', 'zone', 'entered', [Condition('mover_state', 'plume', 'closing')], scald),
        EventBinding('scald_open', 'zone', 'entered', [Condition('mover_state', 'plume', 'open')], scald),
        EventBinding('scald_opening', 'zone', 'entered', [Condition('mover_state', 'plume', 'opening')], scald),
        EventBinding('vent', 'plume', 'opened', [],
                     [Action('close', target='plume'), Action('play_sound', sound=S('steam'), at='plume')]),
    ])


def pump():
    """A coolant piston that rises and drops back with a thump. It stops at
    the bottom; whoever runs the plant restarts it (the world's binding)."""
    return prefablib.Prefab(pid('pump'), [
        C('piston', 'mover', position=(0.0, 0.0, 0.5), size=(0.44, 0.44, 0.8), move=(0.0, 0.0, 0.5), speed=0.5,
          model=M('pump_piston')),
    ], provenance=prov('pump'), bindings=[
        EventBinding('stroke', 'piston', 'opened', [],
                     [Action('close', target='piston'), Action('play_sound', sound=S('pump'), at='piston')]),
    ])


PREFABS = [security_door, breaker_panel, console, valve, status_lamp, ceiling_light, alarm_light, shutter,
           data_core, steam_vent, pump]


def library():
    prefabs = [make() for make in PREFABS]
    used_models = sorted({c.model for p in prefabs for c in p.children if c.model})
    used_sounds = sorted({c.sound for p in prefabs for c in p.children if c.sound} |
                         {a.sound for p in prefabs for b in p.bindings for a in b.actions if a.sound})
    return Library(PACKAGE, [], requires=[Requirement(art.PACKAGE, used_models + used_sounds)],
                   display_name='Night Shift facility prefabs', prefabs=prefabs)
