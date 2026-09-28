"""Content projects (`assetlab project`) and MegaMod: Night Shift, the first
production vertical slice built with one (projects/night_shift)."""
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from assetlab import project, world as worldlib
from assetlab.dependencies import read_library

ROOT = Path(__file__).resolve().parent.parent
NIGHT_SHIFT = ROOT / 'projects' / 'night_shift'


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


TINY = textwrap.dedent('''
    from assetlab.world import Box, Entity, OriginalWorld
    NAME = 'tiny'
    def libraries():
        return {}
    def worlds():
        w = OriginalWorld(id='tiny:world/room', file_name='tiny_room', display_name='Tiny',
                          materials={'floor': (90, 90, 90)}, boxes=[Box((-2, -2, -0.2), (2, 2, 0), 'floor')],
                          spawns=[{'position': [0.0, 0.0, 0.0], 'yaw_degrees': 0.0, 'team': None}],
                          entities=[Entity('tiny:entity/r', 'relay')])
        return [w]
''')


class ProjectCommandTests(unittest.TestCase):
    def test_a_project_builds_into_a_bundle_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'p'; d.mkdir()
            (d / 'project.py').write_text(TINY)
            r = project.build(d, Path(tmp) / 'out')
            self.assertTrue((Path(tmp) / 'out/maps/tiny_room.oalmap').is_file())
            b = r['worlds'][0]['budget']
            self.assertEqual((b['total'], b['headroom'], b['hand_placed']['kinds']), (1, 63, {'relay': 1}))
            self.assertIn('entities 1/64 (headroom 63)', project.text(r))

    def test_budget_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'p'; d.mkdir()
            (d / 'project.py').write_text(TINY)
            r = project.build(d)
            self.assertIsNone(r['output'])
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['p'])

    def test_refusals_name_the_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, 'no project.py'):
                project.load(tmp)
            (Path(tmp) / 'project.py').write_text('def libraries():\n    return {}\n')
            with self.assertRaisesRegex(ValueError, r'a project defines worlds\(\)'):
                project.load(tmp)

    def test_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / 'p'; d.mkdir()
            (d / 'project.py').write_text(TINY)
            out = subprocess.run([sys.executable, '-m', 'assetlab', 'project', 'budget', str(d), '--json'],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout
            self.assertEqual(json.loads(out)['worlds'][0]['budget']['total'], 1)


class NightShiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'a'
        cls.report = project.build(NIGHT_SHIFT, cls.out)
        cls.mod = project.load(NIGHT_SHIFT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_three_packages_and_a_deterministic_build(self):
        again = Path(self.tmp.name) / 'b'
        project.build(NIGHT_SHIFT, again)
        files = ['maps/night_shift.oalmap', 'packages/nightshift.assets.oalasset', 'packages/nightshift.facility.oalasset']
        for f in files:
            self.assertEqual(_sha(self.out / f), _sha(again / f), f)
        self.assertEqual([lib['package'] for lib in self.report['libraries']], ['nightshift.assets', 'nightshift.facility'])
        self.assertEqual(self.report['libraries'][1]['requires'], ['nightshift.assets'])
        w = self.report['worlds'][0]
        self.assertEqual((w['world'], w['package']), ('nightshift:world/harrow_annex', 'nightshift.world01'))

    def test_the_slice_is_pinned(self):
        """The shipped slice's identity (MegaMod's scripts/test_night_shift.sh
        checks the engine agrees). Change deliberately, with the docs."""
        w = self.report['worlds'][0]
        self.assertEqual((w['world_key'], w['budget']['total'], w['budget']['bindings']['total']), ('356266bd', 62, 59))
        digests = {lib['package']: lib['library_digest'] for lib in self.report['libraries']}
        self.assertEqual(digests, {'nightshift.assets': 'de59ce387f6d21e1', 'nightshift.facility': 'ba2f6d488d942451'})

    def test_the_budget_fits_the_runtime(self):
        b = self.report['worlds'][0]['budget']
        self.assertLessEqual(b['total'], worldlib.MAX_ENTITIES)
        self.assertLessEqual(b['bindings']['total'], project.LIMIT_BINDINGS)
        self.assertEqual(b['expanded']['by_prefab']['nightshift:prefab/security_door']['per_instance'], 6)
        self.assertEqual(b['total'], b['hand_placed']['total'] + b['expanded']['total'])

    def test_resources_are_logical_ids_not_paths(self):
        lib = read_library((self.out / 'packages/nightshift.assets.oalasset').read_bytes())
        provides = lib.decl.provides
        for rid in ('nightshift:sound/locked', 'nightshift:sound/alarm', 'nightshift:model/door_panel',
                    'nightshift:material/door_panel', 'nightshift:texture/sign_lift'):
            self.assertIn(rid, provides)
        self.assertTrue(all(':' in p and '/' in p and not p.startswith('/') for p in provides))

    def test_simple_behaviour_is_declarative(self):
        """The prefab library carries no Lua; the world has exactly one script,
        on the one hidden hook a binding uses."""
        libs = self.mod.libraries()
        self.assertEqual(libs['nightshift.facility'].scripts, [])
        w = self.mod.worlds()[0]
        self.assertEqual([s.id for s in w.scripts], ['nightshift:script/anomaly'])
        hooks = [e for e in w.entities if e.script]
        self.assertEqual([e.id for e in hooks], ['nightshift:entity/cold_spot_hook'])
        self.assertLess(hooks[0].reach, 0.1)            # no player can press it
        uses = [b for b in w.bindings if any(a.action == 'use' and a.target == hooks[0].id for a in b.actions)]
        self.assertEqual([b.source for b in uses], ['nightshift:entity/cold_spot'])

    def test_the_security_door(self):
        door = next(p for p in self.mod.libraries()['nightshift.facility'].prefabs if p.id.endswith('/security_door'))
        self.assertEqual(sorted(c.id for c in door.children), ['button', 'button_back', 'door', 'lamp', 'plate', 'power'])
        by = {b.id: b for b in door.bindings}
        self.assertEqual([c.is_ for c in by['locked'].conditions], ['inactive'])
        self.assertEqual([a.action for a in by['toggle'].actions], ['toggle'])
        self.assertEqual([a.action for a in by['unpowered'].actions], ['close', 'close', 'play_sound'])

    def test_the_research_gate_is_an_and(self):
        w = self.mod.worlds()[0]
        gate = [b for b in w.bindings if any(a.target == 'nightshift:entity/d3__power' for a in b.actions)]
        self.assertEqual(sorted((b.source.rsplit('/', 1)[1], b.conditions[0].entity.rsplit('/', 1)[1]) for b in gate),
                         [('coolant_flow', 'security_link'), ('security_link', 'coolant_flow')])

    def test_the_sign_font(self):
        import importlib
        sys.path.insert(0, str(NIGHT_SHIFT))
        try:
            art = importlib.import_module('art')
            self.assertTrue(all(len(g) == 35 for g in art.FONT.values()))
            c = art.text_canvas(['NIGHT SHIFT'], (255, 255, 255), (0, 0, 0))
            self.assertEqual((c.w, c.h), (11 * 6 + 4, 12))
        finally:
            sys.path.remove(str(NIGHT_SHIFT))

    def test_the_cli_summary(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print(project.text(self.report))
        s = buf.getvalue()
        self.assertIn('nightshift:prefab/security_door: 3 x 6 = 18', s)
        self.assertRegex(s, r'entities \d+/64')


if __name__ == '__main__':
    unittest.main()
