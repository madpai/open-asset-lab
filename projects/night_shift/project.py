"""MegaMod: Night Shift -- the content project Open Asset Lab builds.

    assetlab project build projects/night_shift --output <bundle dir>

writes packages/<id>.oalasset for each library and maps/<file>.oalmap for
each world, and reports what was built (resources, prefabs, the expanded
entity budget, bindings, world keys).

Packages:
  nightshift.assets    textures, materials, models, sounds (art.py)
  nightshift.facility  prefabs (facility.py); requires nightshift.assets
  nightshift.world01   the world HARROW ANNEX (world01.py) and its Lua;
                       requires both
"""
import art
import facility
import world01

NAME = 'MegaMod: Night Shift'


def libraries():
    return {art.PACKAGE: art.library(), facility.PACKAGE: facility.library()}


def worlds():
    return [world01.world()]
