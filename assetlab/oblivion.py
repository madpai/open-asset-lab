"""Explicit local BSA/NIF import; normalized output uses existing formats."""
from pathlib import Path
from .importers.bsa import Archive
from .importers.nif_static import read_nif
from .dependencies import Library,compile_library
from .rigid_actor import build

def import_model(mesh_archive,texture_archive,source,output,*,namespace,name,scale,freeze=False,kind='model',display=None,exclude_nodes=()):
    meshes=Archive(mesh_archive);textures=Archive(texture_archive)
    model,mats,tex,report=read_nif(meshes.read(source),textures.read,namespace,name,scale=scale,freeze=freeze,exclude_nodes=exclude_nodes)
    model.provenance.update(archive=meshes.path.name,source=source,redistribution='rights not inferred')
    out=Path(output);lib=Library(namespace+'.art',display_name=display or name,models=[model],materials=mats,textures=tex)
    result={'import':report,'library':compile_library(lib,out/'packages'/((namespace+'.art')+'.oalasset'))}
    if kind!='model':
        meta={'base':'pistol','hold_type':'melee','melee':True} if kind=='weapon' else {'unique_limit':0,'body_shield':0}
        folder='weapons' if kind=='weapon' else 'characters'
        result['actor']=build(out/folder/(name+'.oalasset'),model,mats,tex,name=name,display=display or name,kind=kind,metadata=meta)
    return result
