"""Event bindings (MegaMod X7): assetlab.bindings, prefab bindings in
assetlab.prefabs (schema 2), world bindings in assetlab.world (schema 6) and
the built-package checker. The engine is the authority: the vocabulary,
schemas and limits come from its contract (data/megamod_resources.json,
"bindings"), and every refusal here uses the engine's words (MegaMod's
tests/test_bindings.c and scripts/test_x7.sh check the same packages through
the real loader)."""
import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import bindings as bl, dependencies as dep, prefabs as pf, worldkey
from assetlab.bindings import Action, Condition, EventBinding
from assetlab.dependencies import mapping_source
from assetlab.fixtures import (FIXTURE_LIBRARIES, FIXTURES, X7_DOOR, X7_FACILITY, x7_facility, x7_facility_world,
                               x7_libraries, x7_second_world, x7_security_door)
from assetlab.world import compile_world, validate

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'assetlab/data/megamod_resources.json').read_text())

# X1-X6 fixture packages, byte for byte as Open Asset Lab c420f2a wrote them.
HISTORICAL = {
    'x1_event_lab': 'b6654d0dda237ad7b07024b3ef3fb26c58c14097089ccd4d1bbca742034396fe',
    'x2_definition_lab': '676e6a14bc3d9eda01c87b8ca0553a3393bce7308a4bdc9f438c174b5a50423a',
    'x3_script_lab': 'a6ae339e84ac57a36a8a61173d6bd1a4191d0453c952492d677afd5f092d1406',
    'x4_resource_lab': '13687f4b74b268567e498eb8751e7d19d6886f939d6597108e076681db4b9afc',
    'x5_resource_world': 'ef5048b11cd464f01b6e4e2a48cbf5464a0b656295737f635d85102d9a68346b',
    'x5_second_world': 'c3aa356190bcdfd754d9a104f99811bfc7b82ae5888875ee64de826748d1efbb',
    'x6_prefab_world': '74fcead7d8d0cabd2462f670e613bcd01a227e237f09dd0942b39e3464010c34',
    'x6_second_world': '979a4302d396327f01f508e81b7c0cf68245d1657d6bacf2a88fda16d02d1bf6',
}
HISTORICAL_LIBRARIES = {
    'x4.shared': 'e41f2981e0bb997813c4ed8a33ec256cbc7b445d87fd8e14488a008c5b839274',
    'x5.shared_art': '2f82e8e46316cc558b88d346890a50b1ea2b5a2985693d332d00de27cf7c91af',
    'x6.facility': 'f8473fc26becf59bf7547488db1f1eaca80687c9c97b12964a135ef001ed57fd',
    'x6.shared_assets': '36e36d81b581d9169622026d1172010c2822b624f5abd9125d20b852e6307ffc',
}
# X7 keys: engine == Open Asset Lab (scripts/test_x7.sh).
PINNED = {'x7_facility_world': 'f8f15ddb', 'x7_second_world': '5908f3ab'}


def world_errors(w, libs=None):
    return '\n'.join(validate(w, mapping_source(libs if libs is not None else x7_libraries())))


def library_errors(lib):
    libs = x7_libraries()
    libs[lib.id] = lib
    return '\n'.join(dep.validate_library(lib, mapping_source(libs)))


class ContractTests(unittest.TestCase):
    def test_vocabulary_comes_from_the_engine(self):
        b = CONTRACT['bindings']
        self.assertEqual(bl.EVENT_NAMES, ('used', 'activated', 'entered', 'deactivated', 'opened', 'closed'))
        self.assertEqual(list(bl.CONDITIONS), ['mover_state', 'relay_state'])
        self.assertEqual(list(bl.ACTIONS), ['open', 'close', 'toggle', 'activate', 'deactivate', 'teleport', 'damage',
                                            'play_sound', 'use'])
        self.assertEqual(bl.LIMITS, b['limits'])
        self.assertEqual((bl.WORLD_SCHEMA, bl.PREFAB_SCHEMA), (6, 2))
        self.assertEqual(bl.EVENTS['activated']['link_name'], 'fired')
        self.assertEqual(bl.EVENTS['opened']['actor'], 'never')
        for f in (bl.SOURCE, bl.CONDITION_ENTITY, bl.TARGET, bl.AT, bl.SOUND, bl.PREFAB_SOUND):
            self.assertIn(f, {r['field'] for r in CONTRACT['references']})

    def test_capabilities_are_discoverable(self):
        # What a future agent may ask of a kind: the engine's table, not ours.
        self.assertTrue(bl.affords('interactable', 'use') and bl.affords('mover', 'toggle') and bl.affords('relay', 'deactivate'))
        self.assertFalse(bl.affords('prop', 'use') or bl.affords('mover', 'use') or bl.affords('relay', 'open'))
        self.assertEqual(bl.AFFORDANCES['mover']['events'], ['opened', 'closed'])
        self.assertEqual(bl.AFFORDANCES['relay']['state'], ['relay_state'])


class ModelTests(unittest.TestCase):
    def test_canonical_records(self):
        b = EventBinding('b', 'x7:entity/pad', 'entered', [Condition('relay_state', 'x7:entity/r', 'active')],
                         [Action('damage', amount=10), Action('play_sound', sound='x7:sound/locked', at='x7:entity/pad')])
        self.assertEqual(b.record(), {
            'actions': [{'action': 'damage', 'amount': 10.0},
                        {'action': 'play_sound', 'at': 'x7:entity/pad', 'sound': 'x7:sound/locked'}],
            'conditions': [{'condition': 'relay_state', 'entity': 'x7:entity/r', 'is': 'active'}],
            'event': 'entered', 'id': 'b', 'source': 'x7:entity/pad'})
        a, z = EventBinding('a', 's', 'used', [], [Action('open', target='t')]), EventBinding('z', 's', 'used', [], [Action('open', target='t')])
        self.assertEqual([r['id'] for r in bl.records([z, a])], ['a', 'z'])

    def test_parse_refusals_in_the_engines_words(self):
        def err(obj):
            try:
                bl.parse_text(obj, 'binding')
            except bl.BindingError as e:
                return str(e)
            return None
        good = {'actions': [{'action': 'open', 'target': 'd'}], 'conditions': [], 'event': 'used', 'id': 'x', 'source': 's'}
        self.assertIsNone(err(good))
        self.assertEqual(err(dict(good, event='left')),
                         "binding x: unknown event 'left' (a binding listens to used, activated, entered, deactivated, opened, closed)")
        self.assertEqual(err(dict(good, id='X')), "binding 'X': binding id has capital 'X' (IDs are lowercase; nothing is folded)")
        self.assertEqual(err(dict(good, delay=1)), "binding x: unknown field 'delay' (a binding has actions, conditions, event, id, source)")
        self.assertEqual(err({k: v for k, v in good.items() if k != 'source'}),
                         'binding x: a binding needs actions, conditions, event, id and source')
        self.assertEqual(err(dict(good, actions=[])), 'binding x: has no actions')
        self.assertEqual(err(dict(good, actions=[{'action': 'open'}])), "binding x: action open needs 'target'")
        self.assertEqual(err(dict(good, actions=[{'action': 'damage', 'amount': 5, 'target': 'd'}])),
                         "binding x: action damage does not take 'target'")
        self.assertEqual(err(dict(good, actions=[{'action': 'damage', 'amount': 501}])), 'binding x: action damage: amount must be in (0, 500]')
        self.assertEqual(err(dict(good, actions=[{'action': 'damage', 'amount': float('inf')}])), "binding x: action 0: malformed 'amount'")
        self.assertEqual(err(dict(good, actions=[{'action': 'fly'}])),
                         "binding x: unknown action 'fly' (open, close, toggle, activate, deactivate, teleport, damage, play_sound, use)")
        self.assertEqual(err(dict(good, conditions=[{'condition': 'relay_state', 'entity': 'r', 'is': 'on'}])),
                         "binding x: condition relay_state: unknown value 'on' (inactive, active)")
        self.assertEqual(err(dict(good, conditions=[{'condition': 'health', 'entity': 'r', 'is': 'on'}])),
                         "binding x: unknown condition 'health' (mover_state, relay_state)")
        self.assertEqual(err(dict(good, conditions=[{'condition': 'relay_state', 'entity': 'r', 'is': 'active'}] * 5)),
                         'binding x: more than 4 conditions')
        self.assertEqual(err(dict(good, actions=[{'action': 'open', 'target': 'd'}] * 9)), 'binding x: more than 8 actions')


class PrefabTests(unittest.TestCase):
    def test_x6_bytes_stay_schema_1_and_x7_is_schema_2(self):
        self.assertEqual(pf.member_schema([x7_security_door()]), 2)
        raw = dep.library_bytes(x7_facility())
        m = json.loads(raw[32:32 + struct.unpack_from('<I', raw, 8)[0]])
        self.assertEqual(m['prefabs']['schema'], 2)
        self.assertEqual([b['id'] for b in m['prefabs']['prefabs'][0]['bindings']],
                         ['chime', 'locked', 'power_off', 'power_on', 'powered', 'toggle_door', 'unpowered'])
        self.assertEqual(library_errors(x7_facility()), '')

    def test_prefab_refusals(self):
        def with_(**changes):
            lib = x7_facility()
            p = lib.prefabs[0]
            for i, b in enumerate(p.bindings):
                if b.id in changes:
                    p.bindings[i] = changes[b.id]
            return library_errors(lib)
        P = f'prefab {X7_DOOR}'
        self.assertIn(f"{P} binding chime references missing child 'dor'",
                      with_(chime=EventBinding('chime', 'dor', 'opened', [], [Action('play_sound', sound='x7:sound/chime')])))
        self.assertIn(f"{P} binding chime: event 'opened' is not supported by prop entity 'frame_top' (mover emits it)",
                      with_(chime=EventBinding('chime', 'frame_top', 'opened', [], [Action('play_sound', sound='x7:sound/chime')])))
        self.assertIn(f"{P} binding toggle_door: action toggle targets 'power', a relay, which does not afford toggle (toggle needs a mover)",
                      with_(toggle_door=EventBinding('toggle_door', 'button', 'used', [], [Action('toggle', target='power')])))
        self.assertIn(f"{P} binding chime: action damage acts on the event's actor, and 'opened' never carries one",
                      with_(chime=EventBinding('chime', 'door', 'opened', [], [Action('damage', amount=5)])))
        self.assertIn(f"{P} binding chime: action play_sound at 'power': a relay has no position (name one with 'at')",
                      with_(chime=EventBinding('chime', 'door', 'opened', [], [Action('play_sound', sound='x7:sound/chime', at='power')])))
        self.assertIn(f"{P} binding powered: condition mover_state reads 'power', a relay (mover_state applies to a mover)",
                      with_(powered=EventBinding('powered', 'power', 'activated', [Condition('mover_state', 'power', 'open')],
                                                 [Action('open', target='door')])))
        self.assertIn(f"{P} binding chime references missing sound x7:sound/chimes",
                      with_(chime=EventBinding('chime', 'door', 'opened', [], [Action('play_sound', sound='x7:sound/chimes')])))
        self.assertIn(f"{P} binding chime: sound x6shared:sound/door_hiss is provided by package x6.shared_assets, which package "
                      f"x7.facility requires but does not import it from", self._unimported())

    def _unimported(self):
        lib = x7_facility()
        lib.requires[0].resources.remove('x6shared:sound/door_hiss')
        lib.prefabs[0].bindings[0] = EventBinding('chime', 'door', 'opened', [], [Action('play_sound', sound='x6shared:sound/door_hiss')])
        lib.prefabs[0].children[2].sound = None
        return library_errors(lib)

    def test_unconditional_cycle_refused_conditional_allowed(self):
        lib = x7_facility()
        p = lib.prefabs[0]
        p.children.append(pf.PrefabChild('relay_b', 'relay'))
        p.bindings += [EventBinding('loop_a', 'power', 'activated', [], [Action('activate', target='relay_b')]),
                       EventBinding('loop_b', 'relay_b', 'activated', [], [Action('activate', target='power')])]
        libs = x7_libraries(); libs[X7_FACILITY] = lib
        self.assertIn('binding cycle with no condition: loop_a -> loop_b -> loop_a', world_errors(x7_facility_world(), libs))
        p.bindings[-1] = EventBinding('loop_b', 'relay_b', 'activated', [Condition('relay_state', 'power', 'inactive')],
                                      [Action('activate', target='power')])
        self.assertEqual(world_errors(x7_facility_world(), libs), '')


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixtures_compile_keys_pinned(self):
        libs = x7_libraries()
        for name, fn in (('x7_facility_world', x7_facility_world), ('x7_second_world', x7_second_world)):
            out = self.dir / f'{name}.oalmap'
            manifest, report = compile_world(fn(), out, mapping_source(libs))
            self.assertEqual(report['world_key'], PINNED[name], name)
            r = dep.check_package(out, mapping_source(libs))
            self.assertEqual(r['errors'], [], name)
        self.assertEqual(manifest['world_entities']['schema'], 5)          # the second world only places the prefab
        m, report = compile_world(x7_facility_world(), self.dir / 'f.oalmap', mapping_source(libs))
        self.assertEqual(m['world_entities']['schema'], 6)
        self.assertEqual([b['id'] for b in m['world_entities']['bindings']], ['maintenance_click', 'shock'])
        self.assertEqual(len(report['bindings']), 2 + 7 + 7)
        north = [b for b in report['bindings'] if b['instance'] == 'north_door' and b['id'] == 'toggle_door'][0]
        self.assertEqual(north['source'], 'x7:entity/north_door__button')

    def test_world_refusals(self):
        def with_(*bs, schema_world=None):
            w = x7_facility_world()
            w.bindings = list(bs)
            return world_errors(w)
        self.assertIn("binding shock: event 'opened' is not supported by trigger entity x7:entity/shock_pad (mover emits it)",
                      with_(EventBinding('shock', 'x7:entity/shock_pad', 'opened', [], [Action('play_sound', sound='x7:sound/locked')])))
        self.assertIn('binding shock references missing placed entity x7:entity/pad_dst',
                      with_(EventBinding('shock', 'x7:entity/shock_pad', 'entered', [], [Action('teleport', target='x7:entity/pad_dst')])))
        self.assertIn('binding shock: action teleport targets x7:entity/shock_pad, a trigger, which does not afford teleport (teleport '
                      'needs a teleport)',
                      with_(EventBinding('shock', 'x7:entity/shock_pad', 'entered', [], [Action('teleport', target='x7:entity/shock_pad')])))
        self.assertIn('binding click: action use targets x7:entity/north_door__door, a mover, which does not afford use (use needs an '
                      'interactable)',
                      with_(EventBinding('click', 'x7:entity/maintenance', 'used', [], [Action('use', target='x7:entity/north_door__door')])))
        self.assertIn('binding x: sound x7:prefab/security_door is a prefab, expected a sound',
                      with_(EventBinding('x', 'x7:entity/maintenance', 'used', [], [Action('play_sound', sound='x7:prefab/security_door')])))
        self.assertIn('binding a appears twice', with_(*[EventBinding('a', 'x7:entity/maintenance', 'used', [], [Action('play_sound', sound='x7:sound/locked')])] * 2))
        # a prefab child by its placed ID, and `use`: good
        self.assertEqual(with_(EventBinding('remote', 'x7:entity/maintenance', 'used', [],
                                            [Action('use', target='x7:entity/north_door__power_button')])), '')

    def test_binding_changes_change_the_key(self):
        libs = x7_libraries()
        def key(w, l=libs):
            out = self.dir / 'k.oalmap'
            return compile_world(w, out, mapping_source(l))[1]['world_key']
        k = key(x7_facility_world())
        w = x7_facility_world(); w.bindings[1].actions[0].amount = 41.0
        self.assertNotEqual(key(w), k)
        w = x7_facility_world(); w.bindings[1].actions.reverse()
        self.assertNotEqual(key(w), k)
        l2 = x7_libraries(); l2[X7_FACILITY].prefabs[0].bindings[5].actions[0].action = 'open'
        self.assertNotEqual(key(x7_facility_world(), l2), k)
        l3 = x7_libraries(); l3[X7_FACILITY].prefabs[0].provenance['creator'] = 'elsewhere'
        self.assertEqual(key(x7_facility_world(), l3), k)


class HistoricalFixtureTests(unittest.TestCase):
    """X7 must not move a byte of X1-X6: the same packages as c420f2a."""

    def test_x1_to_x6_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            libs_seen = {}
            for name, want in HISTORICAL.items():
                libs = FIXTURE_LIBRARIES.get(name, lambda: {})()
                out = d / f'{name}.oalmap'
                compile_world(FIXTURES[name](), out, mapping_source(libs))
                self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(), want, name)
                for pid, lib in libs.items():
                    libs_seen[pid] = hashlib.sha256(dep.library_bytes(lib)).hexdigest()
            self.assertEqual(libs_seen, HISTORICAL_LIBRARIES)


if __name__ == '__main__':
    unittest.main()
