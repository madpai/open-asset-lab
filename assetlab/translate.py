"""The translation registry: which Source entities and material properties
mean what in an Open Halo package.

Every Source class or material property the importer acts on is listed
here, as data. Anything not listed is reported as unsupported with a count;
nothing is dropped silently. No entry names a particular map, material or
entity instance -- these are the Source SDK's generic classes and shader
parameters, shared by every game built on it.
"""
from __future__ import annotations
import hashlib

RED, BLUE = 0, 1  # Open Halo team indices. ANY is None.

# Player starts. `team` is fixed, or read from a keyvalue through `values`.
# Which Source faction plays red is a convention, kept here only:
# attackers/rebels red, defenders/combine blue.
SPAWN_CLASSES = {
    'info_player_start': {'team': None},
    'info_player_deathmatch': {'team': None},
    'info_player_terrorist': {'team': RED},
    'info_player_counterterrorist': {'team': BLUE},
    'info_player_rebel': {'team': RED},
    'info_player_combine': {'team': BLUE},
    # TF2: TeamNum 2 is RED, 3 is BLU; 0 means either team.
    'info_player_teamspawn': {'key': 'teamnum', 'values': {'2': RED, '3': BLUE}},
}

# Brush entities: their model's faces are world geometry placed at the
# entity's origin/angles. `solid` is True/False, or a keyvalue rule.
# Moving and breakable brushes are imported in their spawn pose.
BRUSH_CLASSES = {
    'func_brush': {'solid': {'key': 'solidity', 'false': {'1'}}},  # 1 = never solid
    'func_wall': {'solid': True},
    'func_wall_toggle': {'solid': True},
    'func_illusionary': {'solid': False},
    'func_lod': {'solid': True},
    'func_breakable': {'solid': True, 'note': 'imported unbroken'},
    'func_breakable_surf': {'solid': True, 'note': 'imported unbroken'},
    'func_physbox': {'solid': True, 'note': 'imported static at its spawn pose'},
    'func_physbox_multiplayer': {'solid': True, 'note': 'imported static at its spawn pose'},
    # Nothing opens a door in Open Halo, so a sliding door is placed where
    # it stops when open (Source's m_vecPosition2), not left as a wall.
    'func_door': {'solid': True, 'open': True, 'note': 'imported open, does not move'},
    'func_door_rotating': {'solid': True, 'note': 'imported closed, does not open'},
    'func_movelinear': {'solid': True, 'note': 'imported static at its spawn pose'},
    'func_rotating': {'solid': True, 'note': 'imported static, does not rotate'},
    'func_tracktrain': {'solid': True, 'note': 'imported static at its spawn pose'},
    'func_train': {'solid': True, 'note': 'imported static at its spawn pose'},
    'func_button': {'solid': True, 'note': 'imported static, not usable'},
    'func_rot_button': {'solid': True, 'note': 'imported static, not usable'},
    'func_monitor': {'solid': True},
    'func_reflective_glass': {'solid': True},
}
# A brush entity with any of these keyvalues set is not drawn at spawn.
BRUSH_HIDDEN = (('startdisabled', '1'), ('rendermode', '10'))

# Model entities placed like static props (a model, origin and angles).
MODEL_CLASSES = {
    'prop_dynamic': {'solid': True, 'note': 'imported in its bind pose, not animated'},
    'prop_dynamic_override': {'solid': True, 'note': 'imported in its bind pose, not animated'},
    'prop_physics': {'solid': True, 'note': 'imported static'},
    'prop_physics_multiplayer': {'solid': True, 'note': 'imported static'},
    'prop_physics_override': {'solid': True, 'note': 'imported static'},
    'prop_door_rotating': {'solid': True, 'note': 'imported closed, does not open'},
}

# Entities that are deliberately not geometry: invisible volumes, logic and
# effects. They are counted as "not needed", distinct from "unsupported".
NOT_GEOMETRY_PREFIXES = ('trigger_', 'logic_', 'env_', 'info_', 'point_', 'ambient_', 'filter_',
                         'math_', 'game_', 'light', 'keyframe_', 'move_rope', 'ai_', 'path_',
                         'phys_', 'npc_', 'scripted_', 'func_areaportal', 'func_occluder',
                         'func_clip_vphysics', 'func_buyzone', 'func_bomb_target',
                         'func_hostage_rescue', 'func_nobuild', 'func_respawnroom',
                         'func_regenerate', 'func_ladder', 'func_dustmotes', 'func_dustcloud',
                         'func_smokevolume', 'func_precipitation', 'shadow_control',
                         'water_lod_control', 'sky_camera', 'worldspawn', 'color_correction',
                         'fog_volume', 'postprocess_controller', 'infodecal', 'item_', 'weapon_',
                         'team_', 'tf_', 'hostage_entity', 'cycler',
                         # vbsp merges func_detail into the world; a leftover
                         # entity record has no model of its own.
                         'func_detail', 'func_vehicleclip', 'func_playerclip')


# Where each team's flag stands in a capture-the-flag map. TF2's intelligence
# briefcase: TeamNum 2 is RED's, 3 is BLU's.
FLAG_CLASSES = {
    'item_teamflag': {'key': 'teamnum', 'values': {'2': RED, '3': BLUE}},
}


def flag_team(entity):
    """The team whose flag this entity is, or None."""
    rule = FLAG_CLASSES.get(entity.get('classname', '').lower())
    if rule is None:
        return None
    return rule['values'].get(entity.get(rule['key'], '').strip())


def spawn_team(entity):
    """The Open Halo team for a start (None for either), or False when the
    class is not a player start."""
    rule = SPAWN_CLASSES.get(entity.get('classname', '').lower())
    if rule is None:
        return False
    if 'key' in rule:
        value = entity.get(rule['key'], entity.get(rule['key'].lower(), '')).strip()
        return rule['values'].get(value)
    return rule['team']


def brush_rule(entity):
    """(solid, note) for a drawn brush entity, or None when the class is not
    translated as geometry or it starts hidden."""
    rule = BRUSH_CLASSES.get(entity.get('classname', '').lower())
    if rule is None:
        return None
    for key, value in BRUSH_HIDDEN:
        if entity.get(key, '').strip() == value:
            return None
    solid = rule['solid']
    if isinstance(solid, dict):
        solid = entity.get(solid['key'], '').strip() not in solid['false']
    return bool(solid), rule.get('note')


def door_open_offset(entity, bounds):
    """Where a func_door stops when open, from its closed place, in Source
    units: along movedir by the brush's extent that way less the lip
    (CFuncDoor's m_vecPosition2 = pos1 + dir * (|size . |dir|| - lip)).
    `bounds` is the brush model's (mins, maxs). Spawnflag 1 (starts open)
    already stands open: no offset."""
    import math
    try:
        flags = int(entity.get('spawnflags', '0'))
    except ValueError:
        flags = 0
    if flags & 1:
        return (0.0, 0.0, 0.0)
    try:
        pitch, yaw, _ = (float(x) for x in entity.get('movedir', '0 0 0').split())
        lip = float(entity.get('lip', '0'))
    except ValueError:
        return (0.0, 0.0, 0.0)
    p, y = math.radians(pitch), math.radians(yaw)
    d = (math.cos(p)*math.cos(y), math.cos(p)*math.sin(y), -math.sin(p))
    d = tuple(0.0 if abs(c) < 1e-6 else c for c in d)
    size = [bounds[1][k] - bounds[0][k] for k in range(3)]
    travel = abs(sum(abs(d[k])*size[k] for k in range(3))) - lip
    return tuple(d[k]*travel for k in range(3))


def entity_role(classname):
    """'spawn' | 'brush' | 'model' | 'not_geometry' | 'unsupported'."""
    c = classname.lower()
    if c in SPAWN_CLASSES:
        return 'spawn'
    if c in BRUSH_CLASSES:
        return 'brush'
    if c in MODEL_CLASSES:
        return 'model'
    if any(c == p or c.startswith(p) for p in NOT_GEOMETRY_PREFIXES):
        return 'not_geometry'
    return 'unsupported'


# ---- materials ---------------------------------------------------------

# VMT shaders / parameters and what the package does with them.
NON_SOLID_SHADERS = {'water'}            # drawn, not collided with
UNSUPPORTED_MATERIAL_PARAMS = {
    '$basetexture2': 'second blend layer ignored (first layer only)',
    '$bumpmap': 'normal map ignored',
    '$envmap': 'reflections ignored',
    '$detail': 'detail texture ignored',
    '$selfillum': 'self-illumination ignored',
}

# Diagnostic colours for a material whose texture could not be read,
# keyed on Source's generic $surfaceprop vocabulary (surfaceproperties.txt),
# never on material names.
SURFACEPROP_COLORS = (
    (('grass', 'foliage', 'antlion'), (83, 112, 69)),
    (('wood',), (136, 105, 72)),
    (('brick', 'tile', 'ceramic', 'porcelain'), (145, 98, 81)),
    (('concrete', 'rock', 'boulder', 'stone', 'gravel', 'plaster'), (126, 126, 120)),
    (('metal', 'solidmetal', 'metalgrate', 'metalvent', 'chainlink', 'computer'), (112, 123, 131)),
    (('water', 'slime', 'glass', 'ice'), (77, 121, 141)),
    (('dirt', 'mud', 'sand', 'quicksand'), (131, 112, 84)),
)
NEUTRAL = (124, 117, 111)


def material_policy(props):
    """From a VMT's parameters (lower-cased keys, plus 'shader'): whether
    the surface collides, and which of its features are not reproduced."""
    shader = props.get('shader', '').lower()
    solid = shader not in NON_SOLID_SHADERS
    dropped = sorted(msg for key, msg in UNSUPPORTED_MATERIAL_PARAMS.items()
                     if key in props and props[key] not in ('0', ''))
    return solid, dropped


def material_alpha(props):
    """A surface whose texture alpha is its shape: fences, foliage, hay,
    cobwebs ($alphatest) and glass or decals ($translucent). Open Halo draws
    these in its alpha-blended pass, after the solid world."""
    return any(props.get(k, '0').strip() not in ('0', '') for k in ('$alphatest', '$translucent'))


def material_hidden(props):
    """An additive surface (light shafts, glows, sprites) only brightens what
    is behind it. Open Halo draws it opaque -- a black or white slab in the
    air -- so it is left out."""
    return props.get('$additive', '0').strip() not in ('0', '')


def placeholder(name, props=None):
    """A muted 4x4 diagnostic texture for an unresolved material."""
    surface = (props or {}).get('$surfaceprop', '').lower()
    base = next((c for words, c in SURFACEPROP_COLORS if any(w in surface for w in words)), NEUTRAL)
    digest = hashlib.sha256(name.lower().encode()).digest()
    pixels = bytearray()
    for i in range(16):
        d = digest[i] % 11 - 5
        pixels.extend((*[max(0, min(255, c + d)) for c in base], 255))
    return 4, 4, bytes(pixels)


# ---- characters and weapons -------------------------------------------------------
#
# A character clip is baked from a base sequence (by activity, the direction
# picked from its blend grid) plus an optional upper-body layer (by sequence
# name, `{hold}` filled from the build's hold type). Each role lists recipes
# for the Source game families; the first one the model can satisfy is used
# and the report says which. Directions are unit vectors in the model's
# XY plane (+X forward, +Y left), matched against each blend cell's root
# motion or, failing that, the move_x/move_y pose parameters.
CHARACTER_ROLES = {
    'idle': [
        {'activity': ['ACT_HL2MP_IDLE_{HOLD}', 'ACT_HL2MP_IDLE']},
        {'activity': ['ACT_IDLE'], 'layer': ['Idle_Upper_{hold}']},
    ],
    'run_front': [
        {'activity': ['ACT_HL2MP_RUN_{HOLD}', 'ACT_HL2MP_RUN'], 'move': (1, 0)},
        {'activity': ['ACT_RUN'], 'move': (1, 0), 'layer': ['Run_Upper_{hold}']},
    ],
    'run_back': [
        {'activity': ['ACT_HL2MP_RUN_{HOLD}', 'ACT_HL2MP_RUN'], 'move': (-1, 0)},
        {'activity': ['ACT_RUN'], 'move': (-1, 0), 'layer': ['Run_Upper_{hold}']},
    ],
    'run_left': [
        {'activity': ['ACT_HL2MP_RUN_{HOLD}', 'ACT_HL2MP_RUN'], 'move': (0, 1)},
        {'activity': ['ACT_RUN'], 'move': (0, 1), 'layer': ['Run_Upper_{hold}']},
    ],
    'run_right': [
        {'activity': ['ACT_HL2MP_RUN_{HOLD}', 'ACT_HL2MP_RUN'], 'move': (0, -1)},
        {'activity': ['ACT_RUN'], 'move': (0, -1), 'layer': ['Run_Upper_{hold}']},
    ],
    'crouch_idle': [
        {'activity': ['ACT_HL2MP_IDLE_CROUCH_{HOLD}', 'ACT_HL2MP_IDLE_CROUCH']},
        {'activity': ['ACT_CROUCHIDLE'], 'layer': ['Crouch_Idle_Upper_{hold}']},
    ],
    'crouch_move': [
        {'activity': ['ACT_HL2MP_WALK_CROUCH_{HOLD}', 'ACT_HL2MP_WALK_CROUCH'], 'move': (1, 0)},
        {'activity': ['ACT_RUN_CROUCH'], 'move': (1, 0), 'layer': ['Crouch_Walk_Upper_{hold}']},
    ],
    'air': [
        {'activity': ['ACT_HL2MP_JUMP_{HOLD}', 'ACT_HL2MP_JUMP']},
        {'activity': ['ACT_HOP'], 'layer': ['Idle_Upper_{hold}']},
    ],
    'death': [
        # Real death animations only. CS:S and GMod players have none (they
        # ragdoll; ACT_DIE_*SIDE are ragdoll helper poses): the runtime then
        # topples the body itself.
        {'activity': ['ACT_DIESIMPLE', 'ACT_DIEBACKWARD', 'ACT_DIEFORWARD']},
    ],
}
# Roles a character must have; without them the package is refused.
CHARACTER_REQUIRED = ('idle', 'run_front')

# First-person weapon models: clips by viewmodel activity.
VIEWMODEL_ROLES = {
    'idle': ['ACT_VM_IDLE'],
    'fire': ['ACT_VM_PRIMARYATTACK'],
    'reload': ['ACT_VM_RELOAD'],
    'draw': ['ACT_VM_DRAW', 'ACT_VM_DEPLOY'],
}
VIEWMODEL_REQUIRED = ('idle', 'fire')

# Where a skeleton family holds things: the hand bone or attachment to
# look for, in order.
HAND_POINTS = ('anim_attachment_RH', 'ValveBiped.weapon_bone', 'ValveBiped.Bip01_R_Hand')

# Skeleton-family grips: a body that lacks a weapon bone its family's
# weapons bone-merge to gets one as an attachment on its hand. The ValveBiped
# grip was measured, not invented: CS:S's weapon_bone relative to
# Bip01_R_Hand while t_leet holds a rifle (ak_anims_t idle; run and crouch
# agree within ~1 degree). 3x4 row-major, Source units.
SYNTH_GRIPS = (
    {'name': 'ValveBiped.weapon_bone', 'on': 'ValveBiped.Bip01_R_Hand',
     'local': (-0.1263, -0.0185, 0.9918, 4.716,
               -0.9619, 0.2467, -0.1179, -0.972,
               -0.2425, -0.9689, -0.0490, -3.336)},
)
