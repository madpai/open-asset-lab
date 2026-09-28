"""nightshift.world01 -- HARROW ANNEX, the first Night Shift world.

A research annex went quiet during the night shift. A recovery crew comes in
through the loading dock to pull the annex's data core and get out.

Plan (x east, y north, 1 wu per unit, floor top z = 0; see
docs/night_shift/GAME_FLOW.md in MegaMod for the play-through):

    y
   24 |                    +-----------+
      |                    |   CORE    |==service tunnel==+
      |                    |  CHAMBER  |  (sealed until   |
   16 |                    +---| |-----+   lockdown)      |
      |                  +-----------+                    |
      |  cell --passage->| SPECIMEN  |                    |  steam vent
    9 |      corridor -D3-> wing --->|   HALL    |         |
    6 +--+--------+ |    +-----------+                    |
      |  PUMP  |CONTROL| |                                 |  lift breaker
    0 +--------+-------+ |                                 |
      |  AUX   |       | |                                 |  steam vent
   -4 +--------+       +D1+---------+---------------------+
      |   ^ passage    |  DOCK  [shutter]
  -12 |   +------------|  spawn [LIFT] -> surface (x 30..42)
      +-----------------------------------------------------> x
      -16      -9     -0.8  0.8   4  7          17.4 18.6

Budget: the world is written against WORLD_STATE's 64-entity index; every
visible fixture that does not move or react is world geometry (boxes), not
a prop. See docs/night_shift/ENTITY_BUDGET.md.
"""
from __future__ import annotations

from assetlab import prefabs as prefablib
from assetlab.bindings import Action, Condition, EventBinding
from assetlab.resources import Requirement
from assetlab.scripts import Script
from assetlab.world import Box, Entity, MoverDefinition, OriginalWorld

import art
import facility

PACKAGE = 'nightshift.world01'
WORLD = f'{art.NS}:world/harrow_annex'
HERE = __import__('pathlib').Path(__file__).resolve().parent


def eid(name):
    return f'{art.NS}:entity/{name}'


def child(instance, name):
    return eid(f'{instance}__{name}')


S = art.sound_id
P = facility.pid
T = 0.1          # half a wall's thickness

# World geometry is flat colour: dark surfaces, and a few saturated fixtures
# that read as lamps because nothing is shaded.
MATERIALS = {
    'floor': (36, 38, 42), 'floor_dock': (44, 44, 46), 'line': (170, 136, 24),
    'wall': (52, 56, 62), 'wall_low': (32, 34, 38), 'ceiling': (16, 16, 18),
    'wall_cold': (40, 50, 58), 'wall_core': (26, 30, 36), 'cell': (22, 20, 22),
    'metal': (78, 80, 84), 'rust': (82, 60, 44), 'crate': (92, 74, 50), 'truck': (60, 70, 62),
    'generator': (54, 66, 56), 'pipe': (96, 88, 70),
    'water': (14, 30, 44), 'cable': (18, 18, 18), 'spark': (255, 236, 150),
    'lamp_red': (170, 26, 20), 'lamp_amber': (190, 120, 20), 'lamp_cyan': (40, 170, 190),
    'screen': (18, 70, 40), 'tank': (24, 64, 72), 'glass_broken': (70, 110, 120), 'stain': (40, 18, 16),
    'conduit': (30, 120, 140), 'grate': (48, 50, 52), 'bars': (70, 72, 76),
    'ground': (40, 44, 36), 'fence': (66, 68, 64), 'tower': (58, 58, 60), 'flood': (230, 226, 190),
    'hidden': (54, 66, 56),
}


def wall_x(x, y0, y1, h, mat='wall', gaps=()):
    """A wall in the plane x (x-T..x+T) from y0 to y1, with doorways (g0, g1, top)."""
    out, y = [], y0
    for g0, g1, top in sorted(gaps):
        if g0 > y:
            out.append(Box((x - T, y, 0.0), (x + T, g0, h), mat))
        out.append(Box((x - T, g0, top), (x + T, g1, h), mat))
        y = g1
    if y1 > y:
        out.append(Box((x - T, y, 0.0), (x + T, y1, h), mat))
    return out


def wall_y(y, x0, x1, h, mat='wall', gaps=()):
    out, x = [], x0
    for g0, g1, top in sorted(gaps):
        if g0 > x:
            out.append(Box((x, y - T, 0.0), (g0, y + T, h), mat))
        out.append(Box((g0, y - T, top), (g1, y + T, h), mat))
        x = g1
    if x1 > x:
        out.append(Box((x, y - T, 0.0), (x1, y + T, h), mat))
    return out


def slab(x0, y0, x1, y1, h, mat='ceiling', thick=0.2):
    return Box((x0, y0, h), (x1, y1, h + thick), mat)


def floor(x0, y0, x1, y1, mat='floor'):
    return Box((x0, y0, -0.2), (x1, y1, 0.0), mat)


def deco(x0, y0, z0, x1, y1, z1, mat, solid=True):
    return Box((x0, y0, z0), (x1, y1, z1), mat, solid=solid)


def geometry():
    b = []
    # ---- the loading dock (spawn) ----------------------------------------------------
    H = 2.2
    b += [floor(-4, -12, 4, -4, 'floor_dock'), slab(-4.1, -12.1, 4.1, -3.9, H)]
    b += wall_y(-12, -4.1, 4.1, H)
    b += wall_y(-4, -4.1, 4.1, H, gaps=[(-0.6, 0.6, 1.2)])                       # D1
    b += wall_x(-4, -12, -4, H, gaps=[(-11.0, -9.8, 1.4)])                       # the maintenance passage
    b += wall_x(4, -12, -4, H, gaps=[(-9.6, -8.4, 1.2), (-5.8, -4.6, 1.2)])      # LIFT, the tunnel shutter
    b += [deco(-3.9, -11.9, 0.0, -2.6, -11.15, 1.0, 'crate'), deco(-3.9, -9.4, 0.0, -3.0, -8.6, 0.6, 'crate'),
          deco(-3.7, -11.85, 1.0, -2.8, -11.2, 1.5, 'crate'),
          deco(1.6, -11.9, 0.0, 3.9, -10.2, 1.3, 'truck'), deco(1.8, -10.2, 0.0, 3.7, -9.9, 0.8, 'truck'),
          deco(-3.9, -7.5, 0.0, -3.0, -6.5, 0.9, 'crate'),
          deco(-0.08, -11.6, 0.0, 0.08, -4.2, 0.01, 'line', solid=False),         # the painted lane
          deco(-3.2, -4.12, 1.6, -2.8, -4.05, 1.75, 'lamp_amber', solid=False),
          deco(2.8, -4.12, 1.6, 3.2, -4.05, 1.75, 'lamp_amber', solid=False),
          deco(3.93, -10.0, 1.3, 3.98, -9.8, 1.45, 'lamp_red', solid=False)]
    # ---- the maintenance passage and the auxiliary power room -------------------------
    Hp = 1.4
    b += [floor(-12, -11, -4, -9.8), slab(-12.1, -11.1, -3.9, -9.7, Hp)]
    b += wall_y(-11, -12.1, -4, Hp) + wall_y(-9.8, -10.8, -4, Hp)
    b += [floor(-12, -9.8, -10.8, -7), slab(-12.1, -9.8, -10.7, -6.9, Hp)]
    b += wall_x(-12, -11.1, -6.9, Hp) + wall_x(-10.8, -9.8, -7, Hp)
    b += [deco(-9.0, -10.95, 1.1, -5.0, -10.85, 1.2, 'pipe'), deco(-11.95, -9.5, 1.15, -11.85, -7.2, 1.25, 'pipe')]
    Ha = 2.0
    b += [floor(-16, -7, -9, -1.5), slab(-16.1, -7.1, -8.9, -1.4, Ha)]
    b += wall_y(-7, -16.1, -8.9, Ha, gaps=[(-12.0, -10.8, Hp)]) + wall_y(-1.5, -16.1, -8.9, Ha)
    b += wall_x(-16, -7, -1.5, Ha) + wall_x(-9, -7, -1.5, Ha)
    b += [deco(-14.5, -5.0, 0.0, -11.5, -3.0, 1.4, 'generator'),                  # the generator (the cycle lives inside)
          deco(-14.2, -4.6, 1.4, -13.8, -4.2, 1.95, 'pipe'), deco(-12.2, -3.8, 1.4, -11.8, -3.4, 1.95, 'pipe'),
          deco(-15.9, -2.2, 1.7, -15.85, -1.8, 1.8, 'lamp_red', solid=False)]
    # ---- the control room --------------------------------------------------------------
    Hc = 1.8
    b += [floor(-9, 0, -0.8, 6), slab(-9.1, -0.1, -0.7, 6.1, Hc)]
    b += wall_y(0, -9.1, -0.7, Hc) + wall_y(6, -9.1, -0.7, Hc)
    b += wall_x(-9, 0, 6, Hc, gaps=[(1.0, 2.2, 1.3)])                            # to the pump room
    b += [deco(-8.5, 5.6, 0.6, -1.5, 5.9, 1.5, 'wall_low'),                       # the monitor wall, dead
          deco(-8.2, 5.55, 0.8, -7.0, 5.6, 1.3, 'screen', solid=False), deco(-6.5, 5.55, 0.8, -5.3, 5.6, 1.3, 'screen', solid=False),
          deco(-3.6, 5.55, 0.8, -2.4, 5.6, 1.3, 'screen', solid=False),
          deco(-8.6, 0.4, 0.0, -6.8, 1.0, 0.7, 'metal'), deco(-3.4, 0.4, 0.0, -1.4, 1.0, 0.7, 'metal'),
          deco(-5.8, 2.6, 0.0, -5.2, 3.2, 0.5, 'crate')]                          # a toppled chair
    # ---- the pump room (flooded) -------------------------------------------------------
    b += [floor(-16, 0, -9, 7), slab(-16.1, -0.1, -8.9, 7.1, Ha)]
    b += wall_y(0, -16.1, -8.9, Ha) + wall_y(7, -16.1, -8.9, Ha)
    b += wall_x(-16, 0, 7, Ha) + wall_x(-9, 0, 7, Ha, gaps=[(1.0, 2.2, 1.3)])
    b += [deco(-14.8, 0.8, 0.0, -10.2, 5.2, 0.02, 'water', solid=False),
          deco(-13.0, 1.3, 0.0, -12.0, 2.3, 0.2, 'metal'),                          # the pump's plinth
          deco(-13.1, 1.2, 0.2, -13.0, 2.4, 1.4, 'grate'), deco(-12.0, 1.2, 0.2, -11.9, 2.4, 1.4, 'grate'),
          deco(-12.55, 3.35, 0.35, -12.45, 3.45, 2.0, 'cable', solid=False),         # the live cable
          deco(-12.6, 3.3, 0.02, -12.4, 3.5, 0.35, 'spark', solid=False),
          deco(-16.0, 6.0, 1.2, -9.0, 6.2, 1.4, 'pipe'), deco(-15.9, 0.2, 1.7, -15.85, 0.6, 1.8, 'lamp_red', solid=False)]
    # ---- the main corridor ---------------------------------------------------------------
    Hm = 1.6
    b += [floor(-0.8, -4, 0.8, 16), slab(-0.9, -4, 0.9, 16.1, Hm)]
    b += wall_x(-0.8, -3.9, 16.1, Hm, gaps=[(2.4, 3.6, 1.3)])                     # the control room
    b += wall_x(0.8, -3.9, 16.1, Hm, gaps=[(8.4, 9.6, 1.2)])                      # D3
    b += wall_y(16, -0.9, 0.9, Hm)
    b += [deco(-0.7, 14.2, 0.0, 0.1, 15.9, 0.7, 'rust'), deco(-0.2, 15.0, 0.7, 0.7, 15.9, 1.3, 'rust'),   # collapse
          deco(0.1, 13.6, 0.0, 0.7, 14.4, 0.35, 'rust'),
          deco(-0.72, -1.0, 1.45, -0.7, -0.6, 1.55, 'lamp_red', solid=False),
          deco(-0.72, 5.0, 1.45, -0.7, 5.4, 1.55, 'lamp_red', solid=False),
          deco(-0.72, 11.8, 1.45, -0.7, 12.2, 1.55, 'lamp_red', solid=False),
          deco(-0.7, -3.9, 1.45, -0.6, 15.9, 1.52, 'pipe')]
    # ---- the research wing, the holding cell ------------------------------------------------
    Hw = 1.5
    b += [floor(0.9, 8.4, 8, 9.6), slab(0.9, 8.3, 8.1, 9.7, Hw)]
    b += wall_y(8.4, 0.9, 8.0, Hw, gaps=[(2.0, 3.0, 1.2), (4.2, 5.2, 1.2), (6.4, 7.4, 1.2)])
    b += [Box((0.9, 9.5, 0.0), (8.0, 10.1, Hw), 'wall_cold')]                      # thick: the cold spot's entity lives inside
    for x0 in (2.0, 4.2, 6.4):                                                    # specimen alcoves behind bars
        b += [floor(x0, 7.4, x0 + 1.0, 8.3, 'cell'), slab(x0, 7.3, x0 + 1.0, 8.3, Hw),
              Box((x0, 7.3, 0.0), (x0 + 1.0, 7.4, Hw), 'cell'),
              Box((x0 - 0.1, 7.3, 0.0), (x0, 8.3, Hw), 'cell'), Box((x0 + 1.0, 7.3, 0.0), (x0 + 1.1, 8.3, Hw), 'cell')]
        b += [Box((x0 + k * 0.2, 8.35, 0.0), (x0 + k * 0.2 + 0.04, 8.4, 1.2), 'bars') for k in range(1, 5)]
    b += [deco(4.3, 7.5, 0.0, 5.1, 7.8, 0.15, 'stain', solid=False)]
    b += [floor(2, 10.1, 5.5, 13), slab(1.9, 10.1, 5.6, 13.1, Hw)]
    b += wall_y(13, 1.9, 5.6, Hw, 'cell') + wall_x(2, 10.1, 13, Hw, 'cell')
    b += wall_x(5.5, 10.1, 13, Hw, 'cell', gaps=[(11.8, 12.8, 1.3)])
    b += [floor(5.6, 11.8, 8, 12.8), slab(5.6, 11.7, 8.1, 12.9, 1.3)]
    b += wall_y(11.8, 5.6, 8.0, 1.3, 'cell') + wall_y(12.8, 5.6, 8.0, 1.3, 'cell')
    b += [deco(2.2, 12.5, 0.0, 2.6, 12.9, 0.05, 'stain', solid=False), deco(3.6, 12.93, 0.3, 4.4, 12.95, 0.6, 'stain', solid=False)]
    # ---- the specimen hall, the vestibule, the core chamber ------------------------------------
    Hh = 2.4
    b += [floor(8, 6, 14, 14), slab(7.9, 5.9, 14.1, 14.1, Hh)]
    b += wall_y(6, 7.9, 14.1, Hh, 'wall_cold') + wall_y(14, 7.9, 14.1, Hh, 'wall_cold', gaps=[(10.4, 11.6, 1.6)])
    b += wall_x(8, 6, 14, Hh, 'wall_cold', gaps=[(8.4, 9.6, Hw), (11.8, 12.8, 1.3)])
    b += wall_x(14, 6, 14, Hh, 'wall_cold')
    for y0 in (6.6, 8.6, 10.6, 12.6):                                             # specimen tanks
        broken = y0 == 10.6
        b += [deco(12.6, y0, 0.0, 13.8, y0 + 1.0, 0.3, 'metal'),
              deco(12.7, y0 + 0.1, 0.3, 13.7, y0 + 0.9, 0.6 if broken else 1.9, 'glass_broken' if broken else 'tank'),
              deco(12.6, y0, 1.9, 13.8, y0 + 1.0, 2.1, 'metal')]
    b += [deco(11.0, 10.4, 0.0, 12.4, 11.6, 0.01, 'glass_broken', solid=False),
          deco(10.2, 10.7, 0.0, 11.0, 11.2, 0.01, 'stain', solid=False)]
    b += [floor(10.4, 14, 11.6, 16), slab(10.3, 14, 11.7, 16, 1.6)]
    b += wall_x(10.4, 14.1, 15.9, 1.6, 'wall_cold') + wall_x(11.6, 14.1, 15.9, 1.6, 'wall_cold')
    Hk = 3.0
    b += [floor(7, 16, 15, 24), slab(6.9, 15.9, 15.1, 24.1, Hk)]
    b += wall_y(16, 6.9, 15.1, Hk, 'wall_core', gaps=[(10.4, 11.6, 1.6)]) + wall_y(24, 6.9, 15.1, Hk, 'wall_core')
    b += wall_x(7, 16, 24, Hk, 'wall_core') + wall_x(15, 16, 24, Hk, 'wall_core', gaps=[(19.4, 20.6, 1.2)])
    b += [deco(10.5, 20.5, 0.0, 11.5, 21.5, 0.9, 'metal'),                         # the pedestal
          deco(10.3, 20.3, 0.0, 11.7, 21.7, 0.1, 'grate'),
          deco(7.1, 17.0, 0.4, 7.15, 23.0, 0.5, 'conduit', solid=False), deco(7.1, 17.0, 2.2, 7.15, 23.0, 2.3, 'conduit', solid=False),
          deco(8.0, 23.85, 0.4, 14.0, 23.9, 0.5, 'conduit', solid=False), deco(8.0, 23.85, 2.2, 14.0, 23.9, 2.3, 'conduit', solid=False),
          deco(10.9, 21.0, 2.3, 11.1, 21.2, 3.0, 'cable'),                         # the crane stub the core hangs toward
          deco(14.85, 18.4, 1.3, 14.9, 18.8, 1.5, 'lamp_red', solid=False)]
    # ---- the service tunnel (sealed until lockdown) --------------------------------------------
    Ht, thick = 1.4, 0.7                                                           # a thick roof: the steam vents hide in it
    b += [floor(15, 19.4, 18.6, 20.6), slab(15.1, 19.3, 18.7, 20.7, Ht, thick=thick)]
    b += wall_y(19.4, 15.1, 17.4, Ht, 'wall_low') + wall_y(20.6, 15.1, 18.7, Ht, 'wall_low')
    b += [floor(17.4, -5.8, 18.6, 19.4), slab(17.3, -5.9, 18.7, 19.4, Ht, thick=thick)]
    b += wall_x(17.4, -4.6, 19.4, Ht, 'wall_low') + wall_x(18.6, -5.9, 20.7, Ht, 'wall_low')
    b += [floor(4.1, -5.8, 17.4, -4.6), slab(4.1, -5.9, 17.4, -4.5, Ht, thick=thick)]
    b += wall_y(-5.8, 4.1, 18.7, Ht, 'wall_low') + wall_y(-4.6, 4.1, 17.4, Ht, 'wall_low')
    b += [deco(18.45, -4.0, 1.1, 18.5, 18.0, 1.2, 'pipe'), deco(17.5, 4.0, 1.25, 17.55, 4.3, 1.35, 'lamp_red', solid=False),
          deco(8.0, -4.75, 1.25, 8.3, -4.7, 1.35, 'lamp_red', solid=False),
          deco(17.45, 7.4, 0.0, 18.55, 8.6, 0.01, 'grate', solid=False), deco(9.4, -5.75, 0.0, 10.6, -4.65, 0.01, 'grate', solid=False)]
    # ---- the freight lift car -------------------------------------------------------------------
    b += [floor(4.1, -10.5, 7, -7.5, 'grate'), slab(4.1, -10.6, 7.1, -7.4, 2.0)]
    b += wall_y(-10.5, 4.1, 7.1, 2.0, 'metal') + wall_y(-7.5, 4.1, 7.1, 2.0, 'metal') + wall_x(7, -10.6, -7.4, 2.0, 'metal')
    b += [deco(6.85, -9.3, 0.9, 6.9, -8.7, 1.2, 'lamp_amber', solid=False)]
    # ---- the surface (no roof: the sky) -----------------------------------------------------------
    b += [floor(30, -16, 42, -4, 'ground')]
    b += wall_y(-16, 29.9, 42.1, 1.0, 'fence') + wall_y(-4, 29.9, 42.1, 1.0, 'fence')
    b += wall_x(30, -16, -4, 1.0, 'fence') + wall_x(42, -16, -4, 1.0, 'fence')
    b += [deco(30.2, -11.5, 0.0, 32.2, -8.5, 3.2, 'tower'),                         # the lift headframe
          deco(30.4, -11.3, 3.2, 32.0, -8.7, 3.4, 'metal'),
          deco(38.0, -6.0, 0.0, 38.2, -5.8, 3.0, 'tower'), deco(37.8, -6.1, 3.0, 38.4, -5.7, 3.15, 'flood', solid=False),
          deco(38.0, -14.2, 0.0, 38.2, -14.0, 3.0, 'tower'), deco(37.8, -14.3, 3.0, 38.4, -13.9, 3.15, 'flood', solid=False),
          deco(34.0, -15.0, 0.0, 36.5, -13.5, 1.2, 'truck')]
    return b


CYCLE = eid('facility_cycle')
# World movers in a world with props must name a definition (schema 4+).
CYCLE_DEF = f'{art.NS}:mover/facility_cycle'


def entities():
    E = Entity
    return [
        # state: relays remember what they were last told (X7)
        E(eid('aux_power'), 'relay'), E(eid('security_link'), 'relay'), E(eid('coolant_flow'), 'relay'),
        E(eid('lockdown'), 'relay'), E(eid('shift_complete'), 'relay'), E(eid('anomaly'), 'relay'),
        # the plant's heartbeat: a mover hidden in the generator; its travel is the only clock X7 has
        E(CYCLE, 'mover', definition=CYCLE_DEF, position=(-13.0, -4.0, 0.4)),
        # triggers
        E(eid('passage_stinger'), 'trigger', bounds=((-9.2, -11.0, 0.0), (-8.0, -9.8, 1.0))),
        E(eid('corridor_stinger'), 'trigger', bounds=((-0.8, 5.0, 0.0), (0.8, 6.0, 1.0))),
        E(eid('puddle_a'), 'trigger', bounds=((-14.8, 0.8, -0.1), (-12.5, 5.2, 0.6))),
        E(eid('puddle_b'), 'trigger', bounds=((-12.5, 0.8, -0.1), (-10.2, 5.2, 0.6))),
        E(eid('cold_spot'), 'trigger', bounds=((3.0, 8.4, 0.0), (4.2, 9.5, 1.0))),
        E(eid('tunnel_stinger'), 'trigger', bounds=((17.4, 14.0, 0.0), (18.6, 15.0, 1.0))),
        E(eid('lift_car'), 'trigger', bounds=((4.7, -10.4, 0.0), (6.9, -7.6, 1.0))),
        # destinations
        E(eid('holding_cell'), 'teleport', position=(2.6, 10.7, 0.05), yaw_degrees=45.0),
        E(eid('surface'), 'teleport', position=(33.5, -10.0, 0.05), yaw_degrees=0.0),
        # the cold spot's hook for Lua: buried in the wall between the wing and the cell, out of reach
        E(eid('cold_spot_hook'), 'interactable', position=(3.6, 9.8, 0.6), reach=0.05, script=f'{art.NS}:script/anomaly'),
        # signs (props: the world's boxes cannot carry a texture)
        E(eid('sign_aux'), 'prop', position=(-3.88, -10.4, 1.75), model=art.model_id('sign_aux')),
        E(eid('sign_research'), 'prop', position=(0.68, 7.3, 1.3), model=art.model_id('sign_research'), yaw_degrees=180.0),
        E(eid('sign_lift'), 'prop', position=(3.88, -9.0, 1.65), model=art.model_id('sign_lift'), yaw_degrees=180.0),
        E(eid('sign_orders'), 'prop', position=(-2.3, -4.12, 1.2), model=art.model_id('sign_orders'), yaw_degrees=-90.0),
    ]


def instances():
    I = prefablib.PrefabInstance
    return [
        I('d1', P('security_door'), (0.0, -4.0, 0.0), yaw_degrees=90.0),          # dock -> corridor
        I('d3', P('security_door'), (0.8, 9.0, 0.0)),                             # corridor -> research wing
        I('lift', P('security_door'), (4.0, -9.0, 0.0)),                          # dock -> freight lift
        I('aux_breaker', P('breaker_panel'), (-16.0, -4.2, 0.0), yaw_degrees=180.0),
        I('lift_breaker', P('breaker_panel'), (17.4, 0.0, 0.0), yaw_degrees=180.0),
        I('console', P('console'), (-4.8, 5.2, 0.0), yaw_degrees=90.0),
        I('valve', P('valve'), (-16.0, 3.0, 0.0), yaw_degrees=180.0),
        I('cool_lamp', P('status_lamp'), (0.8, 6.8, 0.8)),
        I('sec_lamp', P('status_lamp'), (0.8, 7.8, 0.8)),
        I('dock_light', P('ceiling_light'), (0.0, -8.0, 2.2)),
        I('alarm_corridor', P('alarm_light'), (0.0, 11.0, 1.6), yaw_degrees=90.0),
        I('alarm_core', P('alarm_light'), (11.0, 17.0, 3.0)),
        I('alarm_tunnel', P('alarm_light'), (18.0, 12.0, 1.4), yaw_degrees=90.0),
        I('shutter_core', P('shutter'), (15.0, 20.0, 0.0)),
        I('shutter_dock', P('shutter'), (4.0, -5.2, 0.0), yaw_degrees=180.0),
        I('core', P('data_core'), (11.0, 21.0, 0.0)),
        I('vent_north', P('steam_vent'), (18.0, 8.0, 0.0)),
        I('vent_south', P('steam_vent'), (10.0, -5.2, 0.0), yaw_degrees=90.0),
        I('pump', P('pump'), (-12.5, 1.8, 0.2)),
    ]


def bindings():
    B, A, If = EventBinding, Action, Condition
    rs = lambda e, v: If('relay_state', e, v)
    snd = lambda name, at: A('play_sound', sound=S(name), at=at)
    aux, sec, cool, lock = eid('aux_power'), eid('security_link'), eid('coolant_flow'), eid('lockdown')
    return [
        # 1. auxiliary power: the breaker wakes the dock door, the dock light and the plant
        B('aux_on', child('aux_breaker', 'lever'), 'used', [rs(aux, 'inactive')], [A('activate', target=aux)]),
        B('aux_live', aux, 'activated', [],
          [A('activate', target=child('d1', 'power')), A('open', target=child('dock_light', 'light')),
           A('open', target=CYCLE), snd('generator', child('aux_breaker', 'box'))]),
        # 2. two subsystems; research access needs both (an AND from two conditions)
        B('sec_on', child('console', 'terminal'), 'used', [rs(sec, 'inactive')], [A('activate', target=sec)]),
        B('sec_live', sec, 'activated', [],
          [A('open', target=child('sec_lamp', 'lamp')), snd('confirm', child('console', 'desk'))]),
        B('sec_research', sec, 'activated', [rs(cool, 'active')],
          [A('activate', target=child('d3', 'power')), snd('power_on', child('console', 'desk'))]),
        B('cool_on', child('valve', 'wheel'), 'used', [rs(cool, 'inactive')], [A('activate', target=cool)]),
        B('cool_live', cool, 'activated', [],
          [A('open', target=child('cool_lamp', 'lamp')), A('open', target=child('pump', 'piston')),
           snd('confirm', child('valve', 'body'))]),
        B('cool_research', cool, 'activated', [rs(sec, 'active')],
          [A('activate', target=child('d3', 'power')), snd('power_on', child('valve', 'body'))]),
        B('pump_run', child('pump', 'piston'), 'closed', [rs(cool, 'active')], [A('open', target=child('pump', 'piston'))]),
        # the plant's heartbeat: the cycle swings while there is power
        B('cycle_turn', CYCLE, 'opened', [], [A('close', target=CYCLE)]),
        B('cycle_rearm', CYCLE, 'closed', [rs(aux, 'active')], [A('open', target=CYCLE)]),
        B('plant_hum', CYCLE, 'opened', [rs(lock, 'inactive')],
          [snd('machinery', child('aux_breaker', 'box')), snd('machinery', child('core', 'core'))]),
        B('klaxon', CYCLE, 'opened', [rs(lock, 'active')],
          [snd('alarm', child('alarm_corridor', 'light')), snd('alarm', child('alarm_core', 'light')),
           snd('alarm', child('alarm_tunnel', 'light')), snd('alarm', child('d1', 'plate')),
           A('open', target=child('vent_north', 'plume')), A('open', target=child('vent_south', 'plume'))]),
        B('klaxon_back', CYCLE, 'closed', [rs(lock, 'active')],
          [snd('alarm', child('alarm_corridor', 'light')), snd('alarm', child('alarm_core', 'light')),
           snd('alarm', child('alarm_tunnel', 'light')), snd('alarm', child('d1', 'plate'))]),
        # things in the dark
        B('passage_bang', eid('passage_stinger'), 'entered', [rs(aux, 'inactive')], [snd('distant_bang', child('d3', 'door'))]),
        B('knock', eid('corridor_stinger'), 'entered', [rs(child('d3', 'power'), 'inactive')], [snd('knock', child('d3', 'door'))]),
        B('cold_spot', eid('cold_spot'), 'entered', [], [A('use', target=eid('cold_spot_hook'))]),
        B('followed', eid('tunnel_stinger'), 'entered', [rs(lock, 'active')],
          [snd('knock', child('shutter_core', 'shutter')), snd('distant_bang', child('core', 'core'))]),
        B('stir', eid('anomaly'), 'activated', [], [snd('anomaly', eid('cold_spot')), snd('anomaly', eid('holding_cell'))]),
        # the flooded pump room: the live cable
        B('shock_a', eid('puddle_a'), 'entered', [], [A('damage', amount=20.0), snd('shock', eid('puddle_a'))]),
        B('shock_b', eid('puddle_b'), 'entered', [], [A('damage', amount=20.0), snd('shock', eid('puddle_b'))]),
        # 3. the core: when it has risen clear, the annex locks down
        B('extract', child('core', 'core'), 'opened', [], [A('activate', target=lock)]),
        B('lockdown_seal', lock, 'activated', [],
          [A('deactivate', target=child('d1', 'power')), A('close', target=child('d3', 'door')),
           A('close', target=child('dock_light', 'light')), snd('alarm', child('core', 'core'))]),
        B('lockdown_routes', lock, 'activated', [],
          [A('open', target=child('shutter_core', 'shutter')), A('open', target=child('shutter_dock', 'shutter')),
           A('open', target=child('alarm_corridor', 'light')), A('open', target=child('alarm_core', 'light')),
           A('open', target=child('alarm_tunnel', 'light'))]),
        # 4. the way out
        B('lift_power', child('lift_breaker', 'lever'), 'used', [rs(child('lift', 'power'), 'inactive')],
          [A('activate', target=child('lift', 'power'))]),
        B('ride', eid('lift_car'), 'entered', [],
          [A('teleport', target=eid('surface')), A('activate', target=eid('shift_complete')), snd('lift', eid('surface'))]),
        B('shift_over', eid('shift_complete'), 'activated', [], [snd('shift_over', eid('surface'))]),
    ]


def world():
    spawns = [{'position': [x, -11.0, 0.0], 'yaw_degrees': 90.0, 'team': None} for x in (-1.5, -0.5, 0.5, 1.5)]
    w = OriginalWorld(id=WORLD, file_name='night_shift', display_name='Night Shift: Harrow Annex',
                      materials=dict(MATERIALS), boxes=geometry(), spawns=spawns, entities=entities(),
                      mover_definitions=[MoverDefinition(CYCLE_DEF, (0.8, 0.8, 0.4), (0.0, 0.0, 0.5), 0.125, 'hidden')],
                      scripts=[Script(f'{art.NS}:script/anomaly', (HERE / 'scripts/anomaly.lua').read_text(encoding='ascii'),
                                      ['on_used'])])
    w.prefab_instances = instances()
    w.bindings = bindings()
    w.package = PACKAGE
    used_prefabs = sorted({i.prefab for i in w.prefab_instances})
    used_models = sorted({e.model for e in w.entities if e.model})
    used_sounds = sorted({a.sound for b in w.bindings for a in b.actions if a.sound})
    w.requires = [Requirement(art.PACKAGE, used_models + used_sounds), Requirement(facility.PACKAGE, used_prefabs)]
    return w
