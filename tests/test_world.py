"""Original worlds and generic world entities (assetlab.world, MegaMod X1)."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab import ids
from assetlab import worldkey
from assetlab.fixtures import X2_DOOR, eid, x1_event_lab, x2_definition_lab
from assetlab.package import GROUP_NO_COLLISION, manifest_json, read_manifest
from assetlab.world import (GROUP_ENTITY, MAX_CHAIN, MAX_LINKS_PER_ENTITY, VERSION, Box, Entity, Link,
                            MoverDefinition, WorldError, compile_world, validate)


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


def x2(name):
    return eid(name, 'x2')


class X2DefinitionTests(unittest.TestCase):
    """One reusable mover definition, three placements (MegaMod X2)."""

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

    def door(self, w, name):
        return next(e for e in w.entities if e.id == x2(name))

    def test_fixture_compiles_to_schema_2(self):
        out = self.build(x2_definition_lab())
        m = read_manifest(out)
        self.assertEqual(m['package_version'], 3)               # OALMAP stays v3
        section = m['world_entities']
        self.assertEqual(section['schema'], 2)
        self.assertEqual(section['mover_definitions'], [{'id': X2_DOOR, 'size': [0.1, 1.2, 1.1],
                                                          'move': [0.0, 1.25, 0.0], 'speed': 1.0}])
        movers = [e for e in section['entities'] if e['kind'] == 'mover']
        self.assertEqual([e['id'] for e in movers], [x2('door_a'), x2('door_b'), x2('door_c')])
        for e in movers:     # a reference and a place; no parameters of its own
            self.assertEqual(set(e), {'id', 'kind', 'links', 'definition', 'position'})
            self.assertEqual(e['definition'], X2_DOOR)
        self.assertEqual([e['position'] for e in movers], [[0.0, -3.0, 0.55], [0.0, 0.0, 0.55], [0.0, 3.0, 0.55]])
        # Each placed door is drawn as its own tagged group, out of static collision.
        index = {e['id']: i for i, e in enumerate(section['entities'])}
        tagged = sorted((g[3] >> 8) & 0xFFFF for g in groups_of(out) if g[3] & GROUP_ENTITY)
        self.assertEqual(tagged, sorted(index[e['id']] + 1 for e in movers))
        self.assertTrue(all(g[3] & GROUP_NO_COLLISION for g in groups_of(out) if g[3] & GROUP_ENTITY))

    def test_x1_is_still_schema_1(self):
        section = read_manifest(self.build(x1_event_lab()))['world_entities']
        self.assertEqual(section['schema'], 1)
        self.assertNotIn('mover_definitions', section)

    def test_deterministic(self):
        a = self.build(x2_definition_lab(), 'a.oalmap').read_bytes()
        b = self.build(x2_definition_lab(), 'b.oalmap').read_bytes()
        self.assertEqual(a, b)

    def test_audit_accepts_mover_ids(self):
        self.assertEqual(ids.valid_id(X2_DOOR), (True, ''))

    def test_valid(self):
        self.assertEqual(validate(x2_definition_lab()), [])

    def test_missing_definition(self):
        w = x2_definition_lab()
        self.door(w, 'door_b').definition = 'x2:mover/basic_slide_dor'
        self.assertIn('x2:entity/door_b references missing mover definition x2:mover/basic_slide_dor', self.errors(w))

    def test_wrong_type_references(self):
        w = x2_definition_lab()
        self.door(w, 'door_a').definition = x2('relay_a')
        self.door(w, 'door_b').definition = 'x2:weapon/basic_slide_door'
        e = self.errors(w)
        self.assertIn('x2:entity/door_a: definition x2:entity/relay_a is a placed entity, expected a mover definition', e)
        self.assertIn("x2:entity/door_b: definition 'x2:weapon/basic_slide_door' is not a mover definition ID", e)
        w = x2_definition_lab()
        next(e for e in w.entities if e.id == x2('relay_a')).links = [Link('fired', X2_DOOR, 'open')]
        self.assertIn('x2:entity/relay_a: link target x2:mover/basic_slide_door is a mover definition, expected a placed entity',
                      self.errors(w))
        w = x2_definition_lab()
        next(e for e in w.entities if e.id == x2('relay_b')).definition = X2_DOOR
        self.assertIn('x2:entity/relay_b: only a mover takes a definition (it is a relay)', self.errors(w))

    def test_definition_ids(self):
        w = x2_definition_lab()
        d = w.mover_definitions[0]
        w.mover_definitions += [MoverDefinition(d.id, d.size, d.move, d.speed, d.material),
                                MoverDefinition('x2:mover/Bad-Door', d.size, d.move, d.speed, d.material),
                                MoverDefinition('x2:entity/not_a_mover', d.size, d.move, d.speed, d.material),
                                MoverDefinition('zz:mover/elsewhere', d.size, d.move, d.speed, d.material)]
        e = self.errors(w)
        self.assertIn('x2:mover/basic_slide_door: duplicate mover definition ID', e)
        self.assertIn("'x2:mover/Bad-Door': malformed mover definition ID", e)
        self.assertIn('x2:entity/not_a_mover: a mover definition ID has type mover', e)
        self.assertIn("zz:mover/elsewhere: mover definitions belong to the world's namespace 'x2'", e)

    def test_definition_parameters(self):
        w = x2_definition_lab()
        d = w.mover_definitions[0]
        d.size, d.move, d.speed, d.material = (0.1, 0.0, 1.1), (0, 0, 0), 0, 'gold'
        e = self.errors(w)
        for want in ('x2:mover/basic_slide_door: size must be finite', 'x2:mover/basic_slide_door: move must be finite',
                     'x2:mover/basic_slide_door: speed must be', "x2:mover/basic_slide_door: unknown material 'gold'"):
            self.assertIn(want, e)

    def test_placement_rules(self):
        w = x2_definition_lab()
        self.door(w, 'door_a').speed = 3.0
        self.door(w, 'door_b').position = None
        w.entities.append(Entity(x2('door_inline'), 'mover', move=(0, 1, 0), speed=1.0))
        w.boxes.append(Box((1, 1, 0), (2, 2, 1), 'door', owner=x2('door_inline')))
        e = self.errors(w)
        self.assertIn('x2:entity/door_a: a mover with a definition takes its size, move, speed and geometry from it', e)
        self.assertIn('x2:entity/door_b: a mover with a definition needs a finite position', e)
        self.assertIn('x2:entity/door_inline: in a world with mover definitions every mover names one', e)

    def test_compile_refuses_and_writes_nothing(self):
        w = x2_definition_lab()
        self.door(w, 'door_c').definition = 'x2:mover/nope'
        with self.assertRaises(WorldError):
            compile_world(w, self.dir / 'bad.oalmap')
        self.assertFalse((self.dir / 'bad.oalmap').exists())


class WorldKeyTests(unittest.TestCase):
    """MegaMod's world key (assetlab.worldkey): what it covers, what it
    leaves out. MegaMod computes the same value (scripts/test_x2.sh)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def key(self, world):
        self.n += 1
        out = self.dir / f'k{self.n}.oalmap'
        _, report = compile_world(world, out)
        d = worldkey.world_digest(out.read_bytes())
        self.assertEqual(report['world_digest'], f'{d:016x}')
        return d

    def base(self):
        return self.key(x2_definition_lab())

    def test_same_world_and_rebuild(self):
        self.assertEqual(self.base(), self.base())
        self.assertEqual(self.key(x1_event_lab()), self.key(x1_event_lab()))
        self.assertNotEqual(self.base(), self.key(x1_event_lab()))

    def changed(self, edit):
        w = x2_definition_lab()
        edit(w)
        return self.key(w)

    def test_gameplay_changes_change_it(self):
        b = self.base()

        def box(w, i):
            return w.boxes[i]

        cases = {
            'geometry': lambda w: setattr(box(w, 0), 'max', (5, 5, 0.1)),
            'collision': lambda w: setattr(box(w, 5), 'solid', False),
            'spawn': lambda w: w.spawns[0].update(position=[-3.5, -2.5, 0.0]),
            'spawn team': lambda w: w.spawns[0].update(team=1),
            'placement': lambda w: setattr(next(e for e in w.entities if e.id == x2('door_c')), 'position', (0.0, 3.0, 0.6)),
            'definition move': lambda w: setattr(w.mover_definitions[0], 'move', (0.0, 1.3, 0.0)),
            'definition speed': lambda w: setattr(w.mover_definitions[0], 'speed', 2.0),
            'definition size': lambda w: setattr(w.mover_definitions[0], 'size', (0.1, 1.2, 1.0)),
            'event link': lambda w: setattr(next(e for e in w.entities if e.id == x2('relay_a')), 'links',
                                            [Link('fired', x2('door_a'), 'toggle')]),
            'link target': lambda w: setattr(next(e for e in w.entities if e.id == x2('relay_a')), 'links',
                                             [Link('fired', x2('door_c'), 'open')]),
            'trigger volume': lambda w: setattr(next(e for e in w.entities if e.id == x2('teleport_trigger')), 'bounds',
                                                ((2.5, 3.2, -0.1), (3.6, 4.2, 1.2))),
            'teleport destination': lambda w: setattr(next(e for e in w.entities if e.id == x2('teleport_destination')),
                                                      'position', (-4.25, 4.0, 0.4)),
            'teleport facing': lambda w: setattr(next(e for e in w.entities if e.id == x2('teleport_destination')),
                                                 'yaw_degrees', 90.0),
            'button reach': lambda w: setattr(next(e for e in w.entities if e.id == x2('button_a')), 'reach', 1.5),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.assertNotEqual(self.changed(edit), b, name)

    def test_provenance_and_looks_do_not(self):
        b = self.base()
        # Presentation: the display name, a colour (texture pixels).
        self.assertEqual(self.changed(lambda w: setattr(w, 'display_name', 'Renamed Lab')), b)
        self.assertEqual(self.changed(lambda w: w.materials.update(door=(10, 200, 10))), b)
        # Provenance and reports in the manifest: rewrite the package's
        # manifest with different ones, same geometry and entities.
        out = self.dir / 'p.oalmap'
        compile_world(x2_definition_lab(), out)
        data = out.read_bytes()
        m = read_manifest(out)
        m.update(source_provenance='imported on another machine from /home/someone/else',
                 importer_version='original_world-9.9.9', source_reference='a/local/path.bsp',
                 source_sha256='0' * 64, conversion_warnings=['b', 'a'], created='2030-01-01T00:00:00Z')
        mb = manifest_json(m)
        ml = struct.unpack_from('<I', data, 8)[0]
        other = data[:8] + struct.pack('<I', len(mb)) + data[12:64] + mb + data[64 + ml:]
        self.assertNotEqual(other, data)
        self.assertEqual(worldkey.world_digest(other), b)
        # ...but a played member edited the same way does change it.
        m['spawn_points'][0]['team'] = 0
        mb = manifest_json(m)
        other = data[:8] + struct.pack('<I', len(mb)) + data[12:64] + mb + data[64 + ml:]
        self.assertNotEqual(worldkey.world_digest(other), b)

    def test_fold_and_members(self):
        self.assertEqual(worldkey.fold(0x1122334455667788), 0x11223344 ^ 0x55667788)
        self.assertEqual(worldkey.manifest_members(b'{"a":[1,{"b":"}"}],"c":null}'),
                         [('a', b'[1,{"b":"}"}]'), ('c', b'null')])


if __name__ == '__main__':
    unittest.main()
