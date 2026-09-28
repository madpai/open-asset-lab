"""Build the separate X8 Harrow Annex proof without changing world01."""
import art
import facility
import world_x8

NAME = 'MegaMod: Night Shift X8'


def libraries():
    return {art.PACKAGE: art.library(), facility.PACKAGE: facility.library()}


def worlds():
    return [world_x8.world()]
