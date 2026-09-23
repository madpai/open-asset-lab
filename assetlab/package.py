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
from .importers.source_bsp import BSPError, SourceBSP

MAGIC=b'OALM'
VERSION=1
MAX_TEXTURE=2048
HEADER='<4s8I6fI'  # 64 bytes
VMT_VALUE=re.compile(r'"?(\$[a-zA-Z0-9_]+)"?\s+"([^"\r\n]+)"',re.I)
FALLBACK=bytes((245,0,220,255, 24,24,24,255, 24,24,24,255, 245,0,220,255))


def _vtf_rgba(data):
    if len(data)<80 or data[:4]!=b'VTF\0':raise BSPError('invalid VTF header')
    major,minor,head=struct.unpack_from('<III',data,4)
    if major!=7 or minor>5 or head>len(data):raise BSPError('unsupported VTF version')
    w,h=struct.unpack_from('<HH',data,16)
    fmt=struct.unpack_from('<I',data,52)[0]
    mip=data[63]
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
    def __init__(self,bsp,roots=()):
        self.bsp=bsp
        pak=bsp.lump(40)
        self.zip=zipfile.ZipFile(io.BytesIO(pak)) if pak else None
        if self.zip:
            entries=self.zip.infolist()
            if len(entries)>10000 or any(e.file_size>64*1024*1024 for e in entries):raise BSPError('embedded pakfile resource limit exceeded')
            self.names={e.filename.lower():e.filename for e in entries}
        else:self.names={}
        self.roots=[Path(r).resolve() for r in roots]
        self.missing=[];self.warnings=[]

    def read(self,name):
        name=name.replace('\\','/').lstrip('/').lower()
        if '..' in Path(name).parts or '\0' in name:raise BSPError('unsafe material path')
        if name in self.names:return self.zip.read(self.names[name])
        for root in self.roots:
            p=(root/name).resolve()
            if p.is_relative_to(root) and p.is_file() and p.stat().st_size<64*1024*1024:return p.read_bytes()
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


def compile_map(source,output,material_roots=(),identifier=None):
    bsp=SourceBSP(source)
    world=bsp.convert()
    resolver=Resolver(bsp,material_roots)
    mats=sorted(set(g[0] for g in world.groups))
    textures=[(2,2,FALLBACK)]
    tex_for={}
    for name in mats:
        decoded=resolver.material(name)
        tex_for[name]=len(textures) if decoded else 0
        if decoded:textures.append(decoded)
    buckets={m:[] for m in mats}
    for mat,first,count in world.groups:buckets[mat].extend(world.indices[first:first+count])
    indices=[];groups=[]
    for mat in mats:
        first=len(indices);indices.extend(buckets[mat]);groups.append((first,len(indices)-first,tex_for[mat]))
    src=Path(source)
    source_hash=hashlib.sha256(src.read_bytes()).hexdigest()
    if identifier is None:identifier=re.sub('[^a-z0-9_-]+','-',src.stem.lower()).strip('-')[:64]
    manifest={
        'package_version':VERSION,'importer_version':'source_bsp-0.1.0','map_id':identifier,'display_name':src.stem,
        'source_format':'Source BSP','source_bsp_version':bsp.version,'source_sha256':source_hash,
        'source_reference':src.name,'coordinate_transform':{'axes':'Source xyz -> Open Halo xyz (right handed, +Z up)','scale':1/120,'source_unit':'inch','runtime_unit':'ten feet'},
        'required_open_halo_runtime':'external-map-v1','geometry':{'vertices':len(world.vertices),'triangles':len(indices)//3,'displacements':world.report['converted_displacements']},
        'material_paths':mats,'missing_dependencies':sorted(set(resolver.missing)),
        'supported_features':['world faces','power 2-4 displacement grids','spawn points','opaque albedo VTF subset'],
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
        for first,count,tex in groups:f.write(struct.pack('<4I',first,count,tex,0))
        for w,h,pixels in textures:
            f.write(struct.pack('<3I',w,h,len(pixels)));f.write(pixels)
        for sp in world.spawns:f.write(struct.pack('<4f',*sp['position'],math.radians(sp['yaw_degrees'])))
    report=world.report|{'missing_dependencies':manifest['missing_dependencies'],'material_warnings':resolver.warnings,
        'resolved_textures':len(textures)-1,'texture_bytes':sum(len(t[2]) for t in textures),'runtime_package_bytes':out.stat().st_size,
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
