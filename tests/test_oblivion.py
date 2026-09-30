"""Original fixtures for the bounded classic archive and rigid geometry path."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from assetlab.importers.bsa import Archive,BSAError
from assetlab import rigid_actor
from assetlab.assets import Model,Material,Texture,AssetError

def archive_fixture(payload=b'original mesh',flags=3,toggle=False,folder=b'meshes'):
    compressed=bool(flags&4)^toggle
    body=struct.pack('<I',len(payload))+zlib.compress(payload) if compressed else payload
    folder+=b'\0';name=b'toy.nif\0';start=36+16+1+len(folder)+16+len(name)
    return struct.pack('<4s8I',b'BSA\0',103,36,flags,1,1,len(folder),len(name),1)+struct.pack('<QII',0,1,52+len(name))+bytes([len(folder)])+folder+struct.pack('<QII',0,len(body)|(0x40000000 if toggle else 0),start)+name+body

class ArchiveTests(unittest.TestCase):
    def test_default_and_override_compression_and_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'toy.bsa'
            for flags in (3,7,0x703):
                for toggle in (False,True):
                    p.write_bytes(archive_fixture(flags=flags,toggle=toggle));a=Archive(p)
                    self.assertEqual(a.read('MESHES\\TOY.NIF'),b'original mesh')
                    with self.assertRaises(BSAError):a.read('meshes/toy.nif',limit=3)
            with self.assertRaises(BSAError):a.read('missing.nif')
    def test_invalid_tables_paths_and_compressed_payloads(self):
        raw=archive_fixture();bad=[raw[:10],raw[:55],archive_fixture(folder=b'../bad'),archive_fixture(folder=b'/absolute')]
        q=bytearray(raw);struct.pack_into('<I',q,12,0);bad.append(q)
        q=bytearray(raw);struct.pack_into('<I',q,76,999999);bad.append(q) # payload offset
        q=bytearray(archive_fixture(flags=7));q[-1]^=255;bad.append(q)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'toy.bsa'
            for blob in bad:
                p.write_bytes(blob)
                with self.assertRaises((BSAError,struct.error)):Archive(p).read('meshes/toy.nif')

class RigidTests(unittest.TestCase):
    def test_geometry_bones_and_pixels_survive_compilation(self):
        model=Model('toy:model/triangle',[((0,0,0),(0,0,1),(0,0)),((1,0,0),(0,0,1),(1,0)),((0,1,0),(0,0,1),(0,1))],[0,1,2],[(0,3,0)],['toy:material/paint'])
        mats=[Material('toy:material/paint','toy:texture/paint')];textures=[Texture('toy:texture/paint',1,1,b'\xff\x00\x00\xff')]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'toy.oalasset';report=rigid_actor.build(p,model,mats,textures,name='toy',display='Original Toy')
            raw=p.read_bytes();magic,version,length,count,_=struct.unpack_from('<4s4I',raw)
            self.assertEqual((magic,version,count),(b'OALA',1,1))
            manifest=json.loads(raw[32:32+length]);self.assertIn('no imported skeletal animation',manifest['warnings'][0])
            at=32+length;self.assertEqual(struct.unpack_from('<8I',raw,at),(3,3,1,1,1,0,0,0))
            self.assertEqual(struct.unpack_from('<3f',raw,at+32+48),(1,0,0))
            self.assertEqual(struct.unpack_from('<3I',raw,at+32+144),(0,1,2))
            self.assertEqual(report['package_bytes'],len(raw))
            idle={'fps':30,'loop':True,'frames':[(0,0,0,1,0,0,0),(0,0,0,1,.1,0,0)]}
            report=rigid_actor.build(p,model,mats,textures,name='toy',display='Toy',kind='weapon',view_model=model,view_clips={'idle':idle})
            self.assertEqual(report['models'][1]['clips'][0]['frames'],2)
            with self.assertRaises(AssetError):rigid_actor.build(p,model,mats,textures,name='toy',display='Toy',clips={'bad':{'frames':[(0,0,0,0,0,0,0)]}})
            model.indices[2]=4
            with self.assertRaises(AssetError):rigid_actor.build(p,model,mats,textures,name='toy',display='Toy')

class NifTests(unittest.TestCase):
    def setUp(self):
        try:
            import setuptools
            from pyffi.formats.nif import NifFormat as N
        except ImportError:self.skipTest('optional offline PyFFI decoder is not installed')
        import io
        from PIL import Image
        self.N=N;root=N.NiNode();node=N.NiTriShape();root.num_children=1;root.children.update_size();root.children[0]=node
        geo=N.NiTriShapeData();node.data=geo;geo.num_vertices=3;geo.has_vertices=True;geo.vertices.update_size();geo.has_normals=True;geo.normals.update_size();geo.num_uv_sets=1;geo.uv_sets.update_size()
        for i,(x,y) in enumerate(((0,0),(2,0),(0,2))):geo.vertices[i].x=x;geo.vertices[i].y=y;geo.normals[i].z=1
        geo.num_triangles=1;geo.num_triangle_points=3;geo.has_triangles=True;geo.triangles.update_size();geo.triangles[0].v_1=0;geo.triangles[0].v_2=1;geo.triangles[0].v_3=2
        prop=N.NiTexturingProperty();prop.has_base_texture=True;source=N.NiSourceTexture();source.use_external=1;source.file_name=b'textures/toy.png';prop.base_texture.source=source;node.num_properties=1;node.properties.update_size();node.properties[0]=prop
        self.root=root;self.node=node;self.source=source
        png=io.BytesIO();Image.new('RGBA',(1,1),(255,0,0,255)).save(png,format='PNG');self.png=png.getvalue()
    def raw(self):
        import io
        buf=io.BytesIO();data=self.N.Data(version=0x14000004);data.roots=[self.root];data.write(buf);return buf.getvalue()
    def load(self,**kwargs):
        from assetlab.importers.nif_static import read_nif
        return read_nif(self.raw(),lambda _:self.png,'toy','original',scale=.5,**kwargs)
    def test_original_geometry_units_winding_texture_and_provenance(self):
        model,mats,tex,report=self.load()
        self.assertEqual(model.vertices[1][0],(1,0,0));self.assertEqual(model.indices,[0,1,2]);self.assertEqual(tex[0].rgba,b'\xff\x00\x00\xff')
        self.assertEqual(report['source_to_runtime_scale'],.5);self.assertEqual(report['pose'],'static');self.assertEqual(mats[0].texture,tex[0].id)
    def test_controller_requires_explicit_freeze_and_relative_texture(self):
        self.node.controller=self.N.NiTransformController()
        with self.assertRaisesRegex(AssetError,'freeze'):self.load()
        _,_,_,report=self.load(freeze=True);self.assertTrue(any('controllers discarded' in s for s in report['warnings']))
        self.source.file_name=b'../secret.png'
        with self.assertRaisesRegex(AssetError,'relative texture'):self.load(freeze=True)
    def test_explicit_node_exclusion_omits_subtree_and_preserves_provenance(self):
        extra=self.N.NiNode();extra.name=b'Optional attachment';bad=self.N.NiTriShape();extra.num_children=1;extra.children.update_size();extra.children[0]=bad
        self.root.num_children=2;self.root.children.update_size();self.root.children[1]=extra
        model,_,_,report=self.load(exclude_nodes=['Optional attachment'])
        self.assertEqual(len(model.indices),3);self.assertEqual(report['excluded_nodes'],['Optional attachment'])
        with self.assertRaisesRegex(AssetError,'not found'):self.load(exclude_nodes=['missing'])
        with self.assertRaisesRegex(AssetError,'no supported triangles'):
            self.root.name=b'Everything';self.load(exclude_nodes=['Everything'])
