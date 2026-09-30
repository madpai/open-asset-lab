import unittest
import tempfile
from pathlib import Path
from assetlab import survival as s, project
from assetlab.worldkey import world_key

class SurvivalTests(unittest.TestCase):
    def fixture(self):
        return s.SurvivalConfig((0,0,0),[(5,0,0)],[s.Enemy('Original foe')],[s.Item('test:item/health','Potion',kind=s.HEALTH,power=.5)])
    def test_limits_and_ids(self):
        c=self.fixture();self.assertEqual([],s.errors(c))
        c.items[0].power=float('nan');self.assertTrue(s.errors(c))
        c=self.fixture();c.items.append(c.items[0]);self.assertTrue(s.errors(c))
        c=self.fixture();c.items[0].id='bad id';self.assertTrue(s.errors(c))
        c=self.fixture();c.enemies[0].speed=6;self.assertTrue(s.errors(c))
        c=self.fixture();c.items[0].kind=s.ARMOR;c.items[0].power=.76;self.assertTrue(s.errors(c))
    def test_public_project_and_identity(self):
        mod=project.load(Path(__file__).resolve().parents[1]/'projects/gatebound')
        self.assertEqual([],s.errors(mod.worlds()[0].survival))
        with tempfile.TemporaryDirectory() as d:
            r=project.build(Path(__file__).resolve().parents[1]/'projects/gatebound',d)
            p=Path(d)/'maps/gatebound.oalmap';before=world_key(p)['world_key']
            self.assertTrue(before)
            from assetlab.world import compile_world
            world=mod.worlds()[0];world.survival.items[0].price=1
            compile_world(world,p)
            self.assertNotEqual(before,world_key(p)['world_key'])

    def test_normalized_world_geometry_preserves_uv_and_texture(self):
        from assetlab.assets import Model,Texture
        from assetlab.world import OriginalWorld,ModelPlacement,compile_world,WorldError
        model=Model('toy:model/floor',[((0,0,0),(0,0,1),(.2,.3)),((1,0,0),(0,0,1),(.4,.5)),((0,1,0),(0,0,1),(.6,.7))],[0,1,2],[(0,3,0)],['stone'])
        texture=Texture('toy:texture/stone',1,1,b'\xff\x00\x00\xff')
        world=OriginalWorld('toy:world/floor','floor','Original textured floor',{'stone':(255,255,255)},[],[dict(position=(0,0,0),yaw_degrees=0,team_index=0)],[],model_geometry=[ModelPlacement(model)],material_textures={'stone':texture})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'floor.oalmap';manifest,report=compile_world(world,path);self.assertEqual(report['triangles'],1)
            before=world_key(path)['world_key'];digest=report['package_sha256'];texture.rgba=b'\x00\xff\x00\xff';_,changed=compile_world(world,path);self.assertNotEqual(digest,changed['package_sha256'])
            world.model_geometry[0].position=(1,0,0);compile_world(world,path);self.assertNotEqual(before,world_key(path)['world_key'])
            world.model_geometry[0].scale=float('nan')
            with self.assertRaises(WorldError):compile_world(world,path)
