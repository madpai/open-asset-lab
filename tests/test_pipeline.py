import json
import math
import sqlite3
import struct
import tempfile
import time
import unittest
from pathlib import Path
from assetlab.importers.source_bsp import BSPError,SourceBSP
from assetlab.package import compile_map,read_manifest,parse_keyvalues,_vtf_rgba,fit_textures
from assetlab.importers.source_bsp import parse_entities
from assetlab import translate,coords
from assetlab.report import markdown
from assetlab.importers.source_mdl import Model,angle_matrix
from assetlab.library import Library
from srctools.vpk import VPK


def fixture(disp=False,raised=(2,2),ents=None,texflags=0,version=20,side=0,extra=None,brush_model=False):
    lumps={}
    lumps[0]=(ents if ents is not None else b'{ "classname" "info_player_start" "origin" "60 60 8" "angle" "90" }')+b'\0'
    lumps[1]=struct.pack('<4fi',0,0,1,0,2)
    lumps[2]=struct.pack('<3f5i',.5,.5,.5,0,120,120,120,120)
    lumps[3]=b''.join(struct.pack('<3f',*p) for p in ((0,0,0),(120,0,0),(120,120,0),(0,120,0)))
    ti=bytearray(72)
    struct.pack_into('<4f',ti,0,1,0,0,0);struct.pack_into('<4f',ti,16,0,1,0,0)
    struct.pack_into('<ii',ti,64,texflags,0);lumps[6]=ti
    face=bytearray(56);struct.pack_into('<HBBihhh',face,0,0,side,1,0,4,0,0 if disp else -1);lumps[7]=face
    lumps[12]=b''.join(struct.pack('<HH',i,(i+1)%4) for i in range(4))
    lumps[13]=struct.pack('<4i',0,1,2,3)
    model=bytearray(48);struct.pack_into('<6f',model,0,0,0,0,120,120,32);struct.pack_into('<ii',model,40,0,1);lumps[14]=bytes(model)*(2 if brush_model else 1)
    if disp:
        info=bytearray(176);struct.pack_into('<3fiii',info,0,0,0,0,0,0,2);struct.pack_into('<H',info,36,0);lumps[26]=info
        lumps[33]=b''.join(struct.pack('<5f',0,0,1,4 if (x,y)==raised else 0,0) for y in range(5) for x in range(5))
    lumps[43]=b'test/checker\0';lumps[44]=struct.pack('<i',0)
    lumps.update(extra or {})
    out=bytearray(1036);out[:8]=b'VBSP'+struct.pack('<I',version)
    for i,d in sorted(lumps.items()):
        off=len(out);out.extend(d);struct.pack_into('<4I',out,8+i*16,off,len(d),1 if i==7 else 0,0)
    return out


def model_fixture():
    """One triangle, one texture, one body part: the least a static prop can be."""
    mdl=bytearray(1024);mdl[:4]=b'IDST';struct.pack_into('<ii',mdl,4,48,1234)
    # textures at 300 (one 64-byte record, name at 400), cdmaterials table at 380 -> 420
    struct.pack_into('<iiiiiiiii',mdl,204,1,300,1,380,1,1,390,1,500)
    struct.pack_into('<i',mdl,300,100);mdl[400:408]=b'crate01\0'
    struct.pack_into('<i',mdl,380,420);mdl[420:436]=b'models\\props\\x\\\0'
    struct.pack_into('<h',mdl,390,0)
    struct.pack_into('<iiii',mdl,500,0,1,0,16)            # body part -> model at 516
    struct.pack_into('<iiii',mdl,516+72,1,148,3,0)        # one mesh at 664, vertices from 0
    struct.pack_into('<iiii',mdl,664,0,0,3,0)
    vvd=bytearray(64+3*48);vvd[:4]=b'IDSV';struct.pack_into('<iiii',vvd,4,4,1234,1,3);struct.pack_into('<iii',vvd,48,0,0,64)
    for i,(x,y) in enumerate(((0,0),(10,0),(0,10))):struct.pack_into('<8f',vvd,64+i*48+16,x,y,0,0,0,1,x/10,y/10)
    vtx=bytearray(200);struct.pack_into('<i',vtx,0,7);struct.pack_into('<i',vtx,16,1234);struct.pack_into('<ii',vtx,28,1,36)
    struct.pack_into('<ii',vtx,36,1,8)      # body part 36 -> model 44
    struct.pack_into('<ii',vtx,44,1,8)      # model -> lod 52
    struct.pack_into('<ii',vtx,52,1,12)     # lod -> mesh 64
    struct.pack_into('<ii',vtx,64,1,9)      # mesh -> strip group 73
    struct.pack_into('<iiii',vtx,73,3,25,3,25+27)   # 3 verts at 98, 3 indices at 125
    for i in range(3):struct.pack_into('<H',vtx,98+i*9+4,i)
    struct.pack_into('<3H',vtx,125,0,1,2)
    return bytes(mdl),bytes(vvd),bytes(vtx)


def animated_fixture():
    """A two-bone model whose bone 1 turns 90 degrees about Z in a RAWROT
    animation, with ACT_IDLE and ACT_RUN sequences on that anim, one
    triangle skinned to bone 1. Tables sit after the 408-byte header."""
    mdl=bytearray(4096);mdl[:4]=b'IDST';struct.pack_into('<ii',mdl,4,48,1234)
    struct.pack_into('<iiiiiiiii',mdl,204,1,1000,1,1080,1,1,1090,1,1200)   # tex, cd, skin, bodyparts
    struct.pack_into('<i',mdl,1000,1100-1000);mdl[1100:1108]=b'crate01\0'
    struct.pack_into('<i',mdl,1080,1120);mdl[1120:1136]=b'models\\props\\x\\\0'
    struct.pack_into('<iiii',mdl,1200,0,1,0,16)            # body part -> model at 1216
    struct.pack_into('<iiii',mdl,1216+72,1,148,3,0)        # one mesh at 1364
    struct.pack_into('<iiii',mdl,1364,0,0,3,0)
    struct.pack_into('<ii',mdl,156,2,1600)                 # bones at 1600
    for i,(name_off,parent) in enumerate(((3000,-1),(3010,0))):
        o=1600+i*216
        struct.pack_into('<ii',mdl,o,name_off-o,parent)
        struct.pack_into('<3f',mdl,o+32,0,0,0 if i==0 else 12)
        struct.pack_into('<4f',mdl,o+44,0,0,0,1)
        struct.pack_into('<3f',mdl,o+72,1,1,1); struct.pack_into('<3f',mdl,o+84,1,1,1)
        struct.pack_into('<12f',mdl,o+96,1,0,0,0, 0,1,0,0, 0,0,1,-12 if i else 0)
    mdl[3000:3005]=b'root\0';mdl[3010:3015]=b'hand\0'
    struct.pack_into('<ii',mdl,180,1,2100)                 # one anim desc at 2100
    struct.pack_into('<i',mdl,2104,3020-2100);mdl[3020:3025]=b'turn\0'
    struct.pack_into('<fii',mdl,2108,30.0,0,2)
    struct.pack_into('<ii',mdl,2152,0,2300-2100)          # data at 2300
    z=math.sin(math.pi/4)
    struct.pack_into('<BBh',mdl,2300,1,2,0)
    struct.pack_into('<HHH',mdl,2304,32768,32768,int(z*16384+16384))
    struct.pack_into('<ii',mdl,188,2,2400)                 # two sequences at 2400
    for k,(lab,act) in enumerate(((3030,3040),(3060,3070))):
        o=2400+k*212
        struct.pack_into('<ii',mdl,o+4,lab-o,act-o)
        struct.pack_into('<i',mdl,o+60,2900-o)
        struct.pack_into('<ii',mdl,o+68,1,1)
    mdl[3030:3035]=b'idle\0';mdl[3040:3049]=b'ACT_IDLE\0';mdl[3060:3064]=b'run\0';mdl[3070:3078]=b'ACT_RUN\0'
    struct.pack_into('<h',mdl,2900,0)
    _,vvd,vtx=[bytearray(b) for b in model_fixture()]
    for i in range(3):struct.pack_into('<3f3B',vvd,64+i*48,1,0,0,1,0,0);vvd[64+i*48+15]=1
    return bytes(mdl),bytes(vvd),bytes(vtx)


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name)
        mdl,vvd,vtx=animated_fixture()
        d=self.root/'models/test';d.mkdir(parents=True)
        (d/'guy.mdl').write_bytes(mdl);(d/'guy.vvd').write_bytes(vvd);(d/'guy.dx90.vtx').write_bytes(vtx)
    def tearDown(self):self.t.cleanup()
    def test_studio_parses_bones_sequences_and_raw_rotation(self):
        from assetlab.importers.source_studio import Studio
        st=Studio((self.root/'models/test/guy.mdl').read_bytes(),name='guy')
        self.assertEqual([b['name'] for b in st.bones],['root','hand'])
        self.assertEqual([(q['label'],q['activity']) for q in st.sequences],[('idle','ACT_IDLE'),('run','ACT_RUN')])
        pos,q,delta=st.sample(0,0)[1]
        self.assertAlmostEqual(q[2],math.sin(math.pi/4),places=3);self.assertAlmostEqual(q[3],math.cos(math.pi/4),places=3)
        self.assertEqual(pos,(0,0,12))
    def test_character_bakes_roles_through_the_registry(self):
        from assetlab.character import build_character,MAGIC
        m=build_character('models/test/guy.mdl',self.root/'guy.oalasset',roots=[self.root],hold='ak')
        roles=[c['role'] for c in m['models'][0]['clips']]
        self.assertIn('idle',roles);self.assertIn('run_front',roles)
        self.assertIn('death',m['models'][0]['missing_roles'])
        self.assertEqual(m['models'][0]['bones'],['root','hand'])
        data=(self.root/'guy.oalasset').read_bytes()
        self.assertEqual(data[:4],MAGIC);self.assertEqual(struct.unpack_from('<I',data,4)[0],1)
    def test_character_without_required_roles_is_refused(self):
        from assetlab.character import build_character
        mdl=bytearray((self.root/'models/test/guy.mdl').read_bytes())
        mdl[3070:3078]=b'ACT_XYZ\0';(self.root/'models/test/guy.mdl').write_bytes(bytes(mdl))
        with self.assertRaisesRegex(BSPError,'run_front'):build_character('models/test/guy.mdl',self.root/'x.oalasset',roots=[self.root])


class ModelTests(unittest.TestCase):
    def test_static_model_triangle_and_material(self):
        m=Model(*model_fixture(),exists=lambda n:n=='models/props/x/crate01')
        self.assertEqual(list(m.groups),['models/props/x/crate01'])
        tri=m.groups['models/props/x/crate01']
        self.assertEqual([v[0] for v in tri],[(0,0,0),(10,0,0),(0,10,0)])
        self.assertEqual(tri[1][2],(1.0,0.0))
    def test_checksum_mismatch_rejected(self):
        mdl,vvd,vtx=model_fixture();bad=bytearray(vvd);struct.pack_into('<i',bad,8,99)
        with self.assertRaises(BSPError):Model(mdl,bytes(bad),vtx)
    def test_angle_matrix_yaw(self):
        m=angle_matrix(0,90,0)
        self.assertAlmostEqual(m[0][0],0,places=6);self.assertAlmostEqual(m[1][0],1,places=6)


class BSPTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.path=self.root/'fixture.bsp';self.path.write_bytes(fixture())
    def tearDown(self):self.t.cleanup()
    def test_geometry_scale_winding_entities(self):
        p=SourceBSP(self.path);w=p.convert()
        self.assertEqual(len(w.indices)//3,2)
        self.assertEqual(len(w.spawns),1)
        self.assertAlmostEqual(w.spawns[0]['position'][0],.5)
        self.assertAlmostEqual(w.spawns[0]['position'][2],0)
        a,b,c=(w.vertices[w.indices[j]][0] for j in range(3))
        self.assertGreater((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]),0)
        self.assertEqual(w.vertices[0][2],(0.,0.))
        self.assertEqual(w.report['used_materials']['test/checker'],2)
    def test_displacement_topology(self):
        self.path.write_bytes(fixture(True));w=SourceBSP(self.path).convert()
        self.assertEqual(w.report['converted_displacements'],1)
        self.assertEqual(len(w.indices)//3,32)
        self.assertGreater(max(v[0][2] for v in w.vertices),0)
    def test_displacement_row_order_matches_valve(self):
        # Row index 1, column 0 lies one step along p0->p1 (Source +X), not p0->p3.
        self.path.write_bytes(fixture(True,raised=(0,1)));w=SourceBSP(self.path).convert()
        top=max(w.vertices,key=lambda v:v[0][2])[0]
        self.assertAlmostEqual(top[0],.25);self.assertAlmostEqual(top[1],0);self.assertAlmostEqual(top[2],4/120)
        for t in range(0,len(w.indices),3):
            a,b,c=(w.vertices[w.indices[t+j]][0] for j in range(3))
            self.assertGreater((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]),0)
    def test_invalid_input(self):
        cases=[]
        b=fixture();b[:4]=b'IBSP';cases.append(bytes(b))
        b=fixture();struct.pack_into('<I',b,4,21);cases.append(bytes(b))
        cases.append(bytes(fixture()[:100]))
        b=fixture();struct.pack_into('<I',b,8+3*16,len(b)+1);cases.append(bytes(b))
        b=fixture();off=struct.unpack_from('<I',b,8+13*16)[0];struct.pack_into('<i',b,off,10000);cases.append(bytes(b))
        b=fixture();off=struct.unpack_from('<I',b,8+7*16)[0];struct.pack_into('<h',b,off+8,30000);cases.append(bytes(b))
        for data in cases:
            with self.subTest(case=len(data)):
                self.path.write_bytes(data)
                with self.assertRaises(BSPError):SourceBSP(self.path).convert()
    def test_package_determinism_and_version(self):
        a=self.root/'a.oalmap';b=self.root/'b.oalmap'
        m,r=compile_map(self.path,a);compile_map(self.path,b)
        self.assertEqual(a.read_bytes(),b.read_bytes())
        self.assertEqual(m['package_version'],1)
        self.assertIn('materials/test/checker.vmt',m['missing_dependencies'])
        self.assertEqual(m['placeholder_materials'],['test/checker'])
        self.assertEqual(r['resolved_textures'],0)
        bad=bytearray(a.read_bytes());struct.pack_into('<I',bad,4,2);b.write_bytes(bad)
        with self.assertRaises(BSPError):read_manifest(b)
    def test_vpk_material_resolution(self):
        archive=self.root/'materials_dir.vpk'
        vtf=bytearray(80+16)
        vtf[:4]=b'VTF\0'
        struct.pack_into('<III',vtf,4,7,2,80)
        struct.pack_into('<HH',vtf,16,2,2)
        struct.pack_into('<I',vtf,52,0)
        struct.pack_into('<I',vtf,57,0xffffffff)
        vtf[56]=1
        vtf[63]=0  # VTF depth is zero for this 2D texture.
        vtf[80:]=bytes((255,128,0,255))*4
        with VPK(archive,mode='w') as v:
            v.add_file('materials/test/checker.vmt',b'"LightmappedGeneric" { "$basetexture" "test/checker" }',arch_index=None)
            v.add_file('materials/test/checker.vtf',bytes(vtf),arch_index=None)
        manifest,report=compile_map(self.path,self.root/'from-vpk.oalmap',vpks=[archive])
        self.assertEqual(report['resolved_textures'],1)
        self.assertEqual(report['texture_bytes'],16)
        self.assertEqual(manifest['placeholder_materials'],[])
        self.assertEqual(manifest['missing_dependencies'],[])
    def test_missing_material_uses_diagnostic_color(self):
        # Colour comes from the VMT's $surfaceprop when there is one, never the name.
        wood=translate.placeholder('a/b',{'$surfaceprop':'wood_plank'});grass=translate.placeholder('a/b',{'$surfaceprop':'grass'})
        self.assertEqual(wood,translate.placeholder('a/b',{'$surfaceprop':'wood_plank'}))
        self.assertNotEqual(wood[2],grass[2])
        self.assertEqual((wood[0],wood[1]),(4,4))
        self.assertEqual(translate.placeholder('grass/field')[2][:3],translate.placeholder('grass/field',{})[2][:3])
        self.assertTrue(all(wood[2][i]<180 for i in range(0,len(wood[2]),4)))
    def test_job_recovery_and_source_path(self):
        root=self.root/'library';lib=Library(root,[self.root])
        self.assertIsNone(lib.source_path('../../etc/passwd'))
        self.assertEqual(len(lib.sources()),1)
        lib.close()
        with sqlite3.connect(root/'jobs.sqlite3') as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',('a'*32,'b'*20,'fixture.bsp','IMPORTING',time.time(),time.time(),'started',None,None,None))
        lib=Library(root,[self.root]);self.assertIn('Recovered after service restart',lib.job('a'*32)['log']);lib.close()


def vtf(w,h,pixels_rgba,frames=1,mips=1,fmt=0):
    """A VTF 7.2 of raw RGBA8888 images: smallest mip first, frames within a mip."""
    head=bytearray(80);head[:4]=b'VTF\0';struct.pack_into('<III',head,4,7,2,80)
    struct.pack_into('<HHIH',head,16,w,h,0,frames);struct.pack_into('<i',head,52,fmt);head[56]=mips
    struct.pack_into('<i',head,57,-1);struct.pack_into('<H',head,63,1)
    body=b''.join(pixels_rgba(max(1,w>>m),max(1,h>>m),f) for m in range(mips-1,-1,-1) for f in range(frames))
    return bytes(head)+body


class GeneralizationTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.path=self.root/'m.bsp'
    def tearDown(self):self.t.cleanup()
    def convert(self,**kw):
        self.path.write_bytes(fixture(**kw));return SourceBSP(self.path).convert()

    def test_coordinate_scaling_is_central(self):
        self.assertEqual(coords.to_runtime((120,-240,60)),(1.0,-2.0,0.5))
        w=self.convert()
        self.assertEqual(max(v[0][0] for v in w.vertices),1.0)
        self.assertEqual(w.report['converted_bounds']['max'][:2],[1.0,1.0])

    def test_uv_generation_from_texinfo(self):
        w=self.convert()
        uv={v[0][:2]:v[2] for v in w.vertices}
        # texinfo u=(1,0,0,0), v=(0,1,0,0) over a 120x120 texture: a Source unit per texel.
        self.assertEqual(uv[(1.0,0.0)],(1.0,0.0));self.assertEqual(uv[(1.0,1.0)],(1.0,1.0))

    def test_face_winding_follows_plane_side(self):
        up=self.convert();down=self.convert(side=1)
        def nz(w):
            a,b,c=(w.vertices[w.indices[j]][0] for j in range(3))
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        self.assertGreater(nz(up),0);self.assertLess(nz(down),0)

    def test_bsp_versions(self):
        self.assertEqual(self.convert(version=19).report['bsp_version'],19)
        for v in (18,21):
            self.path.write_bytes(fixture(version=v))
            with self.assertRaisesRegex(BSPError,f'version {v}'):SourceBSP(self.path)
        b=fixture();struct.pack_into('<I',b,8+7*16+8,0);self.path.write_bytes(b)
        with self.assertRaisesRegex(BSPError,'face lump version'):SourceBSP(self.path)

    def test_entity_parsing(self):
        e=parse_entities(b'{"classname" "logic_relay" "OnTrigger" "a,Fire,{x},0,-1"}\n{ "ClassName" "info_player_start" "origin" "1 2 3" }\0junk')
        self.assertEqual(len(e),2);self.assertEqual(e[0]['ontrigger'],'a,Fire,{x},0,-1');self.assertEqual(e[1]['classname'],'info_player_start')
        for bad in (b'{"a" "b"',b'{"a"}',b'{ {"a" "b"} }',b'{"a" "b"} x',b'}'):
            with self.subTest(bad=bad),self.assertRaises(BSPError):parse_entities(bad)

    def test_spawn_teams_by_registry(self):
        ents=b''.join(b'{"classname" "%s" "origin" "60 60 8" %s}'%(c,kv) for c,kv in (
            (b'info_player_terrorist',b''),(b'info_player_counterterrorist',b''),(b'info_player_teamspawn',b'"TeamNum" "3"'),
            (b'info_player_teamspawn',b'"TeamNum" "0"'),(b'info_player_deathmatch',b''),(b'trigger_multiple',b'')))
        w=self.convert(ents=ents)
        self.assertEqual([s['team'] for s in w.spawns],[translate.RED,translate.BLUE,translate.BLUE,None,None])
        self.assertEqual(w.report['entities']['not_geometry'],{'trigger_multiple':1})
        floating=self.convert(ents=b'{"classname" "info_player_start" "origin" "60 60 8"}{"classname" "info_player_start" "origin" "60 60 900"}')
        self.assertEqual(len(floating.spawns),1);self.assertEqual(len(floating.report['rejected_spawns']),1)
        self.assertTrue(any('rejected' in x for x in floating.report['warnings']))

    def test_brush_entities_by_registry(self):
        base=self.convert(brush_model=True)
        moved=self.convert(brush_model=True,ents=b'{"classname" "func_brush" "model" "*1" "origin" "240 0 0"}{"classname" "info_player_start" "origin" "60 60 8"}')
        self.assertEqual(len(moved.indices),len(base.indices)+6)
        self.assertEqual(max(v[0][0] for v in moved.vertices),3.0)
        self.assertEqual(moved.report['brush_entities_converted'],1)
        hidden=self.convert(brush_model=True,ents=b'{"classname" "func_brush" "model" "*1" "StartDisabled" "1"}{"classname" "info_player_start" "origin" "60 60 8"}')
        self.assertEqual(len(hidden.indices),len(base.indices));self.assertEqual(hidden.report['brush_entities_hidden'],1)
        ghost=self.convert(brush_model=True,ents=b'{"classname" "func_illusionary" "model" "*1"}{"classname" "info_player_start" "origin" "60 60 8"}')
        self.assertEqual([g[3] for g in ghost.groups],[True,False])
        odd=self.convert(brush_model=True,ents=b'{"classname" "func_weird_thing" "model" "*1"}{"classname" "info_player_start" "origin" "60 60 8"}')
        self.assertEqual(odd.report['entities']['unsupported'],{'func_weird_thing':1})

    def test_surface_flags_are_counted_not_silent(self):
        self.path.write_bytes(fixture(texflags=0x80))
        with self.assertRaisesRegex(BSPError,'empty'):SourceBSP(self.path).convert()
        water=self.convert(texflags=0x8)
        self.assertEqual(water.report['water_faces'],1);self.assertEqual(water.groups[0][3],False)

    def test_unused_lumps_are_reported(self):
        w=self.convert(extra={8:b'\0'*16,45:b'\0'*4,5:b'\0'*32})
        self.assertIn('lighting',w.report['lumps']['unsupported'])
        self.assertIn('overlays',w.report['lumps']['unsupported'])
        self.assertIn('nodes',w.report['lumps']['not_needed'])
        self.assertIn('lightmaps',w.report['unsupported_features'])

    def test_keyvalues_and_patch_materials(self):
        shader,kv=parse_keyvalues('// c\nLightmappedGeneric\n{\n $basetexture foo/bar // x\n "$translucent" 1\n proxies { a { b c } }\n}')
        self.assertEqual(shader,'lightmappedgeneric');self.assertEqual(kv['$basetexture'],'foo/bar');self.assertEqual(kv['$translucent'],'1')
        self.assertEqual(translate.material_policy({'shader':'water'})[0],False)
        self.assertIn('translucency drawn opaque',translate.material_policy({'$translucent':'1'})[1])
        archive=self.root/'p_dir.vpk'
        with VPK(archive,mode='w') as v:
            v.add_file('materials/test/checker.vmt',b'patch { include "materials/base/w.vmt" insert { "$surfaceprop" "wood" } }',arch_index=None)
            v.add_file('materials/base/w.vmt',b'Water { $basetexture base/w }',arch_index=None)
        self.path.write_bytes(fixture())
        m,r=compile_map(self.path,self.root/'p.oalmap',vpks=[archive])
        self.assertEqual(m['non_solid_materials'],['test/checker'])
        self.assertEqual(m['compatibility']['geometry']['collision_triangles'],0)
        self.assertIn('materials/base/w.vtf',m['missing_dependencies'])

    def test_vtf_frames_and_formats(self):
        solid=lambda c:(lambda w,h,f:bytes(c if f==0 else (9,9,9,9))*w*h)
        w,h,px=_vtf_rgba(vtf(4,4,solid((10,20,30,255)),frames=2,mips=3))
        self.assertEqual((w,h,px[:4]),(4,4,bytes((10,20,30,255))))
        bgr=vtf(2,2,lambda w,h,f:bytes((30,20,10))*w*h,fmt=3)
        self.assertEqual(_vtf_rgba(bgr)[2][:4],bytes((10,20,30,255)))
        with self.assertRaisesRegex(BSPError,'format 24'):_vtf_rgba(vtf(2,2,solid((0,0,0,0)),fmt=24))

    def test_package_shares_identical_vertices(self):
        self.path.write_bytes(fixture())
        m,r=compile_map(self.path,self.root/'v.oalmap')
        # One quad: two triangles over four corners, not six vertices.
        self.assertEqual(m['geometry']['triangles'],2);self.assertEqual(m['geometry']['vertices'],4)
        h=(self.root/'v.oalmap').read_bytes()[:64]
        self.assertEqual(struct.unpack_from('<II',h,12),(4,6))

    def test_texture_budget(self):
        tex={'a':(64,64,bytes(64*64*4)),'b':(16,16,bytes(16*16*4))}
        halved=fit_textures(tex,10000)
        self.assertEqual(halved,{'a':1});self.assertEqual(tex['a'][:2],(32,32))
        self.assertLessEqual(sum(len(t[2]) for t in tex.values()),10000)

    def test_compatibility_report(self):
        self.path.write_bytes(fixture(disp=True))
        m,r=compile_map(self.path,self.root/'c.oalmap')
        c=r['compatibility']
        for key in ('bsp_version','geometry','displacements','materials','static_props','entities','spawns','lumps','unsupported_features','warnings','dependencies'):
            self.assertIn(key,c)
        self.assertEqual(c['displacements'],{'in_bsp':1,'converted':1})
        self.assertEqual(c['materials']['placeholder'],1)
        self.assertEqual(c['geometry']['collision_triangles'],32)
        self.assertEqual(c['spawns']['either'],1)
        self.assertIn('## m.bsp',markdown(c))

if __name__=='__main__':unittest.main()
