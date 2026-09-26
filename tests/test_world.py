"""Original worlds and generic world entities (assetlab.world, MegaMod X1)."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import ids
from assetlab.fixtures import eid, x1_event_lab
from assetlab.package import GROUP_NO_COLLISION, read_manifest
from assetlab.world import (GROUP_ENTITY, MAX_CHAIN, MAX_LINKS_PER_ENTITY, VERSION, Box, Entity, Link,
                            WorldError, compile_world, validate)


def groups_of(package):
    data = Path(package).read_bytes()
    _, version, mlen, vc, ic, gc = struct.unpack_from('<4sIIIII', data, 0)
    at = 64 + mlen + vc * 40 + ic * 4
    size = 20 if version >= 2 else 16
    return [struct.unpack_from('<5I' if size == 20 else '<4I', data, at + i * size) for i in range(gc)]


def entity(world, name):
    return next(e for e in world.entities if e.id == eid(name))


class X1FixtureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, world, name='w.oalmap'):
        out = self.dir / name
        compile_world(world, out)
        return out

    def errors(self, world):
        return '\n'.join(validate(world))

    def test_fixture_compiles_to_v3_with_its_entities(self):
        out = self.build(x1_event_lab())
        m = read_manifest(out)
        self.assertEqual(m['package_version'], VERSION)
        self.assertEqual(m['id'], 'x1:world/event_lab')
        self.assertEqual(m['namespace'], 'x1')
        ents = m['world_entities']['entities']
        self.assertEqual([e['kind'] for e in ents], ['interactable', 'relay', 'mover', 'trigger', 'teleport'])
        self.assertEqual(ents[0]['links'], [{'event': 'used', 'input': 'activate', 'target': eid('relay_main')}])
        self.assertEqual(ents[1]['links'], [{'event': 'fired', 'input': 'open', 'target': eid('door_main')}])
        self.assertEqual(ents[3]['links'], [{'event': 'entered', 'input': 'teleport',
                                              'target': eid('teleport_destination')}])
        door = ents[2]
        self.assertEqual(door['bounds'], {'min': [-0.05, -0.6, 0.0], 'max': [0.05, 0.6, 1.1]})
        self.assertEqual(door['move'], [0.0, 1.25, 0.0])
        # The door's triangles: its own group, tagged with its index + 1,
        # and not in the static collision (it owns its own).
        tagged = [g for g in groups_of(out) if g[3] & GROUP_ENTITY]
        self.assertEqual(len(tagged), 1)
        self.assertEqual((tagged[0][3] >> 8) & 0xFFFF, 3)
        self.assertTrue(tagged[0][3] & GROUP_NO_COLLISION)
        self.assertEqual(tagged[0][1], 36)                  # one box: 12 triangles
        self.assertEqual(tagged[0][4], 0xFFFFFFFF)          # no lightmap
        # Non-solid floor marks stay out of collision too.
        self.assertEqual(sum(1 for g in groups_of(out) if g[3] & GROUP_NO_COLLISION), 3)

    def test_deterministic(self):
        a = self.build(x1_event_lab(), 'a.oalmap').read_bytes()
        b = self.build(x1_event_lab(), 'b.oalmap').read_bytes()
        self.assertEqual(a, b)

    def test_reordered_placements_keep_their_links(self):
        w = x1_event_lab()
        w.entities.reverse()
        m = read_manifest(self.build(w))
        ents = {e['id']: e for e in m['world_entities']['entities']}
        self.assertEqual(ents[eid('button_main')]['links'][0]['target'], eid('relay_main'))
        self.assertEqual(ents[eid('relay_main')]['links'][0]['target'], eid('door_main'))
        # The door's group now carries its new index (1: second of five).
        tagged = {(g[3] >> 8) & 0xFFFF for g in groups_of(self.dir / 'w.oalmap') if g[3] & GROUP_ENTITY}
        self.assertEqual(tagged, {[e['id'] for e in m['world_entities']['entities']].index(eid('door_main')) + 1})

    def test_audit_takes_the_declared_ids(self):
        out = self.build(x1_event_lab(), 'x1_event_lab.oalmap')
        r = ids.audit([out])
        self.assertEqual(r['entries'][0]['proposed_id'], 'x1:world/event_lab')
        self.assertEqual(r['entries'][0]['status'], [])
        self.assertEqual(ids.valid_id(eid('door_main')), (True, ''))

    def test_duplicate_id(self):
        w = x1_event_lab()
        w.entities.append(Entity(eid('relay_main'), 'relay'))
        self.assertIn('x1:entity/relay_main: duplicate placed ID', self.errors(w))

    def test_malformed_ids(self):
        w = x1_event_lab()
        w.entities += [Entity('x1:entity/Bad-Name', 'relay'), Entity('x1:weapon/relay_b', 'relay'),
                       Entity('other:entity/relay_c', 'relay'), Entity('relay_d', 'relay')]
        e = self.errors(w)
        self.assertIn("'x1:entity/Bad-Name': malformed placed ID", e)
        self.assertIn('x1:weapon/relay_b: a placed ID has type entity', e)
        self.assertIn("other:entity/relay_c: placed IDs belong to the world's namespace 'x1'", e)
        self.assertIn("'relay_d': malformed placed ID: missing ':'", e)

    def test_missing_target(self):
        w = x1_event_lab()
        w.entities = [e for e in w.entities if e.id != eid('relay_main')]
        self.assertIn('x1:entity/button_main references missing target x1:entity/relay_main', self.errors(w))

    def test_target_must_accept_the_input(self):
        w = x1_event_lab()
        entity(w, 'button_main').links = [Link('used', eid('door_main'), 'activate')]
        self.assertIn('link used -> x1:entity/door_main.activate: a mover does not accept', self.errors(w))
        entity(w, 'button_main').links = [Link('used', eid('teleport_trigger'), 'open')]
        self.assertIn('a trigger does not accept', self.errors(w))

    def test_unknown_event_input_and_kind(self):
        w = x1_event_lab()
        entity(w, 'button_main').links = [Link('pressed', eid('relay_main'), 'activate')]
        entity(w, 'relay_main').links = [Link('fired', eid('door_main'), 'explode')]
        w.entities.append(Entity(eid('thing'), 'func_door'))
        e = self.errors(w)
        self.assertIn("an interactable does not emit 'pressed'", e)
        self.assertIn("unknown input 'explode'", e)
        self.assertIn("x1:entity/thing: unknown kind 'func_door'", e)

    def test_mover_parameters(self):
        w = x1_event_lab()
        entity(w, 'door_main').move = (0, 0, 0)
        entity(w, 'door_main').speed = -1
        e = self.errors(w)
        self.assertIn('x1:entity/door_main: mover needs a finite move', e)
        self.assertIn('x1:entity/door_main: mover speed must be', e)
        w = x1_event_lab()
        entity(w, 'door_main').move = (float('nan'), 0, 1)
        self.assertIn('mover needs a finite move', self.errors(w))
        w = x1_event_lab()
        w.boxes = [b for b in w.boxes if b.owner is None]
        self.assertIn('x1:entity/door_main: mover has no geometry', self.errors(w))

    def test_trigger_volume(self):
        w = x1_event_lab()
        entity(w, 'teleport_trigger').bounds = ((1, 1, 1), (1, 2, 2))
        self.assertIn('x1:entity/teleport_trigger: trigger bounds are empty', self.errors(w))
        entity(w, 'teleport_trigger').bounds = ((1, 1, 1), (2, float('inf'), 2))
        self.assertIn('x1:entity/teleport_trigger: trigger needs finite bounds', self.errors(w))

    def test_teleport_destination(self):
        w = x1_event_lab()
        entity(w, 'teleport_destination').position = None
        self.assertIn('x1:entity/teleport_destination: teleport needs a finite position', self.errors(w))
        w = x1_event_lab()
        entity(w, 'teleport_destination').position = (3.0, 0.0, 0.5)     # on the pad
        self.assertIn('destination is inside trigger x1:entity/teleport_trigger', self.errors(w))

    def test_geometry_owner(self):
        w = x1_event_lab()
        w.boxes.append(Box((1, 1, 0), (2, 2, 1), 'wall', owner=eid('ghost')))
        w.boxes.append(Box((1, 1, 0), (2, 2, 1), 'wall', owner=eid('relay_main')))
        e = self.errors(w)
        self.assertIn('geometry owned by missing entity x1:entity/ghost', e)
        self.assertIn('x1:entity/relay_main: only a mover owns geometry', e)

    def test_cycles(self):
        w = x1_event_lab()
        w.entities += [Entity(eid('relay_a'), 'relay', links=[Link('fired', eid('relay_b'), 'activate')]),
                       Entity(eid('relay_b'), 'relay', links=[Link('fired', eid('relay_a'), 'activate')])]
        self.assertIn('link cycle: x1:entity/relay_a -> x1:entity/relay_b -> x1:entity/relay_a', self.errors(w))
        w = x1_event_lab()
        entity(w, 'relay_main').links.append(Link('fired', eid('relay_main'), 'activate'))
        self.assertIn('an entity cannot target itself', self.errors(w))

    def test_fanout_chain_and_work_bounds(self):
        w = x1_event_lab()
        entity(w, 'relay_main').links = [Link('fired', eid('door_main'), 'open')] * (MAX_LINKS_PER_ENTITY + 1)
        self.assertIn(f'x1:entity/relay_main: {MAX_LINKS_PER_ENTITY + 1} links; at most', self.errors(w))
        # A chain longer than the runtime follows.
        w = x1_event_lab()
        n = MAX_CHAIN + 1
        for i in range(n):
            nxt = eid(f'r{i + 1}') if i + 1 < n else eid('door_main')
            w.entities.append(Entity(eid(f'r{i}'), 'relay', links=[Link('fired', nxt, 'activate' if i + 1 < n else 'open')]))
        entity(w, 'button_main').links = [Link('used', eid('r0'), 'activate')]
        self.assertIn(f'x1:entity/button_main: a chain of {n + 1} links starts here; at most {MAX_CHAIN}', self.errors(w))
        # Diamonds: few links, exponential work.
        w = x1_event_lab()
        layers = 5
        for L in range(layers):
            for k in range(4):
                tg = [eid(f'd{L + 1}_{j}') for j in range(4)] if L + 1 < layers else [eid('door_main')]
                w.entities.append(Entity(eid(f'd{L}_{k}'), 'relay',
                                         links=[Link('fired', t, 'activate' if L + 1 < layers else 'open') for t in tg]))
        entity(w, 'button_main').links = [Link('used', eid(f'd0_{k}'), 'activate') for k in range(4)]
        self.assertIn('x1:entity/button_main: one event here can cause', self.errors(w))

    def test_compile_refuses_and_writes_nothing(self):
        w = x1_event_lab()
        w.entities = [e for e in w.entities if e.id != eid('relay_main')]
        with self.assertRaises(WorldError) as cm:
            compile_world(w, self.dir / 'bad.oalmap')
        self.assertIn('references missing target', str(cm.exception))
        self.assertFalse((self.dir / 'bad.oalmap').exists())

    def test_diagnostics_do_not_depend_on_the_fixture_object(self):
        w = x1_event_lab()
        self.assertEqual(validate(copy.deepcopy(w)), [])


if __name__ == '__main__':
    unittest.main()
