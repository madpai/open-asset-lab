"""X10 original race route and package identity."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

from assetlab import project
from assetlab.racing import errors


HERE=Path(__file__).resolve().parents[1]/'projects'/'megamod_racing'


class RacingProjectTests(unittest.TestCase):
    def test_project_deterministic_and_bounded(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first=project.build(HERE,a)
            second=project.build(HERE,b)
            self.assertEqual(first['worlds'][0]['world_key'],second['worlds'][0]['world_key'])
            for rel in ('maps/cinder_circuit.oalmap','packages/racing.assets.oalasset',
                        'packages/racing.trackkit.oalasset'):
                self.assertEqual((Path(a)/rel).read_bytes(),(Path(b)/rel).read_bytes())
            self.assertEqual(first['worlds'][0]['budget']['total'],27)
            self.assertEqual(first['worlds'][0]['triangles'],654)
            self.assertEqual(first['libraries'][0]['asset_counts']['sounds'],6)

    def test_invalid_checkpoint_order_and_tuning(self):
        sys.path.insert(0,str(HERE))
        try:
            import race_track01 as track01
            route=copy.deepcopy(track01.world().racing)
            self.assertEqual(errors(route),[])
            route.gates[2].id=route.gates[1].id
            self.assertIn('duplicate gate', '\n'.join(errors(route)))
            route=copy.deepcopy(track01.world().racing)
            route.gates[3].position=route.gates[2].position
            self.assertIn('too close', '\n'.join(errors(route)))
            route=copy.deepcopy(track01.world().racing)
            route.vehicle['boost_speed']=1e9
            self.assertIn('out of bounds','\n'.join(errors(route)))
        finally:
            sys.path.remove(str(HERE))


if __name__=='__main__': unittest.main()
