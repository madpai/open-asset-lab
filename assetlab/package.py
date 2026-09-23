"""OALMAP v1 compiler and Source material resolution."""
from __future__ import annotations
import hashlib
import io
import json
import math
import re
import struct
import zipfile
from pathlib import Path
from PIL import Image
from srctools.vpk import VPK
from .importers.source_bsp import BSPError, SourceBSP, SCALE, cross, sub, norm
from .importers.source_mdl import Model, angle_matrix

MAGIC=b'OALM'
VERSION=1
MAX_TEXTURE=2048
HEADER='<4s8I6fI'  # 64 bytes
GROUP_NO_COLLISION=1  # group record flags: drawn but not solid
VMT_VALUE=re.compile(r'"?(\$[a-zA-Z0-9_]+)"?\s+"([^"\r\n]+)"',re.I)

def _placeholder(name):
    """Muted, material-specific diagnostic colors for unresolved Source assets."""
    key=name.lower()
    palette=(
        (('grass','foliage','tree','leaf','nature'),(83,112,69)),
        (('wood','plank','timber'),(136,105,72)),
        (('brick','tile','roof'),(145,98,81)),
        (('concrete','cement','stone','rock'),(126,126,120)),
        (('metal','steel','iron'),(112,123,131)),
        (('water','river','glass'),(77,121,141)),
        (('dirt','ground','sand'),(131,112,84)),
    )
    base=next((color for words,color in palette if any(word in key for word in words)),(124,117,111))
    digest=hashlib.sha256(key.encode()).digest()
    # Variation is subtle enough to read map shapes; the report still identifies it as a placeholder.
    pixels=bytearray()
    for pixel in range(16):
        delta=digest[pixel]%11-5
        pixels.extend((*[max(0,min(255,c+delta)) for c in base],255))
    return 4,4,bytes(pixels)


def _vtf_rgba(data):
    if len(data)<80 or data[:4]!=b'VTF\0':raise BSPError('invalid VTF header')
    major,minor,head=struct.unpack_from('<III',data,4)
    if major!=7 or minor>5 or head>len(data):raise BSPError('unsupported VTF version')
    w,h=struct.unpack_from('<HH',data,16)
    fmt=struct.unpack_from('<I',data,52)[0]
    # VTF stores mipmapCount at byte 56; byte 63 is the optional depth field.
    mip=data[56]
    if not 0<w<=MAX_TEXTURE or not 0<h<=MAX_TEXTURE or mip<1 or mip>16:raise BSPError('VTF dimensions or mip count out of range')
    if fmt not in (0,12,13,15):raise BSPError(f'unsupported VTF image format {fmt}')
    def level_size(a,b):
        if fmt in (13,15):return max(1,(a+3)//4)*max(1,(b+3)//4)*(8 if fmt==13 else 16)
        return a*b*4
    high=head
    if minor>=3:
        count=struct.unpack_from('<I',data,68)[0]
        if count>32 or 80+count*8>head:raise BSPError('invalid VTF resource table')
        for i in range(count):
            tag=data[80+i*8:83+i*8]
            if tag==b'\x30\x00\x00':high=struct.unpack_from('<I',data,84+i*8)[0]
    else:
        lowfmt=struct.unpack_from('<I',data,57)[0];lw,lh=data[61:63]
        if lowfmt!=0xFFFFFFFF:high+=max(1,(lw+3)//4)*max(1,(lh+3)//4)*8
    # Mips are stored smallest first.
    pos=high
    for i in range(mip-1,0,-1):pos+=level_size(max(1,w>>i),max(1,h>>i))
    n=level_size(w,h)
    if pos+n>len(data):raise BSPError('truncated VTF high-resolution image')
    pixels=data[pos:pos+n]
    if fmt in (0,12):
        if fmt==12: # BGRA8888
            pixels=bytes(v for j in range(0,len(pixels),4) for v in (pixels[j+2],pixels[j+1],pixels[j],pixels[j+3]))
        return w,h,pixels
    dds=bytearray(128)
    dds[:4]=b'DDS '
    struct.pack_into('<I',dds,4,124)
    struct.pack_into('<I',dds,8,0x0002100F)
    struct.pack_into('<III',dds,12,h,w,n)
    struct.pack_into('<I',dds,76,32)
    struct.pack_into('<I',dds,80,4)
    dds[84:88]=b'DXT1' if fmt==13 else b'DXT5'
    struct.pack_into('<I',dds,108,0x1000)
    im=Image.open(io.BytesIO(dds+pixels)).convert('RGBA')
    return w,h,im.tobytes()


class Resolver:
    def __init__(self,bsp,roots=(),vpks=()):
        self.bsp=bsp
        pak=bsp.lump(40)
        self.zip=zipfile.ZipFile(io.BytesIO(pak)) if pak else None
        if self.zip:
            entries=self.zip.infolist()
            if len(entries)>10000 or any(e.file_size>64*1024*1024 for e in entries):raise BSPError('embedded pakfile resource limit exceeded')
            self.names={e.filename.lower():e.filename for e in entries}
        else:self.names={}
        self.roots=[Path(r).resolve() for r in roots]
        self.vpks=[]
        for path in vpks:
            archive=Path(path).resolve()
            if not archive.is_file() or not archive.name.lower().endswith('_dir.vpk'):
                raise BSPError(f'VPK directory file not found: {archive}')
            try:self.vpks.append(VPK(archive))
            except (OSError,ValueError) as e:raise BSPError(f'cannot read VPK {archive}: {e}') from e
        self.missing=[];self.warnings=[]

    def read(self,name):
        name=name.replace('\\','/').lstrip('/').lower()
        if '..' in Path(name).parts or '\0' in name:raise BSPError('unsafe material path')
        if name in self.names:return self.zip.read(self.names[name])
        for root in self.roots:
            p=(root/name).resolve()
            if p.is_relative_to(root) and p.is_file() and p.stat().st_size<64*1024*1024:return p.read_bytes()
        for archive in self.vpks:
            if name in archive:
                entry=archive[name]
                if entry.size>64*1024*1024:raise BSPError(f'VPK resource exceeds 64 MiB: {name}')
                try:return entry.read()
                except FileNotFoundError:
                    self.warnings.append(f'{name}: VPK entry is indexed but its data archive is unavailable')
                    continue
                except (OSError,ValueError) as e:raise BSPError(f'cannot read VPK resource {name}: {e}') from e
        return None

    def material(self,name):
        name=name.removesuffix('.vmt')
        path='materials/'+name+'.vmt'
        props=self._vmt_props(path,set())
        if props is None:return None
        base=props.get('$basetexture')
        if not base:
            self.warnings.append(f'{path}: no $basetexture');return None
        base=base.removesuffix('.vtf')
        tex='materials/'+base+'.vtf'
        raw=self.read(tex)
        if raw is None:self.missing.append(tex);return None
        try:return _vtf_rgba(raw)
        except BSPError as e:self.warnings.append(f'{tex}: {e}');return None

    def _vmt_props(self,path,seen):
        if path in seen or len(seen)>4:
            self.warnings.append(f'{path}: VMT include cycle or depth limit');return None
        seen.add(path)
        raw=self.read(path)
        if raw is None:self.missing.append(path);return None
        body=raw.decode('utf-8','replace')
        props={k.lower():v.strip().lower().replace('\\','/') for k,v in VMT_VALUE.findall(body)}
        include=re.search(r'"?include"?\s+"([^"\r\n]+)"',body,re.I)
        inherited={}
        if include:
            parent=include[1].replace('\\','/').lower().lstrip('/')
            if not parent.startswith('materials/'):parent='materials/'+parent
            if not parent.endswith('.vmt'):parent+='.vmt'
            inherited=self._vmt_props(parent,seen) or {}
        return inherited|props


def add_static_props(world,bsp,resolver):
    """Static prop models placed into the world triangles. Returns
    (placed, model names that could not be read)."""
    cache={};failed=set();placed=0
    exists=lambda m:resolver.read('materials/'+m+'.vmt') is not None
    for path,origin,angles,skin,_solid in bsp.static_prop_placements():
        key=(path,skin)
        if key not in cache:
            base=path.removesuffix('.mdl')
            try:
                mdl,vvd,vtx=(resolver.read(base+ext) for ext in ('.mdl','.vvd','.dx90.vtx'))
                if mdl is None or vvd is None or vtx is None:
                    for ext,blob in (('.mdl',mdl),('.vvd',vvd),('.dx90.vtx',vtx)):
                        if blob is None:resolver.missing.append(base+ext)
                    cache[key]=None
                else:cache[key]=Model(mdl,vvd,vtx,skin,exists)
            except BSPError as e:
                resolver.warnings.append(f'{path}: {e}');cache[key]=None
        model=cache[key]
        if model is None:failed.add(path);continue
        m=angle_matrix(*angles)
        rot=lambda v:tuple(sum(m[r][c]*v[c] for c in range(3)) for r in range(3))
        for mat,tris in model.groups.items():
            start=len(world.indices)
            for t in range(0,len(tris),3):
                corners=[]
                for pos,nrm,uv in tris[t:t+3]:
                    wp=rot(pos);corners.append((tuple((wp[k]+origin[k])*SCALE for k in range(3)),norm(rot(nrm)),uv))
                a,b,c=corners
                face=cross(sub(b[0],a[0]),sub(c[0],a[0]))
                if face==(0.,0.,0.) or norm(face)==(0.,0.,0.):continue
                # Wind to agree with the model's own normals, whatever the source order.
                if sum(face[k]*(a[1][k]+b[1][k]+c[1][k]) for k in range(3))<0:b,c=c,b
                i0=len(world.vertices);world.vertices.extend((a,b,c));world.indices.extend((i0,i0+1,i0+2))
            # Source SOLID_NONE props are drawn, not collided with.
            if len(world.indices)>start:world.groups.append((mat,start,len(world.indices)-start,_solid!=0))
        placed+=1
    return placed,sorted(failed)


def compile_map(source,output,material_roots=(),identifier=None,vpks=()):
    bsp=SourceBSP(source)
    world=bsp.convert()
    resolver=Resolver(bsp,material_roots,vpks)
    props_placed,props_failed=add_static_props(world,bsp,resolver)
    world.report['static_props_placed']=props_placed
    world.report['static_props_unresolved']=props_failed
    mats=sorted(set(g[0] for g in world.groups))
    textures=[]
    tex_for={}
    placeholders=[];resolved=0
    for name in mats:
        decoded=resolver.material(name)
        tex_for[name]=len(textures)
        if decoded:resolved+=1;textures.append(decoded)
        else:placeholders.append(name);textures.append(_placeholder(name))
    buckets={}
    for g in world.groups:
        mat,first,count=g[:3];solid=g[3] if len(g)>3 else True
        buckets.setdefault((mat,solid),[]).extend(world.indices[first:first+count])
    indices=[];groups=[]
    for mat,solid in sorted(buckets,key=lambda k:(k[0],not k[1])):
        first=len(indices);indices.extend(buckets[(mat,solid)])
        groups.append((first,len(indices)-first,tex_for[mat],0 if solid else GROUP_NO_COLLISION))
    src=Path(source)
    source_hash=hashlib.sha256(src.read_bytes()).hexdigest()
    if identifier is None:identifier=re.sub('[^a-z0-9_-]+','-',src.stem.lower()).strip('-')[:64]
    manifest={
        'package_version':VERSION,'importer_version':'source_bsp-0.1.0','map_id':identifier,'display_name':src.stem,
        'source_format':'Source BSP','source_bsp_version':bsp.version,'source_sha256':source_hash,
        'source_reference':src.name,'coordinate_transform':{'axes':'Source xyz -> Open Halo xyz (right handed, +Z up)','scale':1/120,'source_unit':'inch','runtime_unit':'ten feet'},
        'required_open_halo_runtime':'external-map-v1','geometry':{'vertices':len(world.vertices),'triangles':len(indices)//3,'displacements':world.report['converted_displacements']},
        'material_paths':mats,'missing_dependencies':sorted(set(resolver.missing)),
        'placeholder_materials':placeholders,
        'supported_features':['world faces','power 2-4 displacement grids','static prop models (MDL v44-48, LOD 0)','spawn points','opaque albedo VTF subset'],'static_props_placed':props_placed,'static_props_unresolved':props_failed,
        'unsupported_features':world.report['unsupported_features'],
        'conversion_warnings':world.report['warnings']+resolver.warnings,
        'static_prop_count':bsp.inspect()['static_props']['count'],'static_prop_models':bsp.inspect()['static_props']['models'],
        'entity_classes':bsp.inspect()['entity_classes'],'supported_entity_classes':bsp.inspect()['supported_entity_classes'],'unsupported_entity_classes':bsp.inspect()['unsupported_entity_classes'],'entities':world.entities,'spawn_points':world.spawns,
        'bounds':world.report['converted_bounds'],'texture_count':len(textures),
        'source_provenance':'user supplied; redistribution rights not inferred',
    }
    manifest_bytes=json.dumps(manifest,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(manifest_bytes)>4*1024*1024:raise BSPError('runtime manifest exceeds 4 MiB limit')
    lo=world.report['converted_bounds']['min'];hi=world.report['converted_bounds']['max']
    out=Path(output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as f:
        f.write(struct.pack(HEADER,MAGIC,VERSION,len(manifest_bytes),len(world.vertices),len(indices),len(groups),len(textures),len(world.spawns),0,*lo,*hi,0))
        f.write(manifest_bytes)
        for pos,nrm,uv in world.vertices:f.write(struct.pack('<10f',*pos,*nrm,*uv,0.,0.))
        for i in indices:f.write(struct.pack('<I',i))
        for first,count,tex,flags in groups:f.write(struct.pack('<4I',first,count,tex,flags))
        for w,h,pixels in textures:
            f.write(struct.pack('<3I',w,h,len(pixels)));f.write(pixels)
        for sp in world.spawns:f.write(struct.pack('<4f',*sp['position'],math.radians(sp['yaw_degrees'])))
    report=world.report|{'missing_dependencies':manifest['missing_dependencies'],'material_warnings':resolver.warnings,
        'resolved_textures':resolved,'placeholder_materials':placeholders,'texture_bytes':sum(len(t[2]) for t in textures),'runtime_package_bytes':out.stat().st_size,
        'runtime_package_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
    return manifest,report


def read_manifest(package):
    with Path(package).open('rb') as f:
        h=f.read(64)
        if len(h)!=64:raise BSPError('truncated package header')
        magic,version,mlen,vc,ic,gc,tc,sc,flags,*_=struct.unpack(HEADER,h)
        if magic!=MAGIC or version!=VERSION:raise BSPError('invalid or unsupported package version')
        if mlen>4*1024*1024 or vc>5000000 or ic>15000000 or gc>100000 or tc>10000 or sc>100000:raise BSPError('package counts out of range')
        m=f.read(mlen)
        if len(m)!=mlen:raise BSPError('truncated package manifest')
        return json.loads(m)
