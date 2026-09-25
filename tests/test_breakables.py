"""Breakable props and map weather in OALMAP packages."""
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import translate
from assetlab.package import GROUP_BREAKABLE, GROUP_NO_COLLISION, compile_map
from tests.test_pipeline import fixture, model_fixture


def groups_of(package):
    data = Path(package).read_bytes()
    _, _, mlen, vc, ic, gc = struct.unpack_from('<4sIIIII', data, 0)
    at = 64 + mlen + vc * 40 + ic * 4
    return [struct.unpack_from('<4I', data, at + i * 16) for i in range(gc)]


class BreakableTests(unittest.TestCase):
    def test_props_are_kept_apart_and_described(self):
        ents = (b'{ "classname" "info_player_start" "origin" "60 60 8" }'
                b'{ "classname" "prop_physics" "model" "models/props/x/crate01.mdl" "origin" "20 20 0" "Health" "35" }'
                b'{ "classname" "prop_physics_multiplayer" "model" "models/props/x/crate01.mdl" "origin" "80 20 0" "health" "0" "ExplodeDamage" "100" }'
                b'{ "classname" "prop_dynamic" "model" "models/props/x/crate01.mdl" "origin" "50 90 0" }'
                b'{ "classname" "func_precipitation" "preciptype" "6" "renderamt" "70" "model" "*1" }')
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'map.bsp').write_bytes(fixture(ents=ents))
            root = t / 'content' / 'models' / 'props' / 'x'
            root.mkdir(parents=True)
            mdl, vvd, vtx = model_fixture()
            (root / 'crate01.mdl').write_bytes(mdl); (root / 'crate01.vvd').write_bytes(vvd)
            (root / 'crate01.dx90.vtx').write_bytes(vtx)
            m, r = compile_map(t / 'map.bsp', t / 'map.oalmap', [t / 'content'])
            b = m['breakables']
            self.assertEqual(len(b), 2)                                    # prop_dynamic stays scenery
            self.assertEqual([x['health'] for x in b], [35.0, 0.0])         # each its own keyvalues
            self.assertEqual([x['explosive'] for x in b], [False, True])
            self.assertEqual(b[1]['blast_radius'], 3.0)
            self.assertEqual(b[0]['material'], 'wood')                      # "crate"
            lo, hi = b[0]['bounds']['min'], b[0]['bounds']['max']
            self.assertTrue(all(h >= l for l, h in zip(lo, hi)))
            self.assertEqual(m['weather'], {'kind': 'storm', 'intensity': 0.7, 'source': 'func_precipitation'})
            self.assertEqual(r['compatibility']['breakables']['count'], 2)
            # The package's groups: one run per breakable, flagged, carrying
            # its index + 1, and out of the static collision.
            tagged = [(g[3] >> 8) & 0xFFFF for g in groups_of(t / 'map.oalmap') if g[3] & GROUP_BREAKABLE]
            self.assertEqual(sorted(set(tagged)), [1, 2])
            for g in groups_of(t / 'map.oalmap'):
                if g[3] & GROUP_BREAKABLE:
                    self.assertTrue(g[3] & GROUP_NO_COLLISION)

    def test_breakable_brushes(self):
        # One brush model, placed four times: a window, a glass pane, a
        # wall that never breaks and one of unbreakable glass.
        ents = (b'{ "classname" "info_player_start" "origin" "60 60 8" }'
                b'{ "classname" "func_breakable" "model" "*1" "origin" "240 0 0" "material" "0" "health" "20" }'
                b'{ "classname" "func_breakable_surf" "model" "*1" "origin" "480 0 0" }'
                b'{ "classname" "func_breakable" "model" "*1" "origin" "720 0 0" "health" "0" }'
                b'{ "classname" "func_breakable" "model" "*1" "origin" "960 0 0" "material" "7" "health" "5" }')
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'map.bsp').write_bytes(fixture(ents=ents, brush_model=True))
            m, r = compile_map(t / 'map.bsp', t / 'map.oalmap', [])
            b = m['breakables']
            self.assertEqual([(x['classname'], x['material'], x['health']) for x in b],
                             [('func_breakable', 'glass', 20.0), ('func_breakable_surf', 'glass', 0.0)])
            self.assertEqual(r['compatibility']['breakables']['brushes'], 2)
            # Each sits where its entity put it, well apart.
            self.assertLess(b[0]['bounds']['max'][0], b[1]['bounds']['min'][0])
            groups = groups_of(t / 'map.oalmap')
            tagged = sorted({(g[3] >> 8) & 0xFFFF for g in groups if g[3] & GROUP_BREAKABLE})
            self.assertEqual(tagged, [1, 2])
            # The two that never break are world geometry: solid, untagged,
            # with the world's own faces (1 + 2 brush copies' worth).
            plain = sum(g[2] for g in groups if not g[3] & GROUP_BREAKABLE)
            broken = sum(g[2] for g in groups if g[3] & GROUP_BREAKABLE)
            self.assertEqual(plain, broken * 3 // 2)

    def test_brush_rules(self):
        self.assertIsNone(translate.brush_breakable({'classname': 'func_breakable', 'health': '10', 'spawnflags': '1'}))
        self.assertIsNone(translate.brush_breakable({'classname': 'func_wall', 'health': '10'}))
        r = translate.brush_breakable({'classname': 'func_breakable', 'health': '50', 'material': '2', 'explodemagnitude': '90'})
        self.assertEqual((r['material'], r['explosive'], r['blast_damage']), ('metal', True, 90.0))
        self.assertEqual(translate.brush_breakable({'classname': 'func_breakable', 'Health': '5'})['material'], 'wood')

    def test_material_words_and_weather(self):
        self.assertEqual(translate.breakable_material('models/props_c17/oildrum001.mdl'), 'metal')
        self.assertEqual(translate.breakable_material('models/props_junk/glassbottle01a.mdl'), 'glass')
        self.assertEqual(translate.breakable_material('models/props_debris/concrete_chunk01a.mdl'), 'concrete')
        self.assertEqual(translate.breakable_material('models/x/thing.mdl', ['models/x/woodfloor']), 'wood')
        self.assertTrue(translate.breakable_explosive('models/props_c17/oildrum001_explosive.mdl', {}))
        self.assertFalse(translate.breakable_explosive('models/props_c17/oildrum001.mdl', {'explodedamage': '0'}))
        self.assertIsNone(translate.map_weather([{'classname': 'light'}]))
        self.assertEqual(translate.map_weather([{'classname': 'func_precipitation', 'preciptype': '1'}])['kind'], 'snow')


if __name__ == '__main__':
    unittest.main()
