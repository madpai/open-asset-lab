"""Conservative Source 1 BSP v20 reader. Format definitions: Valve source-sdk-2013 bspfile.h."""
from __future__ import annotations
import io
import lzma
import math
import re
import struct
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

MAX_FILE = 512 * 1024 * 1024
SCALE = 1.0 / 120.0  # Source inch to Open Halo ten-foot world unit; axes unchanged.
SIZES = {1: 20, 2: 32, 3: 12, 6: 72, 7: 56, 12: 4, 13: 4, 14: 48, 26: 176, 33: 20, 44: 4}
SPAWN_CLASSES = {'info_player_start','info_player_deathmatch','info_player_teamspawn','info_player_counterterrorist','info_player_terrorist'}
ENTITY = re.compile(rb'"((?:\\.|[^"\\])*)"\s*"((?:\\.|[^"\\])*)"')

class BSPError(ValueError):
    pass


def unpack(fmt, data, off=0):
    size = struct.calcsize(fmt)
    if off < 0 or off + size > len(data):
        raise BSPError(f"read outside lump at {off} ({size} bytes)")
    return struct.unpack_from(fmt, data, off)


def vec3(v):
    return tuple(float(x) * SCALE for x in v)


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def sub(a, b):
    return tuple(x-y for x,y in zip(a,b))


def norm(v):
    n = math.sqrt(sum(x*x for x in v))
    return tuple(x/n for x in v) if n > 1e-12 else (0.0,0.0,0.0)


@dataclass
class World:
    vertices: list  # pos, normal, uv
    indices: list
    groups: list  # material, first index, count
    spawns: list
    materials: list
    entities: list
    report: dict


class SourceBSP:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.stat().st_size > MAX_FILE:
            raise BSPError("BSP exceeds 512 MiB input limit")
        self.data = self.path.read_bytes()
        b = self.data
        if len(b) < 1036:
            raise BSPError("truncated BSP header")
        if b[:4] != b'VBSP':
            raise BSPError("invalid Source BSP magic (expected VBSP)")
        self.version = unpack('<I', b, 4)[0]
        if self.version != 20:
            raise BSPError(f"unsupported BSP version {self.version}; only Source v20 is implemented")
        if unpack('<I', b, 8+7*16+8)[0] != 1:
            raise BSPError('unsupported face lump version; Source v20 face layout v1 required')
        self.revision = unpack('<I', b, 1032)[0]
        self.lumps = []
        for i in range(64):
            off, length, version, fourcc = unpack('<4I', b, 8 + 16*i)
            if off > len(b) or length > len(b) - off:
                raise BSPError(f"lump {i} outside file (offset={off}, length={length})")
            if length > MAX_FILE:
                raise BSPError(f"lump {i} exceeds size limit")
            self.lumps.append((off,length,version,fourcc))
        self._cache = {}
        for i,size in SIZES.items():
            d = self.lump(i)
            if len(d) % size:
                raise BSPError(f"lump {i} has invalid record size {len(d)} for {size}-byte records")
        self.entities = self._entities()
        self.materials = self._materials()

    def lump(self, i):
        if i in self._cache:
            return self._cache[i]
        off,n,_,fourcc = self.lumps[i]
        d = self.data[off:off+n]
        if n and (fourcc or d[:4] == b'LZMA'):
            if len(d) < 17 or d[:4] != b'LZMA':
                raise BSPError(f"lump {i} has unsupported compression")
            raw_n, zipped_n = unpack('<II',d,4)
            if raw_n > MAX_FILE or zipped_n != len(d)-17 or (fourcc and fourcc != raw_n):
                raise BSPError(f"lump {i} invalid compressed size")
            p=d[12]; lc=p%9; lp=(p//9)%5; pb=p//45
            if pb>4:
                raise BSPError(f"lump {i} invalid LZMA properties")
            dictionary=unpack('<I',d,13)[0]
            if dictionary<4096 or dictionary>64*1024*1024:raise BSPError(f'lump {i} invalid LZMA dictionary size')
            try:
                d=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=[dict(id=lzma.FILTER_LZMA1,dict_size=dictionary,lc=lc,lp=lp,pb=pb)]).decompress(d[17:], max_length=raw_n+1)
            except lzma.LZMAError as e:
                raise BSPError(f"lump {i} LZMA decompression failed: {e}") from e
            if len(d)<raw_n:
                raise BSPError(f"lump {i} decompressed length mismatch")
            d=d[:raw_n]
        self._cache[i]=d
        return d

    def _entities(self):
        d=self.lump(0)
        entities=[]
        # Entity blocks are braced; quoted values may contain braces.
        for block in re.findall(rb'\{([^{}]*)\}',d):
            pairs=ENTITY.findall(block)
            if pairs:
                entities.append({k.decode('utf-8','replace'):v.decode('utf-8','replace').replace('\\"','"') for k,v in pairs})
        return entities

    def _materials(self):
        td=self.lump(2); names=self.lump(43); table=self.lump(44)
        out=[]
        for i in range(len(td)//32):
            name_id=unpack('<i',td,i*32+12)[0]
            if name_id<0 or name_id>=len(table)//4:
                raise BSPError(f"texdata {i} invalid material name index")
            off=unpack('<i',table,name_id*4)[0]
            if off<0 or off>=len(names):
                raise BSPError(f"texdata {i} material string outside lump")
            end=names.find(b'\0',off)
            if end<0:
                raise BSPError(f"texdata {i} material string not terminated")
            out.append(names[off:end].decode('utf-8','replace').replace('\\','/').lower())
        return out

    def _models(self):
        d=self.lump(14)
        return [(unpack('<i',d,o+40)[0],unpack('<i',d,o+44)[0],unpack('<6f',d,o)) for o in range(0,len(d),48)]

    def static_prop_placements(self):
        """Every static prop: (model path, origin, angles, skin, solid). The
        leading fields are the same in lump versions 4 to 10; the record
        size is whatever divides the rest of the lump."""
        d=self.lump(35)
        if len(d)<4:return []
        n=unpack('<i',d)[0]
        if n<0 or n>4096 or 4+n*16>len(d):raise BSPError('invalid game lump directory')
        for i in range(n):
            tag,flags,version,off,length=unpack('<IHHii',d,4+i*16)
            if tag!=int.from_bytes(b'prps','little'):continue
            if flags&1 or not 4<=version<=10:return []
            if off<0 or length<0 or off+length>len(self.data):raise BSPError('static prop game lump outside file')
            p=self.data[off:off+length]
            model_n=unpack('<i',p)[0]
            if model_n<0 or model_n>65536:raise BSPError('invalid static prop model dictionary')
            models=[p[4+j*128:4+(j+1)*128].split(b'\0',1)[0].decode('utf-8','replace').replace('\\','/').lower() for j in range(model_n)]
            pos=4+model_n*128
            leaf_n=unpack('<i',p,pos)[0];pos+=4
            if leaf_n<0:raise BSPError('invalid static prop leaf table')
            pos+=leaf_n*2
            count=unpack('<i',p,pos)[0];pos+=4
            if count<=0:return []
            if count>100000 or (len(p)-pos)%count:raise BSPError('static prop records do not divide the lump')
            size=(len(p)-pos)//count
            if size<32:raise BSPError('static prop record too small')
            out=[]
            for k in range(count):
                o=pos+k*size
                origin=unpack('<3f',p,o);angles=unpack('<3f',p,o+12);mt=unpack('<H',p,o+24)[0];solid=p[o+30]
                skin=unpack('<i',p,o+32)[0] if size>=36 else 0
                if mt>=len(models):raise BSPError('static prop model index out of range')
                out.append((models[mt],origin,angles,skin,solid))
            return out
        return []

    def _static_props(self):
        d=self.lump(35)
        if len(d)<4:return {'count':0,'models':[],'supported':False}
        n=unpack('<i',d)[0]
        if n<0 or n>4096 or 4+n*16>len(d):raise BSPError('invalid game lump directory')
        for i in range(n):
            tag,flags,version,off,length=unpack('<IHHii',d,4+i*16)
            if tag != int.from_bytes(b'prps','little'):continue
            # Game lump offsets are absolute file offsets. FourCC on disk is sprp bytes reversed.
            if off<0 or length<0 or off+length>len(self.data):raise BSPError('static prop game lump outside file')
            p=self.data[off:off+length]
            if version!=10:return {'count':None,'models':[],'supported':False,'version':version,'warning':'unsupported static prop version'}
            if flags & 1:
                if p[:4]!=b'LZMA':raise BSPError('unsupported static prop compression')
                raw_n,zipped_n=unpack('<II',p,4)
                if raw_n!=length or zipped_n>len(self.data)-off-17 or raw_n>MAX_FILE:raise BSPError('invalid compressed static prop size')
                q=self.data[off:off+17+zipped_n];prop=q[12];dictionary=unpack('<I',q,13)[0]
                if dictionary<4096 or dictionary>64*1024*1024:raise BSPError('invalid static prop LZMA dictionary')
                try:p=lzma.LZMADecompressor(format=lzma.FORMAT_RAW,filters=[dict(id=lzma.FILTER_LZMA1,dict_size=dictionary,lc=prop%9,lp=(prop//9)%5,pb=prop//45)]).decompress(q[17:],max_length=raw_n+1)[:raw_n]
                except lzma.LZMAError as e:raise BSPError(f'static prop decompression failed: {e}') from e
                if len(p)!=raw_n:raise BSPError('static prop decompressed length mismatch')
            model_n=unpack('<i',p)[0]
            if model_n<0 or model_n>65536 or 4+model_n*128+4>len(p):raise BSPError('invalid static prop model dictionary')
            models=[p[4+j*128:4+(j+1)*128].split(b'\0',1)[0].decode('utf-8','replace') for j in range(model_n)]
            pos=4+model_n*128
            leaf_n=unpack('<i',p,pos)[0];pos+=4
            if leaf_n<0 or pos+leaf_n*2+4>len(p):raise BSPError('invalid static prop leaf table')
            pos+=leaf_n*2
            count=unpack('<i',p,pos)[0]
            if count<0 or count>100000:raise BSPError('invalid static prop count')
            return {'count':count,'models':models,'supported':True,'version':version}
        return {'count':0,'models':[],'supported':True}

    def inspect(self):
        models=self._models();face_n=len(self.lump(7))//56
        props=self._static_props()
        pak=self.lump(40)
        embedded=[]
        if pak:
            try:
                with zipfile.ZipFile(io.BytesIO(pak)) as z:
                    entries=z.infolist()
                    if len(entries)>10000 or any(x.file_size>64*1024*1024 for x in entries):raise BSPError('embedded pakfile resource count or size exceeds limit')
                    embedded=[x.filename for x in entries]
            except zipfile.BadZipFile:raise BSPError('embedded pakfile is invalid ZIP')
        return {'source_format':'Source BSP','bsp_version':self.version,'map_revision':self.revision,
            'source_bytes':len(self.data),'world_bounds_source':{'min':models[0][2][:3],'max':models[0][2][3:6]} if models else None,
            'face_count':face_n,'world_face_count':models[0][1] if models else 0,'vertex_count':len(self.lump(3))//12,
            'displacement_count':len(self.lump(26))//176,'material_count':len(set(self.materials)),
            'entity_count':len(self.entities),'entity_classes':dict(Counter(e.get('classname','?') for e in self.entities)),
            'supported_entity_classes':dict(Counter(e.get('classname','?') for e in self.entities if e.get('classname') in SPAWN_CLASSES)),
            'unsupported_entity_classes':dict(Counter(e.get('classname','?') for e in self.entities if e.get('classname') not in SPAWN_CLASSES)),
            'static_props':props,'embedded_resources':len(embedded),'embedded_vmt':sum(x.lower().endswith('.vmt') for x in embedded),
            'embedded_vtf':sum(x.lower().endswith('.vtf') for x in embedded),
            'compressed_lumps':[i for i,(o,n,v,f) in enumerate(self.lumps) if n and f],
            'unsupported_features':['brush entities, physics brushes, dynamic entities, visibility, Source lightmaps, static prop rendering']}

    def convert(self):
        vdata=self.lump(3);edges=self.lump(12);surf=self.lump(13);faces=self.lump(7);planes=self.lump(1);texinfo=self.lump(6);td=self.lump(2);disp=self.lump(26);dv=self.lump(33)
        models=self._models()
        if not models:raise BSPError('world model missing')
        first,count,_=models[0]
        if first<0 or count<0 or first+count>len(faces)//56:raise BSPError('invalid world face range')
        vertices=[];indices=[];groups=[];warnings=[];disps_done=0;degenerate=0
        material_tri=Counter()
        def point(index):
            if index<0 or index>=len(vdata)//12:raise BSPError(f'invalid vertex index {index}')
            return unpack('<3f',vdata,index*12)
        def addtri(a,b,c,mat,uvfn,normal,fixed=False):
            nonlocal degenerate
            pa,pb,pc=vec3(a),vec3(b),vec3(c)
            n=norm(cross(sub(pb,pa),sub(pc,pa)))
            if n==(0.,0.,0.):degenerate+=1;return
            if fixed:normal=n
            elif sum(n[i]*normal[i] for i in range(3))<0:
                b,c=c,b;pb,pc=pc,pb
            start=len(vertices)
            for p in (a,b,c):vertices.append((vec3(p),normal,uvfn(p)))
            indices.extend((start,start+1,start+2));material_tri[mat]+=1
            if groups and groups[-1][0]==mat and groups[-1][1]+groups[-1][2]==len(indices)-3:
                m,s,n0=groups[-1];groups[-1]=(m,s,n0+3)
            else:groups.append((mat,len(indices)-3,3))
        for fi in range(first,first+count):
            o=fi*56
            plane,side,_,firstedge,numedges,ti,di=unpack('<HBBihhh',faces,o)
            if numedges<3:continue
            if firstedge<0 or firstedge+numedges>len(surf)//4:raise BSPError(f'face {fi} invalid surfedge range')
            if ti<0 or ti>=len(texinfo)//72:continue
            to=ti*72
            flags,tdi=unpack('<ii',texinfo,to+64)
            if tdi<0 or tdi>=len(self.materials):raise BSPError(f'face {fi} invalid texdata index')
            mat=self.materials[tdi]
            # SKY, NODRAW, HINT, SKIP, TRIGGER. Retain metadata but exclude invisible surfaces.
            if flags & (0x2|0x4|0x40|0x80|0x100|0x200):continue
            uvec=unpack('<4f',texinfo,to);vvec=unpack('<4f',texinfo,to+16)
            width,height=unpack('<ii',td,tdi*32+16)
            if width<=0 or height<=0:raise BSPError(f'face {fi} invalid texture dimensions')
            uvfn=lambda p:((sum(p[k]*uvec[k] for k in range(3))+uvec[3])/width,(sum(p[k]*vvec[k] for k in range(3))+vvec[3])/height)
            polygon=[]
            for k in range(numedges):
                ei=unpack('<i',surf,(firstedge+k)*4)[0]
                if abs(ei)>=len(edges)//4:raise BSPError(f'face {fi} invalid edge index {ei}')
                a,b=unpack('<HH',edges,abs(ei)*4)
                polygon.append(point(a if ei>=0 else b))
            if plane>=len(planes)//20:raise BSPError(f'face {fi} invalid plane index')
            base=norm(unpack('<3f',planes,plane*20))
            if side:base=tuple(-x for x in base)
            if base==(0.,0.,0.):degenerate+=1;continue
            if di>=0:
                if di>=len(disp)//176:raise BSPError(f'face {fi} invalid displacement index')
                if numedges!=4:raise BSPError(f'face {fi} displacement base has {numedges} edges')
                do=di*176
                startpos=unpack('<3f',disp,do);dvstart,dtstart,power=unpack('<iii',disp,do+12)
                if power not in (2,3,4):raise BSPError(f'face {fi} unsupported displacement power {power}')
                side_n=(1<<power)+1
                if dvstart<0 or dvstart+side_n*side_n>len(dv)//20:raise BSPError(f'face {fi} displacement vertex range invalid')
                corner=min(range(4),key=lambda j:sum((polygon[j][k]-startpos[k])**2 for k in range(3)))
                p0,p1,p2,p3=(polygon[(corner+j)%4] for j in range(4))
                # Valve CCoreDispInfo layout: the outer (row) index advances
                # p0->p1 and the inner (column) index advances p0->p3.
                grid=[]
                for y in range(side_n):
                    row=[]
                    s=y/(side_n-1)
                    for x in range(side_n):
                        t=x/(side_n-1)
                        basepos=tuple((1-s)*(1-t)*p0[k]+s*(1-t)*p1[k]+s*t*p2[k]+(1-s)*t*p3[k] for k in range(3))
                        vv=unpack('<5f',dv,(dvstart+y*side_n+x)*20)
                        row.append(tuple(basepos[k]+vv[k]*vv[3] for k in range(3)))
                    grid.append(row)
                # Choose one winding for the whole surface from the flat base
                # quad so folded or overhanging terrain keeps consistent facing.
                flip=sum(cross(sub(p1,p0),sub(p3,p0))[k]*base[k] for k in range(3))<0
                for y in range(side_n-1):
                    for x in range(side_n-1):
                        a,b,c,d=grid[y][x],grid[y+1][x],grid[y+1][x+1],grid[y][x+1]
                        if flip:b,d=d,b
                        # Alternate diagonals like Source to avoid directional creases.
                        if (x+y)%2:addtri(a,b,c,mat,uvfn,base,True);addtri(a,c,d,mat,uvfn,base,True)
                        else:addtri(a,b,d,mat,uvfn,base,True);addtri(b,c,d,mat,uvfn,base,True)
                disps_done+=1
            else:
                for j in range(1,len(polygon)-1):addtri(polygon[0],polygon[j],polygon[j+1],mat,uvfn,base)
        if not indices:raise BSPError('world geometry is empty')
        spawns=[]
        for e in self.entities:
            if e.get('classname') not in SPAWN_CLASSES:continue
            try:
                p=tuple(float(x) for x in e['origin'].split())
                if len(p)!=3:continue
                yaw=float(e.get('angles','0 0 0').split()[1]) if 'angles' in e else float(e.get('angle','0'))
                spawns.append({'position':vec3(p),'yaw_degrees':yaw,'classname':e['classname']})
            except (ValueError,KeyError,IndexError):warnings.append('malformed player spawn entity')
        # Source spawn origins vary by game; project onto our walkable collision
        # triangles rather than assuming a fixed origin-to-feet offset.
        for sp in spawns:
            x,y,z=sp['position'];best=None
            for t in range(0,len(indices),3):
                a,b,c=(vertices[indices[t+j]][0] for j in range(3))
                if x<min(a[0],b[0],c[0]) or x>max(a[0],b[0],c[0]) or y<min(a[1],b[1],c[1]) or y>max(a[1],b[1],c[1]):continue
                det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
                if abs(det)<1e-12:continue
                u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det
                v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det
                if u<-.0001 or v<-.0001 or u+v>1.0001:continue
                nz=norm(cross(sub(b,a),sub(c,a)))[2]
                if abs(nz)<.5:continue
                gz=u*a[2]+v*b[2]+(1-u-v)*c[2]
                if gz<=z+.2 and (best is None or gz>best):best=gz
            sp['source_origin']=sp['position']
            if best is not None and z-best<1.5:
                sp['position']=(x,y,best)
                sp['ground_delta']=z-best
            else:warnings.append(f"spawn at {x:.2f},{y:.2f},{z:.2f} has no nearby walkable ground")
        bounds_min=[min(v[0][k] for v in vertices) for k in range(3)]
        bounds_max=[max(v[0][k] for v in vertices) for k in range(3)]
        if max(bounds_max[k]-bounds_min[k] for k in range(3))>1000:raise BSPError('converted bounds implausibly large')
        report=self.inspect()
        report.update({'converted_vertices':len(vertices),'converted_triangles':len(indices)//3,
            'converted_displacements':disps_done,'degenerate_triangles':degenerate,'converted_bounds':{'min':bounds_min,'max':bounds_max},
            'used_materials':dict(material_tri),'spawns':spawns,'warnings':warnings})
        if disps_done!=report['displacement_count']:warnings.append(f"{report['displacement_count']-disps_done} displacements not in visible world geometry")
        if not spawns:warnings.append('no supported player spawn entity')
        return World(vertices,indices,groups,spawns,self.materials,self.entities,report)
