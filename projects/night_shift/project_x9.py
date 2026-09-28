"""X9 visual production variant; X8 world and libraries remain pinned."""
import art_x9
import facility_x9
import world_x9

NAME = 'MegaMod: Night Shift X9'


def libraries():
    return {art_x9.PACKAGE: art_x9.library(), facility_x9.PACKAGE: facility_x9.library()}


def worlds():
    return [world_x9.world()]
