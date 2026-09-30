"""Original small track-kit art and synthesized cues. No foreign assets."""
import math
import struct
from assetlab.assets import Texture, Material, Model, Sound, box_model
from assetlab.dependencies import Library

PACKAGE='racing.assets'
COLORS={
    'gate_pillar':(28,170,222),
    'gate_beam':(240,109,34),
    'pad':(30,220,190),
    'kart_shell':(235,55,130),
    'kart_nose':(244,218,63),
    'kart_dark':(19,24,39),
    'kart_glow':(31,225,246),
}
HALF={
    'gate_pillar':(0.18,0.18,1.65),
    'gate_beam':(0.18,4.15,0.16),
    'pad':(1.6,2.0,0.025),
}


def rid(kind,name): return f'racing:{kind}/{name}'


def tone(name, seconds, base, sweep=0, harmonics=0.0, fade=True):
    """Small deterministic PCM cue; engine_loop uses an exact 110 Hz period."""
    rate=16000
    count=int(rate*seconds)
    samples=[]
    phase=0.0
    for i in range(count):
        u=i/count
        hz=base+sweep*u
        phase+=2*math.pi*hz/rate
        env=(min(1.0,i/160.0)*min(1.0,(count-i)/240.0)) if fade else 1.0
        signal=math.sin(phase)+harmonics*math.sin(phase*2)
        samples.append(max(-32767,min(32767,int(signal*env*11000))))
    return Sound(rid('sound',name),rate,1,struct.pack('<'+'h'*count,*samples),
                 provenance={'origin':'original synthesized MegaMod Racing X10'})


def hyperkart():
    """One compact, readable procedural kart; +X is the exaggerated nose."""
    names=('kart_shell','kart_nose','kart_dark','kart_glow')
    materials=[rid('material',n) for n in names]
    parts=[
        ((0,0,0.25),(.78,.46,.13),0),
        ((.68,0,.24),(.32,.34,.095),1),
        ((-.64,0,.31),(.18,.4,.16),2),
        ((-.20,0,.48),(.32,.29,.19),2),
        ((-.17,0,.66),(.23,.23,.08),3),
        ((.2,.44,.27),(.52,.08,.09),0),
        ((.2,-.44,.27),(.52,.08,.09),0),
        ((-.46,.58,.20),(.21,.16,.19),2),
        ((-.46,-.58,.20),(.21,.16,.19),2),
        ((.48,.58,.20),(.21,.16,.19),2),
        ((.48,-.58,.20),(.21,.16,.19),2),
        ((-.88,.27,.31),(.13,.14,.11),3),
        ((-.88,-.27,.31),(.13,.14,.11),3),
    ]
    verts=[]; indices=[]; groups=[]
    for off,half,slot in parts:
        part=box_model('racing:model/part',half,[materials[slot]])
        first=len(indices); base=len(verts)
        verts += [(tuple(p[k]+off[k] for k in range(3)),n,uv) for p,n,uv in part.vertices]
        indices += [base+i for i in part.indices]
        groups.append((first,len(part.indices),slot))
    return Model(rid('model','hyperkart'),verts,indices,groups,materials,
                 provenance={'origin':'original procedural MegaMod Racing X10'})


def library():
    textures=[]; materials=[]; models=[]
    for name,color in sorted(COLORS.items()):
        pixels=bytes((*color,255))*16*16
        textures.append(Texture(rid('texture',name),16,16,pixels,
                                provenance={'origin':'original MegaMod Racing X10'}))
        materials.append(Material(rid('material',name),rid('texture',name),'opaque',
                                  provenance={'origin':'original MegaMod Racing X10'},emissive=0.8 if name!='gate_pillar' else 0.25))
        if name in HALF:
            models.append(box_model(rid('model',name),HALF[name],[rid('material',name)],
                                    provenance={'origin':'original MegaMod Racing X10'}))
    models.append(hyperkart())
    sounds=[tone('engine_loop',0.5,110,0,0.35,False),
            tone('drift',0.18,260,-90,0.5),
            tone('boost',0.34,180,420,0.4),
            tone('impact',0.15,95,-50,0.9),
            tone('checkpoint',0.22,620,290,0.1),
            tone('finish',0.55,520,470,0.3)]
    return Library(PACKAGE,display_name='MegaMod Racing track kit art',
                   textures=textures,materials=materials,models=models,sounds=sounds)
