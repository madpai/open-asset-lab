"""Normalized rigid models with optional authored root motion, existing OALA1.

Foreign skeletal clips are not inferred. View and world geometry can differ;
procedural root clips are explicit authoring data, recorded in the manifest.
"""
import hashlib
import json
import math
import struct
from pathlib import Path
from .assets import validate,AssetError

def _chunk(model,materials,textures,clips):
    errors=validate(textures,materials,[model],[])
    if errors:raise AssetError('; '.join(errors))
    mats={m.id:m for m in materials};tex={t.id:t for t in textures}
    chosen=[tex[mats[mid].texture] for mid in model.materials]
    vertices=b''.join(struct.pack('<8f4B3f',*p,*n,*uv,0,0,0,0,1,0,0) for p,n,uv in model.vertices)
    indices=struct.pack('<'+str(len(model.indices))+'I',*model.indices)
    groups=b''.join(struct.pack('<4I',first,count,slot,2 if mats[model.materials[slot]].draw=='alpha' else 0) for first,count,slot in model.groups)
    pixels=b''.join(struct.pack('<3I',t.width,t.height,len(t.rgba))+t.rgba for t in chosen)
    root=struct.pack('<64si12f3f4f',b'root',-1,1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,1)
    animation=[];infos=[]
    for role,c in (clips or {}).items():
        frames=c['frames'];fps=c.get('fps',30);loop=bool(c.get('loop',role=='idle'))
        if not isinstance(role,str) or not role.isascii() or not 0<len(role)<16 or not 0<fps<=240 or not 1<=len(frames)<=600:raise AssetError('invalid authored root clip')
        for frame in frames:
            if len(frame)!=7 or not all(math.isfinite(x) for x in frame) or abs(sum(x*x for x in frame[:4])-1)>.001:raise AssetError('invalid root keyframe/quaternion')
        animation.append(struct.pack('<16sfII',role.encode(),fps,len(frames),int(loop))+b''.join(struct.pack('<7f',*f) for f in frames))
        infos.append({'role':role,'fps':fps,'frames':len(frames),'loop':loop,'source':'authored procedural root motion'})
    chunk=struct.pack('<8I',len(model.vertices),len(model.indices),len(model.groups),len(chosen),1,0,len(animation),0)+vertices+indices+groups+pixels+root+b''.join(animation)
    return chunk,{'vertices':len(model.vertices),'triangles':len(model.indices)//3,'bones':['root'],'clips':infos}

def build(output,model,materials,textures,*,name,display,kind='character',metadata=None,view_model=None,clips=None,view_clips=None):
    if kind not in ('character','weapon'):raise AssetError('rigid actor kind must be character or weapon')
    chunk,info=_chunk(model,materials,textures,clips);chunks=[chunk];infos=[info]
    if kind=='weapon':
        chunk,info=_chunk(view_model or model,materials,textures,view_clips if view_clips is not None else clips);chunks.append(chunk);infos.append(info)
    manifest={'asset_version':1,'kind':kind,'name':name,'display_name':display,'models':infos,'source_provenance':model.provenance,'warnings':['Rigid stored-pose fallback: no imported skeletal animation'],**(metadata or {})}
    blob=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode();out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(struct.pack('<4sIIII12x',b'OALA',1,len(blob),len(chunks),0)+blob+b''.join(chunks))
    return dict(manifest,package_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),package_bytes=out.stat().st_size)
