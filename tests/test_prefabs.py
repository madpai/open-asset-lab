"""Prefabs (MegaMod X6): assetlab.prefabs, prefab libraries in
assetlab.dependencies, prefab instances in assetlab.world, and a Source
model composed into a prefab. The engine is the authority: its local-ID
verdicts (data/megamod_id_conformance.json, "local_ids") and contract
(data/megamod_resources.json, "prefabs") are what these check against;
MegaMod's tests/test_prefab.c and scripts/test_x6.sh check the same rules and
packages through the real loader, with the same words."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import assets as assetlib, dependencies as dep, prefabs as pf, resources as res, worldkey
from assetlab.dependencies import Library, PackageError, compile_library, mapping_source
from assetlab.fixtures import (FIXTURES, X6_DOOR, X6_FACILITY, X6_SHARED, x6_facility, x6_libraries, x6_prefab_world,
                               x6_second_world, x6_security_door, x6_shared_assets)
from assetlab.package import Resolver
from assetlab.prefabs import Prefab, PrefabChild, PrefabInstance, PrefabLink
from assetlab.resources import Requirement
from assetlab.scripts import Script
from assetlab.world import Entity, Link, compile_world, validate

from test_pipeline import model_fixture, vtf

ROOT = Path(__file__).resolve().parents[1]
CONFORMANCE = json.loads((ROOT / 'assetlab/data/megamod_id_conformance.json').read_text())
CONTRACT = json.loads((ROOT / 'assetlab/data/megamod_resources.json').read_text())


def errors_of_world(w, libs=None):
    return '\n'.join(validate(w, mapping_source(libs if libs is not None else x6_libraries())))


def errors_of_library(lib, libs=None):
    return '\n'.join(dep.validate_library(lib, mapping_source(libs if libs is not None else x6_libraries())))


class ContractTests(unittest.TestCase):
    def test_local_ids_match_the_engine(self):
        self.assertTrue(CONFORMANCE['local_ids'])
        for case in CONFORMANCE['local_ids']:
            why = pf.local_id_error(case['id'], 'local id')
            self.assertEqual(why is None, case['valid'], repr(case['id']))
            self.assertEqual(why or '', case['why'], repr(case['id']))

    def test_prefab_is_supported_and_rules_come_from_the_contract(self):
        p = CONTRACT['prefabs']
        self.assertEqual(res.TYPES['prefab']['status'], 'supported')
        self.assertTrue(res.TYPES['prefab']['importable'])
        self.assertEqual(pf.SCHEMA, 2)                    # X7 reads 1 and 2; an X6 prefab is still written as 1
        self.assertEqual(pf.member_schema([x6_security_door()]), 1)
        self.assertEqual(pf.LIMITS, p['limits'])
        self.assertEqual(pf.LIMITS['children'], 16)
        self.assertEqual(pf.LIMITS['expanded_entities'], 1024)
        self.assertFalse(p['nesting']['supported'])
        self.assertEqual(pf.SEP, '__')
        self.assertEqual(set(pf.KINDS), {'interactable', 'relay', 'mover', 'trigger', 'teleport', 'prop'})
        self.assertIn('prefabs', res.WORLD_KEY['library_members'])
        self.assertEqual(CONTRACT['world_entities']['schema'], 6)
        for f in (pf.CHILD_MODEL, pf.CHILD_SOUND, pf.CHILD_SCRIPT, pf.INSTANCE_PREFAB):
            self.assertIn(f, res.REFERENCES)
        self.assertEqual(res.REFERENCES[pf.INSTANCE_PREFAB]['expects'], 'prefab')

    def test_transform_is_exact_at_right_angles(self):
        self.assertEqual(pf.cossin(-90.0), (0.0, -1.0))
        self.assertEqual(pf.cossin(450.0), (0.0, 1.0))
        self.assertEqual(pf.xform_point((-3.0, -2.0, 0.0), 1.0, pf.cossin(-90.0), (-0.16, -0.7, 0.9)), (-3.7, -2.0 + 0.16, 0.9))
        self.assertTrue(pf.axis_aligned(-270.0) and not pf.axis_aligned(45.0))


class LibraryTests(unittest.TestCase):
    def test_round_trip_and_canonical_bytes(self):
        lib = x6_facility()
        a = dep.library_bytes(lib)
        lib.prefabs[0].children.reverse()                 # authored in any order, written canonically
        self.assertEqual(dep.library_bytes(lib), a)
        loaded = dep.read_library(a)
        self.assertEqual(loaded.decl.provides, [X6_DOOR, 'x6:script/security_door_log'])
        self.assertEqual([c['id'] for c in loaded.prefabs[0]['children']],
                         ['button', 'button_panel', 'door', 'frame_left', 'frame_right', 'frame_top'])
        m = json.loads(a[32:32 + struct.unpack_from('<I', a, 8)[0]])
        self.assertEqual(m['prefabs']['schema'], 1)
        self.assertIn(X6_DOOR, m['provenance'])             # provenance beside, never inside the played member
        self.assertNotIn('provenance', json.dumps(m['prefabs']))

    def test_references_resolve_from_the_providers_view(self):
        deps = dep.load_set(res.PackageDecl('w', [], [Requirement(X6_FACILITY, [X6_DOOR])]), mapping_source(x6_libraries()))
        fac = next(d for d in deps if d.decl.id == X6_FACILITY)
        door = next(c for c in fac.prefabs[0]['children'] if c['id'] == 'door')
        self.assertEqual(door['model_index'], 1)            # x6shared:model/door_panel in the set's table
        self.assertEqual(door['sound_index'], 0)
        button = fac.prefabs[0]['children'][0]
        self.assertEqual(button['script_provider'], X6_FACILITY)

    def test_digest_covers_prefabs_not_provenance(self):
        base = dep.read_library(dep.library_bytes(x6_facility())).digest
        moved = x6_facility()
        moved.prefabs[0].children[4].position = (0.0, 0.71, 0.7)
        self.assertNotEqual(dep.read_library(dep.library_bytes(moved)).digest, base)
        prov = x6_facility()
        prov.prefabs[0].provenance = {'creator': 'someone else'}
        self.assertEqual(dep.read_library(dep.library_bytes(prov)).digest, base)

    def test_refusals_in_the_engines_words(self):
        P = 'prefab x6:prefab/security_door'

        def fac(edit):
            lib = x6_facility()
            edit(lib.prefabs[0].children)
            return errors_of_library(lib)
        self.assertIn(f"{P} contains duplicate local child id 'frame_left'",
                      fac(lambda c: setattr(c[4], 'id', 'frame_left')))
        self.assertIn(f"{P} child 'button' references missing child 'dor'",
                      fac(lambda c: setattr(c[0].links[0], 'target', 'dor')))
        self.assertIn(f"{P} child 'button' links to itself", fac(lambda c: setattr(c[0].links[0], 'target', 'button')))
        self.assertIn(f"{P} child 'button' links to child 'frame_top', and a prop does not accept 'toggle'",
                      fac(lambda c: setattr(c[0].links[0], 'target', 'frame_top')))
        self.assertIn(f"{P} child 'frame_top' contains a nested prefab reference, which is not supported in prefab schema 1",
                      fac(lambda c: setattr(c[5], 'kind', 'prefab')))
        self.assertIn(f"{P} child 'frame_top': unknown kind 'widget'", fac(lambda c: setattr(c[5], 'kind', 'widget')))
        self.assertIn(f"{P} child 'Frame_top': local child id has capital 'F'", fac(lambda c: setattr(c[5], 'id', 'Frame_top')))
        self.assertIn(f"{P} child 'door': a mover needs 'speed'", fac(lambda c: setattr(c[2], 'speed', None)))
        self.assertIn(f"{P} child 'frame_top': a prop does not take 'reach'", fac(lambda c: setattr(c[5], 'reach', 1.0)))
        self.assertIn(f"{P} child 'door': mover speed out of range", fac(lambda c: setattr(c[2], 'speed', 0.0)))
        self.assertIn(f"{P} child 'door' references missing model x6shared:model/door_panels",
                      fac(lambda c: setattr(c[2], 'model', 'x6shared:model/door_panels')))
        self.assertIn(f"{P} child 'frame_top': model x6shared:sound/door_hiss is a sound, expected a model",
                      fac(lambda c: setattr(c[5], 'model', 'x6shared:sound/door_hiss')))
        self.assertIn(f"{P} child 'door': sound 'X6shared:sound/door_hiss' is not a resource ID",
                      fac(lambda c: setattr(c[2], 'sound', 'X6shared:sound/door_hiss')))
        self.assertIn(f"{P} child 'button' references missing script x6:script/nothing",
                      fac(lambda c: setattr(c[0], 'script', 'x6:script/nothing')))
        # A relay cycle inside a prefab.
        self.assertIn(f'{P}: link cycle: a -> b -> a', fac(lambda c: c.extend([
            PrefabChild('a', 'relay', [PrefabLink('fired', 'b', 'activate')]),
            PrefabChild('b', 'relay', [PrefabLink('fired', 'a', 'activate')])])))
        # Too many children.
        self.assertIn(f'{P} has more than 16 children',
                      fac(lambda c: c.extend(PrefabChild(f'r{i:02d}', 'relay') for i in range(11))))
        # An import the provider did not declare.
        lib = x6_facility()
        lib.requires[0].resources.remove('x6shared:model/frame_top')
        self.assertIn(f"{P} child 'frame_top': model x6shared:model/frame_top is provided by package x6.shared_assets, "
                      'which package x6.facility requires but does not import it from', errors_of_library(lib))
        # A script without on_used.
        lib = x6_facility()
        lib.scripts = [Script('x6:script/security_door_log', 'function on_ability(p) end', ['on_ability'])]
        self.assertIn(f"{P} child 'button': script x6:script/security_door_log does not declare on_used",
                      errors_of_library(lib))
        # A malformed prefab ID; provides that disagree (the reader).
        self.assertIn("prefab 'x6:prefab/Door' is not a resource ID: name has capital 'D'",
                      '\n'.join(pf.validate([Prefab('x6:prefab/Door', x6_security_door().children)], 'x6.facility')))
        data = bytearray(dep.library_bytes(x6_facility()))
        ml = struct.unpack_from('<I', data, 8)[0]
        m = data[32:32 + ml].replace(b'"provides":["x6:prefab/security_door",', b'"provides":[')
        bad = bytes(data[:8]) + struct.pack('<I', len(m)) + bytes(data[12:32]) + bytes(m)
        with self.assertRaises(PackageError) as cm:
            dep.read_library(bad)
        self.assertIn('package x6.facility has prefab x6:prefab/security_door but does not list it in provides', str(cm.exception))


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_expansion(self):
        w = x6_prefab_world()
        self.assertEqual(errors_of_world(w), '')
        _, report = compile_world(w, self.dir / 'w.oalmap', mapping_source(x6_libraries()))
        self.assertEqual(report['entity_schema'], 5)
        ex = report['expanded']
        self.assertEqual(len(ex), 12)
        self.assertEqual(ex[0], {'path': 'north_door/button', 'entity': 'x6:entity/north_door__button', 'kind': 'interactable', 'index': 1})
        self.assertEqual(ex[8]['entity'], 'x6:entity/south_door__door')
        self.assertEqual(ex[8]['index'], 9)
        # The world imports the prefab, nothing else.
        m = json.loads((self.dir / 'w.oalmap').read_bytes()[64:64 + struct.unpack_from('<I', (self.dir / 'w.oalmap').read_bytes(), 8)[0]])
        self.assertEqual(m['package']['requires'], [{'package': X6_FACILITY, 'resources': [X6_DOOR]}])
        self.assertEqual([i['id'] for i in m['world_entities']['prefab_instances']], ['north_door', 'south_door'])
        # Turned -90: its door slides +x, its button stands north of the wall.
        s = pf.expand('x6', {'id': 'south_door', 'position': [-3.0, -2.0, 0.0], 'prefab': X6_DOOR, 'yaw_degrees': -90.0},
                      pf.parse({'prefabs': pf.member([x6_security_door()])}, 'p')[0])
        door = next(e for e in s if e['child'] == 'door')
        self.assertEqual(door['move'], (1.3, 0.0, 0.0))
        self.assertEqual(s[0]['position'], (-3.7, -1.84, 0.9))

    def test_refusals_in_the_engines_words(self):
        w = x6_prefab_world(); w.requires = [Requirement(X6_FACILITY, [])]
        self.assertIn('prefab instance north_door: prefab x6:prefab/security_door is provided by package x6.facility, which '
                      'package x6.prefab_world requires but does not import it from', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[0].prefab = 'x6:prefab/security_dor'
        self.assertIn('prefab instance north_door references missing prefab x6:prefab/security_dor', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[0].prefab = 'x6:script/security_door_log'
        self.assertIn('prefab instance north_door: prefab x6:script/security_door_log is a script, expected a prefab', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[1].scale = 0.0
        self.assertIn('prefab instance south_door: scale 0 out of range (uniform, 0.25 to 4)', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[1].scale = float('nan')
        self.assertIn('prefab instance south_door: scale nan out of range', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[1].scale = float('inf')
        self.assertIn('prefab instance south_door: scale inf out of range', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[1].yaw_degrees = 720.0
        self.assertIn('prefab instance south_door: yaw_degrees out of range (|yaw| <= 360)', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[1].id = 'north_door'
        self.assertIn('prefab instance north_door appears twice', errors_of_world(w))
        w = x6_prefab_world(); w.prefab_instances[0].id = 'no__rth'
        self.assertIn("prefab instance 'no__rth': instance id has '__'", errors_of_world(w))
        w = x6_prefab_world(); w.entities.append(Entity('x6:entity/north_door__door', 'relay'))
        self.assertIn("x6:entity/north_door__door: '__' is reserved for prefab children", errors_of_world(w))
        w = x6_prefab_world()
        w.prefab_instances += [PrefabInstance(f'n{i:02d}', X6_DOOR, (0.0, 0.0, 0.0)) for i in range(11)]
        self.assertEqual(errors_of_world(w), '')  # X8: 67 objects are ordinary, within the runtime limit
        w = x6_prefab_world(); w.prefab_instances[1].scale = 4.0
        self.assertIn("prefab instance south_door (x6:prefab/security_door) child 'button': reach 4.8 after scale 4 exceeds 4 wu",
                      errors_of_world(w))
        self.assertIn('requires package x6.facility, but it is not present', errors_of_world(x6_prefab_world(), {}))
        libs = x6_libraries(); del libs[X6_SHARED]
        self.assertIn('package x6.facility requires package x6.shared_assets, but it is not present', errors_of_world(x6_prefab_world(), libs))

    def test_world_links_and_scripts_may_name_a_child(self):
        w = x6_prefab_world()
        w.entities.append(Entity('x6:entity/panic', 'interactable', [Link('used', 'x6:entity/south_door__door', 'close')],
                                 position=(-4.0, 0.0, 0.9), reach=1.0))
        self.assertEqual(errors_of_world(w), '')
        w.entities[-1].links[0].target = 'x6:entity/south_door__dor'
        self.assertIn('x6:entity/panic references missing placed entity x6:entity/south_door__dor', errors_of_world(w))

    def test_prop_transform_is_schema_5(self):
        from assetlab.fixtures import x5_resource_world, x5_shared_art
        w = x5_resource_world()
        w.entities[-1].yaw_degrees = 30.0
        w.entities[-1].scale = 1.5
        _, report = compile_world(w, self.dir / 'p.oalmap', mapping_source({'x5.shared_art': x5_shared_art()}))
        self.assertEqual(report['entity_schema'], 5)
        w.entities[-1].scale = 9.0
        self.assertIn('x5:entity/crate_b: scale 9 out of range (uniform, 0.25 to 4)',
                      '\n'.join(validate(w, mapping_source({'x5.shared_art': x5_shared_art()}))))

    def test_keys_pinned_two_consumers_one_prefab(self):
        libs = x6_libraries()
        keys = {}
        for name, fn in (('x6_prefab_world', x6_prefab_world), ('x6_second_world', x6_second_world)):
            out = self.dir / f'{name}.oalmap'
            compile_world(fn(), out, mapping_source(libs))
            keys[name] = worldkey.world_key(out, mapping_source(libs))['world_key']
            r = dep.check_package(out, mapping_source(libs))
            self.assertEqual(r['errors'], [], name)
            self.assertEqual([d['package'] for d in r['set']], [X6_FACILITY, X6_SHARED])
            self.assertEqual([d['direct'] for d in r['set']], [True, False])
        # The engine agrees (MegaMod scripts/test_x6.sh).
        self.assertEqual(keys, {'x6_prefab_world': PINNED['x6_prefab_world'], 'x6_second_world': PINNED['x6_second_world']})
        # A prefab child moved, or one texel of the art the world never
        # imported: a new key. The prefab's provenance: the same key.
        data = (self.dir / 'x6_prefab_world.oalmap').read_bytes()
        moved = x6_libraries(); moved[X6_FACILITY].prefabs[0].children[4].position = (0.0, 0.71, 0.7)
        texel = x6_libraries(); t = texel[X6_SHARED].textures[0]; t.rgba = bytes([t.rgba[0] ^ 1]) + t.rgba[1:]
        prov = x6_libraries(); prov[X6_FACILITY].prefabs[0].provenance = {'creator': 'elsewhere'}
        k = lambda libs_: f'{worldkey.fold(worldkey.world_digest(data, mapping_source(libs_))):08x}'
        self.assertNotEqual(k(moved), keys['x6_prefab_world'])
        self.assertNotEqual(k(texel), keys['x6_prefab_world'])
        self.assertEqual(k(prov), keys['x6_prefab_world'])
        # An instance's identity is gameplay (scripts and links may name it).
        w = x6_prefab_world(); w.prefab_instances[0].id = 'nort_door'
        compile_world(w, self.dir / 'r.oalmap', mapping_source(libs))
        self.assertNotEqual(worldkey.world_key(self.dir / 'r.oalmap', mapping_source(libs))['world_key'], keys['x6_prefab_world'])

    def test_older_fixtures_unchanged(self):
        # X1-X5 fixtures keep their bytes and keys (also pinned in
        # test_resources and test_assets); X6 only adds.
        self.assertEqual(set(FIXTURES) - {'x6_prefab_world', 'x6_second_world', 'x7_facility_world', 'x7_second_world'},
                         {'x1_event_lab', 'x2_definition_lab', 'x3_script_lab', 'x4_resource_lab', 'x5_resource_world',
                          'x5_second_world'})
        from assetlab.fixtures import x5_resource_world, x5_shared_art
        out = self.dir / 'x5.oalmap'
        compile_world(x5_resource_world(), out, mapping_source({'x5.shared_art': x5_shared_art()}))
        self.assertEqual(worldkey.world_key(out, mapping_source({'x5.shared_art': x5_shared_art()}))['world_key'], '1b067045')
        lib = dep.library_bytes(x5_shared_art())
        self.assertNotIn(b'"prefabs"', lib)


PINNED = {'x6_prefab_world': '55b83b8b', 'x6_second_world': 'f99b737d'}


class SourceModelIntoPrefabTests(unittest.TestCase):
    """X5 turns a Source prop into MegaMod resources; X6 composes them. No
    provider knowledge reaches the prefab: it names resource IDs."""

    def test_imported_model_composed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mdl, vvd, vtx = model_fixture()
            (root / 'models/props/x').mkdir(parents=True)
            for ext, blob in (('.mdl', mdl), ('.vvd', vvd), ('.dx90.vtx', vtx)):
                (root / f'models/props/x/crate01{ext}').write_bytes(blob)
            (root / 'materials/models/props/x').mkdir(parents=True)
            (root / 'materials/models/props/x/crate01.vmt').write_text('"VertexLitGeneric" { "$basetexture" "models/props/x/crate01" }')
            (root / 'materials/models/props/x/crate01.vtf').write_bytes(vtf(2, 2, lambda w, h, f: bytes([10, 20, 30, 255]) * (w * h)))
            model, materials, textures, _ = assetlib.from_source_model(
                Resolver(None, roots=[root]), 'models/props/x/crate01.mdl', 'community',
                provider={'provider': 'steam_workshop', 'workshop_item': '424242'})
        props = Library('community.props', [], textures=textures, materials=materials, models=[model])
        stack = Library('community.stack', [], [Requirement('community.props', [model.id])], prefabs=[Prefab(
            'community:prefab/crate_stack', [PrefabChild('bottom', 'prop', position=(0.0, 0.0, 0.1), model=model.id),
                                             PrefabChild('top', 'prop', position=(0.0, 0.0, 0.3), yaw_degrees=30.0,
                                                         model=model.id)])])
        libs = {'community.props': props, 'community.stack': stack}
        self.assertEqual(dep.validate_library(stack, mapping_source(libs)), [])
        m = json.loads(dep.library_bytes(stack)[32:])
        self.assertNotIn('workshop', json.dumps(m['prefabs']))       # provenance stays with the props library
        deps = dep.load_set(res.PackageDecl('w', [], [Requirement('community.stack', ['community:prefab/crate_stack'])]),
                            mapping_source(libs))
        self.assertEqual([d.decl.id for d in deps], ['community.props', 'community.stack'])


if __name__ == '__main__':
    unittest.main()
