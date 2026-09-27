"""Resource identity and package dependencies (MegaMod X4): assetlab.resources,
assetlab.dependencies, and how worlds use them. The engine is the authority:
its grammar verdicts (data/megamod_id_conformance.json) and contract
(data/megamod_resources.json) are what these check against."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from assetlab import dependencies as dep, ids, resources as res, scripts as scriptlib, worldkey
from assetlab.dependencies import Library, PackageError, compile_library, directory_source, mapping_source
from assetlab.fixtures import FIXTURES, X4_PULSE, X4_SHARED, x4_resource_lab, x4_shared
from assetlab.package import read_manifest
from assetlab.resources import Requirement, ResourceError
from assetlab.scripts import Script
from assetlab.world import WorldError, compile_world, declaration, validate

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE = json.loads((ROOT / 'assetlab/data/megamod_id_conformance.json').read_text())
PULSE_SRC = 'function on_ability(p) log(p) end\n'


def lib(pid, names, ns=None, requires=()):
    ns = ns or pid.replace('.', '')
    return Library(pid, [Script(f'{ns}:script/{n}', PULSE_SRC, ['on_ability']) for n in names], list(requires))


class ConformanceTests(unittest.TestCase):
    """Same verdict, same words, as MegaMod's own grammar for every case."""

    def test_resource_ids_match_the_engine(self):
        self.assertEqual(CONFORMANCE['grammar'], res.GRAMMAR['version'])
        for case in CONFORMANCE['resource_ids']:
            code, why, rid = res.parse_id(case['id'])
            self.assertEqual((code, why), (case['result'], case['why']), repr(case['id']))
            self.assertEqual(rid.type if rid and code in (res.OK, res.RESERVED_TYPE) else None, case['type'], case['id'])
            self.assertEqual(code == res.OK and res.reserved_namespace(rid.namespace), case['reserved_namespace'])

    def test_package_ids_match_the_engine(self):
        for case in CONFORMANCE['package_ids']:
            why = res.package_id_error(case['id'])
            self.assertEqual(why is None, case['valid'], case['id'])
            self.assertEqual(why or '', case['why'], case['id'])

    def test_registry_comes_from_the_contract(self):
        contract = json.loads((ROOT / 'assetlab/data/megamod_resources.json').read_text())
        self.assertEqual(contract['contract'], 'megamod.resources')
        self.assertEqual(set(ids.TYPES), {t['name'] for t in contract['types'] if t['status'] == 'supported'})
        # X5: models, materials, textures and sounds are importable resources.
        self.assertEqual(set(res.IMPORTABLE), {'script', 'model', 'material', 'texture', 'sound'})
        self.assertEqual(set(res.RESERVED), {'animation', 'prefab', 'ruleset'})
        self.assertEqual(scriptlib.MAX_SCRIPTS, contract['scripts']['max_scripts'])
        self.assertEqual(scriptlib.MAX_SOURCE, contract['scripts']['max_source_bytes'])
        self.assertEqual(scriptlib.MAX_POOL, contract['scripts']['max_pool_bytes'])
        self.assertEqual(scriptlib.API, contract['scripts']['api'])
        self.assertEqual(worldkey.PLAYED, tuple(contract['world_key']['played_members']))
        self.assertIn('package', worldkey.PLAYED)
        # Every limit comes from there, not from this repository.
        self.assertEqual(res.LIMITS, {'namespace': 40, 'type': 24, 'name': 48, 'total': 96})

    def test_valid_ids(self):
        for good in ('x3:script/button_logic', 'showdown:script/door_controller', 'common:world/lab',
                     'x' * 40 + ':script/' + 'y' * 48):
            self.assertEqual(res.parse_id(good)[0], res.OK, good)
        for reserved in ('community:animation/rifle_run', 'showdown:prefab/security_door', 'showdown:ruleset/tdm'):
            self.assertEqual(res.parse_id(reserved)[0], res.RESERVED_TYPE, reserved)
            self.assertFalse(ids.valid_id(reserved)[0])


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.rs = res.ResourceSet(['x4.lab', 'x4.shared', 'x4.other'])
        self.rs.add('x4:entity/door', 'entity', 0)
        self.rs.add('x4:script/open_door', 'script', 0)
        self.rs.add('x4:mover/door', 'mover', 0)
        self.rs.add('x4shared:script/pulse', 'script', 1)
        self.rs.add('x4shared:script/other', 'script', 1)
        self.rs.add('x4other:script/pulse', 'script', 2)
        self.rs.imports.add((1, 'x4shared:script/pulse'))
        self.rs.required.add(1)

    def fails(self, field_name, ref, want):
        with self.assertRaises(ResourceError) as cm:
            self.rs.resolve(field_name, 'x4:entity/button', ref)
        self.assertIn(want, str(cm.exception))

    def test_typed(self):
        self.assertEqual(self.rs.resolve(res.SCRIPT, 'b', 'x4:script/open_door').provider, 0)
        self.assertEqual(self.rs.resolve(res.ABILITY_SCRIPT, 'b', 'x4shared:script/pulse').provider, 1)
        self.fails(res.SCRIPT, 'x4:mover/door', 'script x4:mover/door is a mover definition, expected a script')
        self.fails(res.LINK_TARGET, 'x4:script/open_door', 'link target x4:script/open_door is a script, expected a placed entity')
        self.fails(res.SCRIPT, 'x4:script/door', 'references missing script x4:script/door (x4:entity/door is a placed entity)')
        self.fails(res.SCRIPT, 'x4:weapon/door', "script 'x4:weapon/door' is not a script ID (namespace:script/name)")
        self.fails(res.SCRIPT, 'x4:prefab/door', "resource type 'prefab' is reserved")
        self.fails(res.SCRIPT, 'x4:model/door', "script 'x4:model/door' is not a script ID")        # X5: supported

    def test_across_packages(self):
        self.fails(res.SCRIPT, 'x4shared:script/other',
                   'is provided by package x4.shared, which package x4.lab requires but does not import it from')
        self.fails(res.SCRIPT, 'x4other:script/pulse', 'is provided by package x4.other, which package x4.lab does not require')
        self.rs.add('x4shared:entity/far', 'entity', 1)
        self.fails(res.LINK_TARGET, 'x4shared:entity/far', 'a link target must be in the same package')

    def test_duplicates_are_refused(self):
        with self.assertRaises(ResourceError) as cm:
            self.rs.add('x4shared:script/pulse', 'script', 0)
        self.assertIn('provided by both package x4.shared and package x4.lab', str(cm.exception))

    def test_nontrivial_counts(self):
        rs = res.ResourceSet()
        t0 = time.perf_counter()
        for i in range(res.PACKAGE_LIMITS['resources_per_set']):
            rs.add(f't:script/s{i}', 'script', 0, i)
        for i in range(res.PACKAGE_LIMITS['resources_per_set']):
            self.assertEqual(rs.resolve(res.SCRIPT, 'who', f't:script/s{i}').index, i)
        self.assertLess(time.perf_counter() - t0, 2.0)
        with self.assertRaises(ResourceError):
            rs.add('t:script/one_more', 'script', 0)


class DeclarationTests(unittest.TestCase):
    def bad(self, member, want):
        with self.assertRaises(ResourceError) as cm:
            res.parse_decl({'package': member})
        self.assertIn(want, str(cm.exception))

    def test_round_trip_is_canonical(self):
        d = res.PackageDecl('x4.lab', ['x4:world/lab', 'x4:script/a'],
                            [Requirement('x4.zeta', ['z:script/b', 'z:script/a']), Requirement('x4.alpha', [])])
        rec = d.record()
        self.assertEqual(rec['provides'], ['x4:script/a', 'x4:world/lab'])
        self.assertEqual([q['package'] for q in rec['requires']], ['x4.alpha', 'x4.zeta'])
        self.assertEqual(rec['requires'][1]['resources'], ['z:script/a', 'z:script/b'])
        back = res.parse_decl({'package': rec})
        self.assertEqual(back.record(), rec)
        self.assertIsNone(res.parse_decl({'id': 'x3:world/lab'}))

    def test_refusals(self):
        base = {'id': 'a', 'provides': [], 'requires': [], 'schema': 1}
        self.bad(base | {'schema': 2}, 'unsupported package schema 2')
        self.bad({k: v for k, v in base.items() if k != 'requires'}, 'needs id, schema, provides and requires')
        self.bad(base | {'version': '1'}, "unknown field 'version'")
        self.bad(base | {'id': 'A'}, "package 'A': package ID segment has capital")
        self.bad(base | {'provides': ['a:script/b', 'a:script/a']}, 'not in canonical (byte) order at a:script/a')
        self.bad(base | {'provides': ['a:script/a', 'a:script/a']}, 'lists a:script/a twice')
        self.bad(base | {'provides': ['a:entity/door']}, 'is a placement, never provided or imported')
        self.bad(base | {'provides': ['megamod:script/x']}, "namespace 'megamod' is reserved")
        self.bad(base | {'requires': [{'package': 'b', 'resources': ['b:mover/door']}]}, 'mover definition cannot be imported')
        self.bad(base | {'requires': [{'package': 'c', 'resources': []}, {'package': 'b', 'resources': []}]},
                 'requires is not in canonical (package ID) order at b')
        self.bad(base | {'requires': [{'package': 'a', 'resources': []}]}, 'package a: requires itself')
        self.bad(base | {'requires': [{'package': 'b:c', 'resources': []}]}, "requires 'b:c'")
        self.bad(base | {'provides': [f'a:script/s{i:04d}' for i in range(257)]}, 'provides has more than 256 entries')
        self.bad(base | {'requires': [{'package': f'p{i:02d}', 'resources': []} for i in range(17)]}, 'requires more than 16 packages')


class GraphTests(unittest.TestCase):
    def load(self, requires, libs):
        root = res.PackageDecl('r.root', ['r:world/root'], requires)
        return dep.load_set(root, mapping_source({l.id: l for l in libs}))

    def fails(self, requires, libs, want):
        with self.assertRaises(PackageError) as cm:
            self.load(requires, libs)
        self.assertIn(want, str(cm.exception))

    def test_none_one_many(self):
        self.assertEqual(dep.load_set(None, None), [])
        self.assertEqual(dep.load_set(res.PackageDecl('r.root', [], []), None), [])
        got = self.load([Requirement('g.a', ['ga:script/p'])], [lib('g.a', ['p'])])
        self.assertEqual([d.decl.id for d in got], ['g.a'])
        self.assertTrue(got[0].direct)
        got = self.load([Requirement('g.a', []), Requirement('g.b', ['gb:script/p'])], [lib('g.a', ['p']), lib('g.b', ['p'])])
        self.assertEqual([d.decl.id for d in got], ['g.a', 'g.b'])

    def test_chain_fan_out_fan_in(self):
        a = lib('g.a', ['p'], requires=[Requirement('g.b', ['gb:script/p'])])
        b = lib('g.b', ['p'], requires=[Requirement('g.c', [])])
        c = lib('g.c', ['p'])
        d = lib('g.d', ['p'], requires=[Requirement('g.b', [])])
        got = self.load([Requirement('g.a', [])], [a, b, c])
        self.assertEqual([(x.decl.id, x.direct) for x in got], [('g.a', True), ('g.b', False), ('g.c', False)])
        got = self.load([Requirement('g.a', []), Requirement('g.d', [])], [a, b, c, d])      # diamond: b once
        self.assertEqual([x.decl.id for x in got], ['g.a', 'g.b', 'g.c', 'g.d'])

    def test_missing_and_wrong(self):
        self.fails([Requirement('g.zzz', [])], [], 'package r.root requires package g.zzz, but it is not present '
                                                   '(looked for packages/g.zzz.oalasset)')
        self.fails([Requirement('g.a', ['ga:script/nope'])], [lib('g.a', ['p'])],
                   'package r.root requires ga:script/nope from package g.a, but package g.a does not provide it')
        liar = lib('c.liar', ['p'])
        with self.assertRaises(PackageError) as cm:
            dep.load_set(res.PackageDecl('r.root', [], [Requirement('c.honest', [])]), mapping_source({'c.honest': liar}))
        self.assertIn('packages/c.honest.oalasset declares package c.liar', str(cm.exception))
        with self.assertRaises(PackageError) as cm:
            dep.load_set(res.PackageDecl('r.root', [], [Requirement('g.a', [])]), None)
        self.assertIn('no package source was given', str(cm.exception))

    def test_cycles_are_refused_with_their_path(self):
        a = lib('c.a', ['p'], requires=[Requirement('c.b', [])])
        b = lib('c.b', ['p'], requires=[Requirement('c.a', [])])
        self.fails([Requirement('c.a', [])], [a, b], 'package cycle: c.a -> c.b -> c.a')
        back = lib('c.r', ['p'], requires=[Requirement('r.root', [])])
        self.fails([Requirement('c.r', [])], [back], 'package cycle: r.root -> c.r -> r.root')

    def test_depth_and_width_are_bounded(self):
        chain = [lib(f'k.d{i}', ['p'], requires=[Requirement(f'k.d{i + 1}', [])] if i < 9 else []) for i in range(1, 10)]
        self.fails([Requirement('k.d1', [])], chain, 'package requirements deeper than 8: r.root -> k.d1')
        self.assertEqual(len(self.load([Requirement('k.d2', [])], chain)), 8)
        wide = [lib(f'w.p{i:02d}', ['p']) for i in range(16)]
        self.assertEqual(len(self.load([Requirement(l.id, []) for l in wide[:15]], wide)), 15)
        self.fails([Requirement(l.id, []) for l in wide], wide, 'more than 16 packages in one set')

    def test_order_found_does_not_matter(self):
        with tempfile.TemporaryDirectory() as t:
            one, two = Path(t, 'one'), Path(t, 'two')
            for d in (one, two):
                (d / 'packages').mkdir(parents=True)
            compile_library(lib('o.a', ['p'], requires=[Requirement('o.b', [])]), one / 'packages/o.a.oalasset')
            compile_library(lib('o.b', ['p']), two / 'packages/o.b.oalasset')
            root = res.PackageDecl('r.root', [], [Requirement('o.a', []), Requirement('o.b', [])])
            x = dep.load_set(root, directory_source(one, two))
            y = dep.load_set(root, directory_source(two, one))
            self.assertEqual([(d.decl.id, d.digest) for d in x], [(d.decl.id, d.digest) for d in y])


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_and_digest(self):
        out = self.dir / 'packages/x4.shared.oalasset'
        _, report = compile_library(x4_shared(), out)
        data = out.read_bytes()
        loaded = dep.read_library(data)
        self.assertEqual(loaded.decl.id, X4_SHARED)
        self.assertEqual(loaded.decl.provides, [X4_PULSE])
        self.assertEqual(f'{loaded.digest:016x}', report['library_digest'])
        self.assertEqual(struct.unpack_from('<4sIIII', data, 0), (b'OALA', 1, len(data) - 32, 0, 0))
        # Deterministic, and provenance is not played.
        compile_library(x4_shared(), self.dir / 'again.oalasset')
        self.assertEqual((self.dir / 'again.oalasset').read_bytes(), data)
        m = json.loads(data[32:])
        m['source_provenance'] = 'elsewhere'
        mb = json.dumps(m, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(dep.library_digest(mb), loaded.digest)
        m['scripts'][0]['source'] += '-- one more line\n'
        mb = json.dumps(m, sort_keys=True, separators=(',', ':')).encode()
        self.assertNotEqual(dep.library_digest(mb), loaded.digest)

    def test_refusals(self):
        bad = Library('X4.shared', [Script('megamod:script/p', PULSE_SRC, ['on_ability'])])
        errs = '\n'.join(dep.validate_library(bad))
        self.assertIn("package 'X4.shared'", errs)
        self.assertIn("namespace 'megamod' is reserved", errs)
        with self.assertRaises(PackageError):
            compile_library(bad, self.dir / 'bad.oalasset')
        self.assertFalse((self.dir / 'bad.oalasset').exists())
        for m, want in (({'kind': 'weapon'}, 'not a library package'),
                        ({'kind': 'library', 'scripts': []}, 'a library must declare its package'),
                        ({'kind': 'library', 'package': {'id': 'l.x', 'provides': ['lx:script/a'], 'requires': [], 'schema': 1},
                          'scripts': []}, 'package l.x lists lx:script/a in provides, but has no such script')):
            mb = json.dumps(m).encode()
            with self.assertRaises(PackageError) as cm:
                dep.read_library(struct.pack('<4sIIII12x', b'OALA', 1, len(mb), 0, 0) + mb)
            self.assertIn(want, str(cm.exception))


class WorldPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.libs = {X4_SHARED: x4_shared()}
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, w, libs=None):
        return '\n'.join(validate(w, mapping_source(self.libs if libs is None else libs)))

    def build(self, w, libs=None):
        self.n += 1
        out = self.dir / f'w{self.n}.oalmap'
        compile_world(w, out, mapping_source(self.libs if libs is None else libs))
        return out

    def test_fixture_declares_and_requires(self):
        out = self.build(x4_resource_lab())
        m = read_manifest(out)
        self.assertEqual(m['package'], {
            'id': 'x4.resource_lab', 'schema': 1,
            'provides': ['x4:mover/basic_slide_door', 'x4:script/open_door', 'x4:world/resource_lab'],
            'requires': [{'package': 'x4.shared', 'resources': ['x4shared:script/pulse_ability']}]})
        section = m['world_entities']
        self.assertEqual(section['ability_script'], X4_PULSE)
        self.assertEqual([s['id'] for s in section['scripts']], ['x4:script/open_door'])     # not copied in
        self.assertNotIn('x4shared', json.dumps(section['scripts']))

    def test_script_to_script_and_wrong_types(self):
        w = x4_resource_lab()
        self.assertEqual(self.errors(w), '')
        w.ability_script = 'x4:mover/basic_slide_door'
        self.assertIn('ability_script: ability script x4:mover/basic_slide_door is a mover definition, expected a script', self.errors(w))
        w = x4_resource_lab()
        button = next(e for e in w.entities if e.script)
        button.script = 'x4:entity/door_a'
        self.assertIn('x4:entity/button_script: script x4:entity/door_a is a placed entity, expected a script', self.errors(w))
        button.script = 'x4:script/open_dor'
        self.assertIn('x4:entity/button_script references missing script x4:script/open_dor', self.errors(w))
        button.script = 'X4:script/open_door'
        self.assertIn("script 'X4:script/open_door' is not a resource ID: namespace has capital 'X'", self.errors(w))

    def test_dependency_rules(self):
        w = x4_resource_lab()
        self.assertIn('package x4.resource_lab requires package x4.shared, but it is not present', self.errors(w, {}))
        w.requires = [Requirement(X4_SHARED, [])]
        self.assertIn('which package x4.resource_lab requires but does not import it from', self.errors(w))
        w.requires = []
        self.assertIn('ability_script references missing script x4shared:script/pulse_ability', self.errors(w))
        w = x4_resource_lab()
        dup = x4_shared()
        dup.scripts.append(Script('x4:script/open_door', 'function on_used(e, p) end\n', ['on_used']))
        self.assertIn('x4:script/open_door: provided by both package x4.resource_lab and package x4.shared',
                      self.errors(w, {X4_SHARED: dup}))
        w.requires = [Requirement('x4.Shared', [X4_PULSE])]
        self.assertIn("package x4.resource_lab: requires 'x4.Shared'", self.errors(w))
        w = x4_resource_lab()
        w.package = 'x4:resource_lab'
        self.assertIn("package 'x4:resource_lab'", self.errors(w))
        with self.assertRaises(WorldError):
            self.build(w)

    def test_imported_callbacks_are_checked(self):
        w = x4_resource_lab()
        button = next(e for e in w.entities if e.script)
        button.script = X4_PULSE
        w.requires = [Requirement(X4_SHARED, [X4_PULSE])]
        self.assertIn(f'x4:entity/button_script: script {X4_PULSE} does not declare on_used', self.errors(w))

    def test_identity(self):
        a = self.build(x4_resource_lab())
        b = self.build(x4_resource_lab())
        self.assertEqual(a.read_bytes(), b.read_bytes())
        # Requirements written in another order: the same bytes.
        w = x4_resource_lab()
        w.requires = list(reversed(w.requires + [Requirement('x4.aaa', [])]))
        libs = dict(self.libs, **{'x4.aaa': lib('x4.aaa', ['p'])})
        c = self.build(w, libs)
        w2 = x4_resource_lab()
        w2.requires = w2.requires + [Requirement('x4.aaa', [])]
        d = self.build(w2, libs)
        self.assertEqual(c.read_bytes(), d.read_bytes())
        src = mapping_source(self.libs)
        k0 = worldkey.world_digest(a.read_bytes(), src)
        # The library's content is part of the world's identity...
        changed = x4_shared()
        changed.scripts[0].source = changed.scripts[0].source.replace('150', '151')
        self.assertNotEqual(worldkey.world_digest(a.read_bytes(), mapping_source({X4_SHARED: changed})), k0)
        # ...its provenance is not.
        moved = x4_shared()
        moved.display_name = 'renamed'
        self.assertEqual(worldkey.world_digest(a.read_bytes(), mapping_source({X4_SHARED: moved})), k0)
        # The world's provenance is not either; its requires are.
        m = read_manifest(a)
        self.assertNotEqual(k0, worldkey.world_digest(c.read_bytes(), mapping_source(libs)))
        with self.assertRaises(PackageError):
            worldkey.world_digest(a.read_bytes(), None)       # its dependency is part of its key
        self.assertEqual(m['package']['id'], 'x4.resource_lab')

    def test_older_fixtures_are_byte_stable(self):
        # X1-X3 packages are exactly what they were before X4 (no package
        # member; world keys unchanged).
        want = {'x1_event_lab': 'b6654d0dda237ad7b07024b3ef3fb26c58c14097089ccd4d1bbca742034396fe',
                'x2_definition_lab': '676e6a14bc3d9eda01c87b8ca0553a3393bce7308a4bdc9f438c174b5a50423a',
                'x3_script_lab': 'a6ae339e84ac57a36a8a61173d6bd1a4191d0453c952492d677afd5f092d1406'}
        keys = {'x1_event_lab': '552c1757', 'x2_definition_lab': '73bd2d8b', 'x3_script_lab': '512a1fc3'}
        for name, sha in want.items():
            out = self.dir / f'{name}.oalmap'
            compile_world(FIXTURES[name](), out)
            self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(), sha, name)
            self.assertNotIn('package', read_manifest(out))
            self.assertEqual(worldkey.world_key(out)['world_key'], keys[name], name)
            self.assertIsNone(declaration(FIXTURES[name]()))

    def test_check_package_catches_what_the_engine_refuses(self):
        out = self.dir / 'bundle/x4_resource_lab.oalmap'
        out.parent.mkdir()
        compile_library(x4_shared(), self.dir / 'bundle/packages/x4.shared.oalasset')
        compile_world(x4_resource_lab(), out, directory_source(self.dir / 'bundle'))
        good = dep.check_package(out, directory_source(out.parent))
        self.assertEqual(good['errors'], [])
        self.assertEqual(good['set'][0]['package'], X4_SHARED)
        data = out.read_bytes()
        ml = struct.unpack_from('<I', data, 8)[0]
        for old, new, want in (
                ('"script":"x4:script/open_door"', '"script":"x4:mover/basic_slide_door"',
                 'script x4:mover/basic_slide_door is a mover definition, expected a script'),
                ('"resources":["x4shared:script/pulse_ability"]', '"resources":[]',
                 'which package x4.resource_lab requires but does not import it from'),
                ('"provides":["x4:mover/basic_slide_door",', '"provides":[',
                 'package x4.resource_lab defines mover definition x4:mover/basic_slide_door but does not list it in provides')):
            mb = data[64:64 + ml].replace(old.encode(), new.encode(), 1)
            v = self.dir / 'bundle' / 'variant.oalmap'
            v.write_bytes(data[:8] + struct.pack('<I', len(mb)) + data[12:64] + mb + data[64 + ml:])
            got = dep.check_package(v, directory_source(out.parent))
            self.assertTrue(any(want in e for e in got['errors']), (want, got['errors']))
        # The command line says so, and fails.
        r = subprocess.run([sys.executable, '-m', 'assetlab', 'resources', 'check', str(v)], capture_output=True, text=True,
                           cwd=ROOT)
        self.assertEqual(r.returncode, 1)
        self.assertIn('REFUSED', r.stdout)


class NeverRunsLuaTests(unittest.TestCase):
    """Open Asset Lab never executes a script: at most `luac -p` parses one."""

    def test_only_a_parse_is_ever_spawned(self):
        calls = []
        real = subprocess.run

        def spy(cmd, *a, **k):
            calls.append(list(cmd))
            return real(cmd, *a, **k)
        loop = x4_shared()
        loop.scripts[0].source = 'while true do end\nos.exit(1)\nfunction on_ability(p) end\n'
        with tempfile.TemporaryDirectory() as t, mock.patch('subprocess.run', spy):
            t0 = time.perf_counter()
            compile_library(loop, Path(t, 'packages/x4.shared.oalasset'))
            compile_world(x4_resource_lab(), Path(t, 'w.oalmap'), directory_source(t))
            dep.check_package(Path(t, 'w.oalmap'), directory_source(t))
            self.assertLess(time.perf_counter() - t0, 30)     # an infinite loop was never run
        for cmd in calls:
            self.assertIn(Path(cmd[0]).name, ('luac5.4', 'luac54', 'luac'), cmd)
            self.assertIn(cmd[1], ('-p', '-v'), cmd)


if __name__ == '__main__':
    unittest.main()
