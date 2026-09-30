"""Experimental NIF 20.0.0.4 diffuse geometry -> normalized Model resources.

PyFFI is an optional offline decoder, isolated from the native engine. Strict
mode rejects animated/skinned geometry. Explicit freeze mode imports the stored
pose and reports discarded controllers/skin/particles. No KF or Havok support.
"""
import hashlib
import io
import math
from pathlib import PurePosixPath
from ..assets import Model,Material,Texture,AssetError

MAX_BYTES=64*1024*1024

def read_nif(raw, texture_fetch, namespace, name, *, scale, freeze=False, exclude_nodes=()):
    if not 0<len(raw)<=MAX_BYTES or not math.isfinite(scale) or not 0<scale<=100:
        raise AssetError('NIF: invalid file size or explicit unit scale')
    try:
        import setuptools  # supplies distutils on Python 3.12+ for PyFFI
        from pyffi.formats.nif import NifFormat as N
        from PIL import Image
    except ImportError as e:
        raise AssetError('NIF requires the optional PyFFI decoder and Pillow') from e
    data=N.Data()
    try:data.read(io.BytesIO(raw))
    except Exception as e:raise AssetError('NIF decoder failed: '+str(e)) from e
    if data.version!=0x14000004:raise AssetError('NIF: only version 20.0.0.4 is supported')
    if len(exclude_nodes)>64 or any(not isinstance(s,str) or not 0<len(s)<=128 for s in exclude_nodes):raise AssetError('NIF: invalid excluded node names')
    blocked=set();found=set()
    for root in data.roots:
        for node in root.tree():
            label=getattr(node,'name',b'').decode('cp1252')
            if label in exclude_nodes:
                found.add(label);blocked.update(id(child) for child in node.tree())
    if found!=set(exclude_nodes):raise AssetError('NIF: excluded node not found: '+', '.join(sorted(set(exclude_nodes)-found)))
    vertices=[];indices=[];groups=[];materials={};textures={};warnings=set()
    visited=set()
    for root in data.roots:
        if not isinstance(root,N.NiAVObject):raise AssetError('NIF: unsupported scene root')
        for node in root.tree():
            if id(node) in blocked:continue
            if id(node) in visited:continue
            visited.add(id(node))
            if len(visited)>100000:raise AssetError('NIF: scene object budget exceeded')
            if getattr(node,'controller',None):
                if not freeze:raise AssetError('NIF: controllers require explicit freeze mode')
                warnings.add('controllers discarded; stored pose only')
            if not isinstance(node,N.NiGeometry):continue
            if node.skin_instance:
                if not freeze:raise AssetError('NIF: skin requires explicit freeze mode')
                warnings.add('skin discarded; stored pose only, no skeletal animation')
            if not isinstance(node.data,(N.NiTriShapeData,N.NiTriStripsData)):
                if freeze:warnings.add('non-triangle geometry omitted');continue
                raise AssetError('NIF: unsupported geometry')
            geo=node.data
            prop=next((p for p in node.properties if isinstance(p,N.NiTexturingProperty)),None)
            if not prop or not prop.has_base_texture or not prop.base_texture.source or not prop.base_texture.source.use_external:
                if freeze:warnings.add('untextured emitter/geometry omitted');continue
                raise AssetError('NIF: external diffuse texture required')
            if not geo.has_normals or not geo.uv_sets:
                if freeze:warnings.add('geometry without normals or UVs omitted');continue
                raise AssetError('NIF: normals and UVs required')
            source=prop.base_texture.source.file_name.decode('cp1252').replace('\\','/').lower()
            if '..' in PurePosixPath(source).parts or source.startswith('/') or ':' in source:
                raise AssetError('NIF: invalid relative texture path')
            slot=hashlib.sha256(source.encode()).hexdigest()[:12]
            mid=f'{namespace}:material/{name}_{slot}';tid=f'{namespace}:texture/{name}_{slot}'
            alpha=any(isinstance(p,N.NiAlphaProperty) for p in node.properties)
            if mid not in materials:
                blob=texture_fetch(source)
                if not blob or len(blob)>MAX_BYTES:raise AssetError('NIF: missing or oversized texture '+source)
                with Image.open(io.BytesIO(blob)) as im:
                    if im.width>8192 or im.height>8192:raise AssetError('NIF: oversized decoded texture')
                    im=im.convert('RGBA');pixels=im.tobytes();w,h=im.size
                textures[tid]=Texture(tid,w,h,pixels,provenance={'source':source,'sha256':hashlib.sha256(blob).hexdigest()})
                materials[mid]=Material(mid,tid,'alpha' if alpha else 'opaque')
            transform=node.get_transform() if node is root else node.get_transform(relative_to=root)*root.get_transform()
            matrix=transform.get_matrix_33().as_list();base=len(vertices)
            if base+geo.num_vertices>1000000:raise AssetError('NIF: vertex budget exceeded')
            if len(geo.normals)!=geo.num_vertices or len(geo.uv_sets[0])!=geo.num_vertices:raise AssetError('NIF: inconsistent vertex arrays')
            for pos,normal,uv in zip(geo.vertices,geo.normals,geo.uv_sets[0]):
                point=tuple(x*scale for x in (pos*transform).as_tuple())
                normal=normal.as_tuple();normal=tuple(sum(normal[j]*matrix[j][k] for j in range(3)) for k in range(3))
                length=math.sqrt(sum(x*x for x in normal));normal=tuple(x/length for x in normal) if length>1e-10 else (0,0,1)
                if not all(math.isfinite(x) for x in (*point,*normal,uv.u,uv.v)):raise AssetError('NIF: non-finite vertex')
                vertices.append((point,normal,(uv.u,uv.v)))
            first=len(indices)
            for a,b,c in geo.get_triangles():
                if min(a,b,c)<0 or max(a,b,c)>=geo.num_vertices:raise AssetError('NIF: index out of range')
                pa,pb,pc=(vertices[base+i][0] for i in (a,b,c));u=tuple(pb[k]-pa[k] for k in range(3));v=tuple(pc[k]-pa[k] for k in range(3));face=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                if sum(x*x for x in face)<1e-18:continue
                average=tuple(sum(vertices[base+i][1][k] for i in (a,b,c)) for k in range(3))
                if sum(face[k]*average[k] for k in range(3))<0:b,c=c,b
                indices.extend((base+a,base+b,base+c))
                if len(indices)>3000000:raise AssetError('NIF: triangle budget exceeded')
            if len(indices)>first:groups.append((first,len(indices)-first,list(materials).index(mid)))
    if not indices:raise AssetError('NIF: no supported triangles')
    warnings.update(('Havok collision omitted; use authored collision','KF clips, morphs, particles, normal maps and vertex colors omitted'))
    provenance={'source_format':'NIF 20.0.0.4','source_sha256':hashlib.sha256(raw).hexdigest(),'source_to_runtime_scale':scale,'pose':'frozen stored pose' if freeze else 'static','excluded_nodes':sorted(found),'warnings':sorted(warnings)}
    return Model(f'{namespace}:model/{name}',vertices,indices,groups,list(materials),provenance=provenance),list(materials.values()),list(textures.values()),provenance
