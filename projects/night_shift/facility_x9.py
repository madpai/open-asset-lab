"""Same gameplay prefabs, linked to the visual art package."""
from assetlab.resources import Requirement
import facility
import art_x9

PACKAGE = 'nightshift.facility_x9'


def library():
    lib = facility.library()
    lib.id = PACKAGE
    lib.requires = [Requirement(art_x9.PACKAGE, list(r.resources)) for r in lib.requires]
    return lib
