"""Reusable original gate and pad compositions."""
from assetlab.dependencies import Library
from assetlab.prefabs import Prefab, PrefabChild
from assetlab.resources import Requirement
import race_art as art

PACKAGE='racing.trackkit'


def library():
    C=PrefabChild
    gate=Prefab(art.rid('prefab','checkpoint_gate'),[
        C('beam','prop',position=(0,0,3.4),model=art.rid('model','gate_beam')),
        C('left','prop',position=(0,4.0,1.65),model=art.rid('model','gate_pillar')),
        C('right','prop',position=(0,-4.0,1.65),model=art.rid('model','gate_pillar')),
    ],provenance={'origin':'original MegaMod Racing X10'})
    pad=Prefab(art.rid('prefab','boost_pad'),[
        C('plate','prop',position=(0,0,-0.04),model=art.rid('model','pad')),
    ],provenance={'origin':'original MegaMod Racing X10'})
    models=[art.rid('model',name) for name in sorted(art.HALF)]
    return Library(PACKAGE,requires=[Requirement(art.PACKAGE,models)],
                   display_name='MegaMod Racing reusable track elements',prefabs=[pad,gate])
