import json
import math
import sqlite3
import struct
import tempfile
import time
import unittest
from pathlib import Path
from assetlab.importers.source_bsp import BSPError,SourceBSP
from assetlab.package import compile_map,read_manifest
from assetlab.library import Library


def fixture(disp=False):
    lumps={}
    lumps[0]=b'{ "classname" "info_player_start" "origin" "60 60 8" "angle" "90" }\0'
    lumps[1]=struct.pack('<4fi',0,0,1,0,2)
    lumps[2]=struct.pack('<3f5i',.5,.5,.5,0,120,120,120,120)
    lumps[3]=b''.join(struct.pack('<3f',*p) for p in ((0,0,0),(120,0,0),(120,120,0),(0,120,0)))
    ti=bytearray(72)
    struct.pack_into('<4f',ti,0,1,0,0,0);struct.pack_into('<4f',ti,16,0,1,0,0)
    struct.pack_into('<ii',ti,64,0,0);lumps[6]=ti
    face=bytearray(56);struct.pack_into('<HBBihhh',face,0,0,0,1,0,4,0,0 if disp else -1);lumps[7]=face
    lumps[12]=b''.join(struct.pack('<HH',i,(i+1)%4) for i in range(4))
    lumps[13]=struct.pack('<4i',0,1,2,3)
    model=bytearray(48);struct.pack_into('<6f',model,0,0,0,0,120,120,32);struct.pack_into('<ii',model,40,0,1);lumps[14]=model
    if disp:
        info=bytearray(176);struct.pack_into('<3fiii',info,0,0,0,0,0,0,2);struct.pack_into('<H',info,36,0);lumps[26]=info
        lumps[33]=b''.join(struct.pack('<5f',0,0,1,4 if x==2 and y==2 else 0,0) for y in range(5) for x in range(5))
    lumps[43]=b'test/checker\0';lumps[44]=struct.pack('<i',0)
    out=bytearray(1036);out[:8]=b'VBSP'+struct.pack('<I',20)
    for i,d in sorted(lumps.items()):
        off=len(out);out.extend(d);struct.pack_into('<4I',out,8+i*16,off,len(d),1 if i==7 else 0,0)
    return out


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
        bad=bytearray(a.read_bytes());struct.pack_into('<I',bad,4,2);b.write_bytes(bad)
        with self.assertRaises(BSPError):read_manifest(b)
    def test_job_recovery_and_source_path(self):
        root=self.root/'library';lib=Library(root,[self.root])
        self.assertIsNone(lib.source_path('../../etc/passwd'))
        self.assertEqual(len(lib.sources()),1)
        lib.close()
        with sqlite3.connect(root/'jobs.sqlite3') as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',('a'*32,'b'*20,'fixture.bsp','IMPORTING',time.time(),time.time(),'started',None,None,None))
        lib=Library(root,[self.root]);self.assertIn('Recovered after service restart',lib.job('a'*32)['log']);lib.close()

if __name__=='__main__':unittest.main()
