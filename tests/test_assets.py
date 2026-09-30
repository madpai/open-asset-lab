"""Package-backed asset resources (MegaMod X5): assetlab.assets, asset
libraries in assetlab.dependencies, props and mover sounds in
assetlab.world, and a Source model imported as MegaMod resources. The engine
is the authority: its member-path verdicts (data/megamod_id_conformance.json)
and contract (data/megamod_resources.json, "assets") are what these check
against; MegaMod's scripts/test_x5.sh checks the same packages through the
real loader."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import assets as assetlib, dependencies as dep, resources as res, worldkey
from assetlab.assets import AssetError, Material, Sound, Texture, box_model
from assetlab.dependencies import Library, PackageError, compile_library, directory_source, mapping_source
from assetlab.fixtures import (FIXTURES, X5_CRATE, X5_CRATE_MAT, X5_CRATE_TEX, X5_IMPACT, X5_SHARED, x5_resource_world,
                               x5_second_world, x5_shared_art, x4_resource_lab, x4_shared)
from assetlab.package import Resolver, read_manifest
from assetlab.resources import Requirement
from assetlab.world import Entity, compile_world, validate

from test_pipeline import model_fixture, vtf

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE = json.loads((ROOT / 'assetlab/data/megamod_id_conformance.json').read_text())
CONTRACT = json.loads((ROOT / 'assetlab/data/megamod_resources.json').read_text())


def art(pid='t.art', ns='ta', requires=(), texture_ref=None, **kw):
    """A small library: one texture, material, model and sound."""
    tex = Texture(f'{ns}:texture/crate', 2, 2, bytes([200, 30, 30, 255] * 4), provenance={'source_path': 'materials/crate.vtf'})
    return Library(pid, [], list(requires), textures=[tex],
                   materials=[Material(f'{ns}:material/crate', texture_ref or tex.id)],
                   models=[box_model(f'{ns}:model/crate', (0.25, 0.25, 0.25), [f'{ns}:material/crate'])],
                   sounds=[Sound(f'{ns}:sound/knock', 22050, 1, b'\x10\x00' * 50)], **kw)


class ContractTests(unittest.TestCase):
    def test_member_paths_match_the_engine(self):
        self.assertTrue(CONFORMANCE['member_paths'])
        for case in CONFORMANCE['member_paths']:
            why = assetlib.member_path_error(case['path'])
            self.assertEqual(why is None, case['valid'], repr(case['path']))
            self.assertEqual(why or '', case['why'], repr(case['path']))

    def test_limits_come_from_the_contract(self):
        a = CONTRACT['assets']
        self.assertEqual(assetlib.SCHEMA, a['schema'])
        self.assertEqual(assetlib.LIMITS, a['limits'])
        self.assertEqual(assetlib.TYPES['model']['max_slots'], 16)
        self.assertEqual(CONTRACT['world_entities']['schema'], 9)          # X10: racing
        self.assertIn('prop', CONTRACT['world_entities']['kinds'])
        # Four asset types are real (X5); prefabs too since X6.
        for t in assetlib.KINDS:
            self.assertEqual(res.TYPES[t]['status'], 'supported', t)
            self.assertTrue(res.TYPES[t]['importable'], t)
        self.assertEqual(res.TYPES['prefab']['status'], 'supported')
        self.assertEqual(res.TYPES['sounds']['importable'], False)       # the UI pack is not a sound resource
        self.assertIn('assets', res.WORLD_KEY['library_members'])
        for f in (res.MATERIAL_TEXTURE, res.MODEL_MATERIAL, res.PROP_MODEL, res.MOVER_SOUND):
            self.assertIn(f, res.REFERENCES)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip(self):
        out = self.dir / 'packages/t.art.oalasset'
        manifest, report = compile_library(art(), out)
        data = out.read_bytes()
        lib = dep.read_library(data)
        self.assertEqual(lib.decl.provides, ['ta:material/crate', 'ta:model/crate', 'ta:sound/knock', 'ta:texture/crate'])
        self.assertEqual(f'{lib.digest:016x}', report['library_digest'])
        self.assertEqual(lib.assets.models[0]['triangles'], 12)
        self.assertEqual(lib.assets.models[0]['bounds'], ((-0.25, -0.25, -0.25), (0.25, 0.25, 0.25)))
        m = manifest['assets']
        self.assertEqual([x['path'] for x in m['members']], ['models/crate.mesh', 'sounds/knock.pcm', 'textures/crate.rgba'])
        self.assertEqual(len(data), 32 + struct.unpack_from('<I', data, 8)[0] + sum(x['size'] for x in m['members']))
        self.assertEqual(manifest['provenance'], {'ta:texture/crate': {'source_path': 'materials/crate.vtf'}})
        # Deterministic.
        compile_library(art(), self.dir / 'again.oalasset')
        self.assertEqual((self.dir / 'again.oalasset').read_bytes(), data)

    def test_digest_covers_payload_not_provenance(self):
        base = dep.read_library(dep.library_bytes(art())).digest
        a = art(); a.textures[0].rgba = bytes([201]) + a.textures[0].rgba[1:]
        self.assertNotEqual(dep.read_library(dep.library_bytes(a)).digest, base)
        a = art(); a.materials[0].draw = 'alpha'
        self.assertNotEqual(dep.read_library(dep.library_bytes(a)).digest, base)
        a = art(); a.sounds[0].pcm = b'\x11\x00' + a.sounds[0].pcm[2:]
        self.assertNotEqual(dep.read_library(dep.library_bytes(a)).digest, base)
        a = art(); a.textures[0].provenance = {'source_path': 'elsewhere.vtf', 'workshop_item': '12345'}
        self.assertEqual(dep.read_library(dep.library_bytes(a)).digest, base)

    def test_x4_library_unchanged(self):
        # A library without assets is byte-for-byte what X4 wrote.
        out = self.dir / 'x4.shared.oalasset'
        compile_library(x4_shared(), out)
        self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),
                         'e41f2981e0bb997813c4ed8a33ec256cbc7b445d87fd8e14488a008c5b839274')
        self.assertNotIn('assets', json.loads(out.read_bytes()[32:]))

    def _refused(self, data, want):
        with self.assertRaises(PackageError) as cm:
            dep.read_library(data)
        self.assertIn(want, str(cm.exception))

    def _patched(self, old=None, new=None, payload=None):
        data = dep.library_bytes(art())
        ml = struct.unpack_from('<I', data, 8)[0]
        m = data[32:32 + ml]
        if old is not None:
            self.assertIn(old.encode(), m)
            m = m.replace(old.encode(), new.encode(), 1)
        return data[:8] + struct.pack('<I', len(m)) + data[12:32] + m + (data[32 + ml:] if payload is None else payload)

    def test_refusals_in_the_engines_words(self):
        P = 'package t.art'
        for old, new, want in (
                ('"member":"models/crate.mesh"', '"member":"models/crates.mesh"',
                 'ta:model/crate declares package member models/crates.mesh, but that member is missing'),
                ('"member":"models/crate.mesh"', '"member":"../crate.mesh"',
                 "ta:model/crate: member path '../crate.mesh': has '..' (no parent references)"),
                ('{"path":"models/crate.mesh"', '{"path":"/models/crate.mesh"', "member path '/models/crate.mesh': starts with '/'"),
                ('"member":"sounds/knock.pcm"', '"member":"textures/crate.rgba"', 'member textures/crate.rgba backs both'),
                ('"width":2}', '"width":3}', 'ta:texture/crate: 3x2 rgba8 is 24 bytes, but member textures/crate.rgba holds 16'),
                ('"frames":50', '"frames":51', 'ta:sound/knock: 51 frames of 1-channel pcm_s16le are 102 bytes'),
                ('"format":"mesh1"', '"format":"mdl"', f"{P}: ta:model/crate: unsupported model format 'mdl'"),
                ('"draw":"opaque"', '"draw":"glow"', "unknown draw 'glow'"),
                ('"width":2}', '"width":2,"vtf":"x"}', f"{P}: ta:texture/crate: unknown or repeated field 'vtf' in assets.textures"),
                ('"schema":1,"sounds"', '"schema":3,"sounds"', f'{P}: unsupported assets schema 3 (this engine has 2)'),
                ('"provides":["ta:material/crate",', '"provides":[', f'{P} has material ta:material/crate but does not list it in provides'),
                ('"ta:texture/crate"],"requires"', '"ta:texture/crate","ta:texture/more"],"requires"',
                 f'{P} lists ta:texture/more in provides, but has no such texture'),
                ('"id":"ta:model/crate"', '"id":"ta:texture/crate"', f'{P}: assets.models: ta:texture/crate is a texture ID, expected a model')):
            self._refused(self._patched(old, new), want)
        self._refused(self._patched(payload=b''), f'{P}: its members add up to')
        mesh = assetlib.mesh1(art().models[0])
        for edit, want in ((lambda b: b[:4].__class__(b'MSH2') + b[4:], 'member models/crate.mesh: not a mesh1 payload'),
                           (lambda b: b[:4] + struct.pack('<I', 25) + b[8:], 'is 1132 bytes, but its counts need 1172'),
                           (lambda b: b[:16 + 24 * 40 + 8] + struct.pack('<I', 24) + b[16 + 24 * 40 + 12:], 'index 2 names vertex 24 of 24'),
                           (lambda b: b[:-4] + struct.pack('<I', 1), 'group 0 draws with material slot 1, but the model has 1'),
                           (lambda b: b[:16] + struct.pack('<f', float('nan')) + b[20:], 'vertex 0 is not finite')):
            data = dep.library_bytes(art())
            ml = struct.unpack_from('<I', data, 8)[0]
            payload = data[32 + ml:]
            self.assertTrue(payload.startswith(mesh))
            self._refused(data[:32 + ml] + edit(mesh) + payload[len(mesh):], want)

    def test_validate_before_writing(self):
        bad = art()
        bad.textures[0].member = 'Textures/crate.rgba'
        bad.models.append(box_model('ta:texture/oops', (1, 1, 1), ['ta:material/crate']))
        errs = '\n'.join(dep.validate_library(bad))
        self.assertIn("member path 'Textures/crate.rgba': has capital 'T'", errs)
        self.assertIn('assets.models: ta:texture/oops is a texture ID, expected a model', errs)
        with self.assertRaises(PackageError):
            compile_library(bad, self.dir / 'bad.oalasset')
        self.assertFalse((self.dir / 'bad.oalasset').exists())
        # A material naming a texture the library neither has nor imports.
        errs = '\n'.join(dep.validate_library(art(texture_ref='ta:texture/nope')))
        self.assertIn('ta:material/crate references missing texture ta:texture/nope', errs)

    def test_a_library_imports_another_librarys_texture(self):
        base = art()
        skin = Library('t.skin', [], [Requirement('t.art', ['ta:texture/crate'])],
                       materials=[Material('sk:material/glass', 'ta:texture/crate', 'alpha')],
                       models=[box_model('sk:model/pane', (1, 0.05, 1), ['sk:material/glass'])])
        libs = {'t.art': base, 't.skin': skin}
        self.assertEqual(dep.validate_library(skin, mapping_source(libs)), [])
        not_imported = Library('t.skin', [], [Requirement('t.art', [])], materials=skin.materials, models=skin.models)
        errs = '\n'.join(dep.validate_library(not_imported, mapping_source(libs)))
        self.assertIn('sk:material/glass: texture ta:texture/crate is provided by package t.art, which package t.skin requires '
                      'but does not import it from', errs)
        slot_is_texture = Library('t.skin', [], [Requirement('t.art', ['ta:texture/crate'])],
                                  models=[box_model('sk:model/pane', (1, 0.05, 1), ['ta:texture/crate'])])
        errs = '\n'.join(dep.validate_library(slot_is_texture, mapping_source(libs)))
        self.assertIn('sk:model/pane: material slot ta:texture/crate is a texture, expected a material', errs)


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.libs = {X5_SHARED: x5_shared_art()}

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, w):
        return '\n'.join(validate(w, mapping_source(self.libs)))

    def test_fixture_places_imported_props(self):
        out = self.dir / 'w.oalmap'
        _, report = compile_world(x5_resource_world(), out, mapping_source(self.libs))
        m = read_manifest(out)
        section = m['world_entities']
        self.assertEqual(section['schema'], 4)
        crate = next(e for e in section['entities'] if e['id'] == 'x5:entity/crate_a')
        self.assertEqual(crate, {'id': 'x5:entity/crate_a', 'kind': 'prop', 'links': [], 'model': X5_CRATE,
                                 'position': [-2.0, 1.2, 0.25]})
        self.assertEqual(section['mover_definitions'][0]['sound'], X5_IMPACT)
        self.assertEqual(m['package']['requires'], [{'package': X5_SHARED, 'resources': [X5_CRATE, X5_IMPACT]}])
        self.assertNotIn(X5_CRATE, m['package']['provides'])
        # The world does not carry the library's bytes.
        lib = dep.library_bytes(self.libs[X5_SHARED])
        payload = lib[32 + struct.unpack_from('<I', lib, 8)[0]:]
        self.assertNotIn(payload[:1024], out.read_bytes())
        self.assertNotIn(b'MSH1', out.read_bytes())
        self.assertEqual(report['props'], {'x5:entity/crate_a': X5_CRATE, 'x5:entity/crate_b': X5_CRATE})

    def test_refusals(self):
        w = x5_resource_world(); w.requires = []
        self.assertIn("missing model x5shared:model/test_crate (no package in this set provides namespace 'x5shared': "
                      "is a requirement missing?)", self.errors(w))
        w = x5_resource_world(); w.requires = [Requirement(X5_SHARED, [X5_IMPACT])]
        self.assertIn('x5:entity/crate_a: model x5shared:model/test_crate is provided by package x5.shared_art, which package '
                      'x5.resource_world requires but does not import it from', self.errors(w))
        w = x5_resource_world(); w.entities[-1].model = X5_CRATE_MAT
        self.assertIn('x5:entity/crate_b: model x5shared:material/test_crate is a material, expected a model', self.errors(w))
        w = x5_resource_world(); w.mover_definitions[0].sound = X5_CRATE
        self.assertIn('x5:mover/basic_slide_door: sound x5shared:model/test_crate is a model, expected a sound', self.errors(w))
        w = x5_resource_world(); w.entities[-1].model = None
        self.assertIn('x5:entity/crate_b: a prop needs a model', self.errors(w))
        w = x5_resource_world(); w.entities[0].model = X5_CRATE
        self.assertIn('only a prop takes a model', self.errors(w))
        w = x5_resource_world(); w.entities[-1].model = 'x5shared:ruleset/crate'
        self.assertIn("resource type 'ruleset' is reserved", self.errors(w))
        w = x5_resource_world(); w.requires = [Requirement('x5.gone', [])]
        self.assertIn('requires package x5.gone, but it is not present (looked for packages/x5.gone.oalasset)', self.errors(w))
        self.assertEqual(self.errors(x5_resource_world()), '')

    def test_inline_movers_stay_schema_1(self):
        from assetlab.fixtures import x1_event_lab, eid
        w = x1_event_lab()
        w.entities.append(Entity(eid('crate'), 'prop', position=(-2, 1, 0.25), model=X5_CRATE))
        w.package, w.requires = 'x1.with_props', [Requirement(X5_SHARED, [X5_CRATE])]
        self.assertIn('x1:entity/door_main: a world with props or mover sounds (world_entities schema 4) gives every mover a '
                      'definition', self.errors(w))

    def test_keys_pinned_and_two_consumers_share_one_library(self):
        keys = {}
        for name, fn in (('x5_resource_world', x5_resource_world), ('x5_second_world', x5_second_world)):
            out = self.dir / f'{name}.oalmap'
            compile_world(fn(), out, mapping_source(self.libs))
            keys[name] = worldkey.world_key(out, mapping_source(self.libs))['world_key']
            report = dep.check_package(out, mapping_source(self.libs))
            self.assertEqual(report['errors'], [], name)
            self.assertEqual(report['set'][0]['package'], X5_SHARED)
        # The engine agrees (MegaMod scripts/test_x5.sh).
        self.assertEqual(keys, {'x5_resource_world': '1b067045', 'x5_second_world': '6748f47e'})
        # One texel of the library is a new key for BOTH consumers; its
        # provenance is not.
        changed = x5_shared_art()
        changed.textures[0].rgba = bytes([0]) + changed.textures[0].rgba[1:]
        prov = x5_shared_art()
        prov.models[0].provenance = {'provider': 'steam_workshop', 'workshop_item': '123', 'source_path': 'models/crate.mdl'}
        for name in keys:
            data = (self.dir / f'{name}.oalmap').read_bytes()
            self.assertNotEqual(worldkey.fold(worldkey.world_digest(data, mapping_source({X5_SHARED: changed}))),
                                int(keys[name], 16))
            self.assertEqual(worldkey.fold(worldkey.world_digest(data, mapping_source({X5_SHARED: prov}))), int(keys[name], 16))

    def test_older_fixtures_byte_stable(self):
        # X4's world and library are what X4 wrote; X1-X3 are pinned in
        # test_resources.
        out = self.dir / 'x4_resource_lab.oalmap'
        compile_world(x4_resource_lab(), out, mapping_source({'x4.shared': x4_shared()}))
        self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(),
                         '13687f4b74b268567e498eb8751e7d19d6886f939d6597108e076681db4b9afc')
        self.assertEqual(worldkey.world_key(out, mapping_source({'x4.shared': x4_shared()}))['world_key'], '46bee75f')
        self.assertEqual(set(FIXTURES) - {'x6_prefab_world', 'x6_second_world', 'x7_facility_world', 'x7_second_world'},   # X6, X7 add their own
                         {'x1_event_lab', 'x2_definition_lab', 'x3_script_lab', 'x4_resource_lab', 'x5_resource_world',
                          'x5_second_world'})

    def test_check_package_reads_an_asset_library(self):
        lib = self.dir / 'packages/x5.shared_art.oalasset'
        compile_library(x5_shared_art(), lib)
        r = dep.check_package(lib, directory_source(self.dir))
        self.assertEqual(r['errors'], [])
        self.assertEqual(r['provides'], [X5_CRATE_MAT, X5_CRATE, X5_IMPACT, X5_CRATE_TEX])


class SourceModelTests(unittest.TestCase):
    """A Source static prop becomes MegaMod resources: IDs are MegaMod's,
    Source paths are provenance."""

    def test_mdl_to_resources(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mdl, vvd, vtx = model_fixture()
            (root / 'models/props/x').mkdir(parents=True)
            for ext, blob in (('.mdl', mdl), ('.vvd', vvd), ('.dx90.vtx', vtx)):
                (root / f'models/props/x/crate01{ext}').write_bytes(blob)
            (root / 'materials/models/props/x').mkdir(parents=True)
            (root / 'materials/models/props/x/crate01.vmt').write_text('"VertexLitGeneric" { "$basetexture" "models/props/x/crate01" }')
            (root / 'materials/models/props/x/crate01.vtf').write_bytes(
                vtf(2, 2, lambda w, h, f: bytes([10, 20, 30, 255]) * (w * h)))
            resolver = Resolver(None, roots=[root])
            model, materials, textures, report = assetlib.from_source_model(
                resolver, 'models/props/x/crate01.mdl', 'community',
                provider={'provider': 'steam_workshop', 'workshop_item': '424242', 'license': 'unknown'})
        self.assertEqual(model.id, 'community:model/crate01')
        self.assertEqual([m.id for m in materials], ['community:material/crate01'])
        self.assertEqual(textures[0].id, 'community:texture/crate01')
        self.assertEqual(textures[0].rgba[:4], bytes([10, 20, 30, 255]))
        self.assertEqual(report['missing_textures'], [])
        # Runtime units (a Source inch is 1/120 wu); the Source paths are provenance only.
        self.assertAlmostEqual(model.vertices[1][0][0], 10 / 120)
        self.assertEqual(model.provenance['source_path'], 'models/props/x/crate01.mdl')
        self.assertEqual(model.provenance['workshop_item'], '424242')
        self.assertEqual(materials[0].provenance['source_material'], 'materials/models/props/x/crate01.vmt')
        for r in [model] + materials + textures:
            self.assertEqual(res.parse_id(r.id)[0], res.OK)
            self.assertNotIn('/props/', r.id)
        # ...and packages as a library the engine's rules accept.
        lib = Library('community.props', [], textures=textures, materials=materials, models=[model])
        data = dep.library_bytes(lib)
        loaded = dep.read_library(data)
        self.assertEqual(loaded.decl.provides, ['community:material/crate01', 'community:model/crate01', 'community:texture/crate01'])
        m = json.loads(data[32:32 + struct.unpack_from('<I', data, 8)[0]])
        self.assertEqual(m['provenance']['community:model/crate01']['source_path'], 'models/props/x/crate01.mdl')
        self.assertNotIn('provenance', m['assets'])


if __name__ == '__main__':
    unittest.main()
