"""Night Shift visual production world. X8 gameplay wiring is inherited."""
from assetlab.resources import Requirement
from assetlab.world import Box, Environment, Light

import art_x9
import facility_x9
import world_x8
import world01


def _dress(w):
    # Static, non-colliding architectural layers: no runtime or network ID.
    def box(lo, hi, mat):
        w.boxes.append(Box(lo, hi, mat, solid=False))

    # Loading dock: columns, steel skirting, header and ceiling service rails.
    for y in (-11.6, -9.7, -7.8, -5.9):
        box((-3.89, y, 0.0), (-3.79, y + 0.15, 2.1), 'metal')
        box((3.79, y, 0.0), (3.89, y + 0.15, 2.1), 'metal')
    box((-3.88, -11.9, 0.08), (-3.78, -4.1, 0.18), 'wall_low')
    box((3.78, -11.9, 0.08), (3.88, -4.1, 0.18), 'wall_low')
    for y in (-10.8, -7.8, -4.8):
        box((-3.8, y, 2.05), (3.8, y + 0.12, 2.16), 'metal')
    # Maintenance passage: wall cable tray and low, sharp skirting.
    box((-10.7, -10.88, 0.12), (-4.2, -10.81, 0.24), 'metal')
    box((-10.7, -10.86, 1.14), (-4.2, -10.79, 1.23), 'pipe')
    for x in (-10.2, -8.0, -5.8):
        box((x, -10.87, 0.15), (x + 0.08, -10.79, 1.35), 'rust')
    # Main security corridor: repeated ribs and a shoulder-height rail.
    for y in (-3.3, -0.2, 3.0, 6.2, 9.4, 12.6):
        box((-0.69, y, 0.0), (-0.61, y + 0.12, 1.56), 'metal')
        box((0.61, y, 0.0), (0.69, y + 0.12, 1.56), 'metal')
        box((-0.62, y, 1.49), (0.62, y + 0.12, 1.56), 'metal')
    box((-0.69, -3.9, 0.1), (-0.6, 15.7, 0.18), 'wall_low')
    box((0.6, -3.9, 0.1), (0.69, 15.7, 0.18), 'wall_low')
    # Research hall and core: overhead channels and framed tank alcoves.
    for y in (7.0, 9.0, 11.0, 13.0):
        box((8.15, y, 2.20), (13.85, y + 0.1, 2.35), 'metal')
    for x in (8.15, 13.75):
        box((x, 6.2, 0.15), (x + 0.08, 13.8, 0.25), 'wall_low')
    for x in (7.4, 10.8, 14.2):
        box((x, 16.1, 2.85), (x + 0.12, 23.9, 2.95), 'metal')
    # Service tunnel and freight exit: overhead pipe and floor edging.
    box((17.5, -4.0, 1.23), (18.5, 13.8, 1.33), 'pipe')
    box((17.45, -4.0, 0.04), (17.55, 13.8, 0.12), 'rust')


def _lights():
    L = Light
    aux, lock = world01.eid('aux_power'), world01.eid('lockdown')
    sec, cool = world01.eid('security_link'), world01.eid('coolant_flow')
    p = lambda id, pos, color, power, radius, relay=None: L(id, 'point', pos, color, power, radius, relay=relay)
    s = lambda id, pos, color, power, radius, relay=None: L(id, 'spot', pos, color, power, radius,
                                                            relay=relay, direction=(0, 0, -1),
                                                            inner_degrees=32, outer_degrees=67)
    return sorted([
        p('aux_emergency', (-11.7, -5.8, 1.72), (1, .18, .08), 1.9, 2.8),
        p('aux_passage', (-7.7, -10.45, 1.15), (1, .32, .12), 2.7, 3.8),
        s('aux_main', (-12.6, -4.2, 1.82), (1, .68, .31), 4.8, 4.6, aux),
        p('corridor_emergency', (-.55, 6.0, 1.38), (.9, .13, .08), 1.5, 2.8),
        p('corridor_safety', (-.55, -1.2, 1.35), (1, .32, .13), 2.7, 3.7),
        s('corridor_mid', (0, 3.4, 1.5), (1, .72, .4), 4.3, 4.1, aux),
        s('corridor_north', (0, 10.5, 1.5), (.7, .83, 1), 3.9, 4.0, sec),
        s('corridor_south', (0, -2.0, 1.5), (1, .68, .37), 3.7, 4.0, aux),
        s('dock_center', (0, -8.0, 2.0), (1, .74, .45), 5.2, 5.6, aux),
        p('dock_door', (-.15, -4.3, 1.35), (.3, 1, .52), 2.2, 2.2, world01.child('d1', 'power')),
        p('dock_safety', (-3, -5.3, 1.7), (1, .34, .1), 3.1, 4.1),
        s('dock_west', (-2.7, -10.0, 2.0), (1, .58, .29), 3.3, 3.9, aux),
        p('lift_control', (4.1, -9, 1.18), (.35, 1, .52), 2.8, 2.5, world01.child('lift', 'power')),
        p('lockdown_core', (11, 18, 2.4), (1, .08, .04), 4.3, 6.0, lock),
        p('lockdown_hall', (0, 11, 1.35), (1, .08, .04), 4.0, 4.3, lock),
        p('lockdown_tunnel', (18, 12, 1.22), (1, .09, .05), 3.6, 4.4, lock),
        s('pump_work', (-12.5, 1.8, 1.8), (.7, .9, 1), 3.3, 4.0, cool),
        p('research_door', (.95, 9, 1.2), (.25, 1, .58), 2.7, 2.2, world01.child('d3', 'power')),
        s('research_main', (11, 9.5, 2.2), (.4, .72, 1), 4.4, 5.7, sec),
        p('research_tank', (13, 11.1, 1.2), (.12, .65, .9), 2.3, 3.4),
        p('service_low', (18, 3, 1.1), (1, .32, .15), 2.5, 3.5, lock),
        p('service_mid', (18, 8, 1.1), (1, .26, .12), 2.8, 3.5, lock),
        s('security_console', (-4.8, 4.2, 1.6), (.35, .95, 1), 3.2, 3.7, sec),
        s('specimen_cold', (3.5, 9, 1.45), (.3, .6, 1), 2.5, 3.3),
        p('tunnel_hint', (18, -2, 1.1), (1, .18, .08), 1.6, 2.7),
        p('vestibule', (11, 15, 1.42), (.45, .7, 1), 2.8, 3.2),
    ], key=lambda l: l.id)


def world():
    w = world_x8.world()
    w.id = 'nightshift:world/harrow_annex_x9'
    w.file_name = 'night_shift_x9'
    w.package = 'nightshift.world_x9'
    w.display_name = 'Night Shift: Harrow Annex'
    w.requires = [Requirement(art_x9.PACKAGE if r.package == 'nightshift.assets' else facility_x9.PACKAGE,
                              list(r.resources)) for r in w.requires]
    w.environment = Environment((.36, .39, .45), (.015, .022, .034), (.045, .055, .075), .08, 2.5)
    w.lights = _lights()
    w.texture_style = 'industrial'
    _dress(w)
    return w
