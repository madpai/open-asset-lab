"""Build with `assetlab project build projects/megamod_racing --output DIR`."""
import race_art as art
import race_trackkit as trackkit
import race_track01 as track01

NAME='MegaMod Racing: Cinder Circuit'


def libraries(): return {art.PACKAGE:art.library(),trackkit.PACKAGE:trackkit.library()}


def worlds(): return [track01.world()]
