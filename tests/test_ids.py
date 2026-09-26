"""The read-only stable-ID audit (assetlab/ids.py), on synthetic packages.

Only manifests are needed: the audit never reads geometry, models or
sounds, and never writes a package."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from assetlab.ids import audit, propose_segment, text_report, valid_id
from assetlab.package import HEADER, MAGIC


def asset(path, manifest):
    """An OALASSET header and manifest (no models: the audit reads none)."""
    m = json.dumps(manifest).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack('<4sIIII', b'OALA', 1, len(m), 1, 0) + bytes(12) + m)


def world(path, manifest):
    """An OALMAP header (all counts 0) and manifest."""
    m = json.dumps(manifest).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack(HEADER, MAGIC, 1, len(m), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) + m)


def bundle(root):
    """A small bundle with one of every finding the audit makes."""
    asset(root / 'weapons/rifle.oalasset', {'kind': 'weapon', 'name': 'rifle', 'display_name': 'Rifle',
                                            'base': 'assault rifle'})
    asset(root / 'weapons/Blaster-2.oalasset', {'kind': 'weapon', 'name': 'Blaster-2', 'display_name': 'Blaster'})
    asset(root / 'characters/hero.oalasset', {'kind': 'character', 'name': 'hero', 'display_name': 'Hero',
                                              'loadout': ['Rifle', 'pistol'], 'ability_base': 'plasma rifle'})
    # Two names that only collide once normalised, and a straight duplicate.
    asset(root / 'characters/Twin.oalasset', {'kind': 'character', 'name': 'Twin'})
    asset(root / 'characters/twin.oalasset', {'kind': 'character', 'name': 'twin'})
    asset(root / 'characters/copy_a.oalasset', {'kind': 'character', 'name': 'copy'})
    asset(root / 'characters/copy_b.oalasset', {'kind': 'character', 'name': 'copy'})
    # Too long for the grammar, and a kind it does not know.
    asset(root / 'characters/long.oalasset', {'kind': 'character', 'name': 'x' * 60})
    asset(root / 'misc/odd.oalasset', {'kind': 'vehicle', 'name': 'odd'})
    # One that owns its namespace; one map whose file is not its map_id.
    asset(root / 'characters/owned.oalasset', {'kind': 'character', 'name': 'owned', 'namespace': 'lab_demo'})
    world(root / 'arena.oalmap', {'map_id': 'arena', 'display_name': 'Arena'})
    world(root / 'arena_lit.oalmap', {'map_id': 'arena', 'display_name': 'Arena (lit)'})


def by_file(result, name):
    return next(e for e in result['entries'] if Path(e['file']).name == name)


class GrammarTests(unittest.TestCase):
    def test_valid_ids(self):
        for good in ('megamod:weapon/ion_rifle', 'lab_demo:world/relay_test', 'a:sounds/b',
                     'x' * 40 + ':character/' + 'y' * 45):
            self.assertEqual(valid_id(good), (True, ''), good)

    def test_invalid_ids(self):
        for bad, why in (('Megamod:weapon/x', 'namespace'), ('m:weapon/Ion', 'name'),
                         ('m:weapon/ion-rifle', 'name'), ('m:weapon/ion.rifle', 'name'),
                         ('m:weapon/9mm', 'name'), ('m:weapon/', 'empty'), ('m:weapon', "'/'"),
                         ('weapon/x', "':'"), ('m:gadget/x', 'unknown type'), ('m:weapon/é', 'ASCII'),
                         ('m:weapon/a/b', 'name'), ('x' * 41 + ':weapon/a', 'namespace'),
                         ('m:weapon/' + 'y' * 49, 'name'), ('m' * 40 + ':character/' + 'n' * 48, 'longer')):
            ok, reason = valid_id(bad)
            self.assertFalse(ok, bad)
            self.assertIn(why, reason, bad)

    def test_proposals(self):
        self.assertEqual(propose_segment('AK-47'), 'ak_47')
        self.assertEqual(propose_segment('.357 Magnum (HL2)'), 'n357_magnum_hl2')
        self.assertEqual(propose_segment('assault rifle'), 'assault_rifle')
        self.assertEqual(propose_segment('ak47'), 'ak47')
        self.assertIsNone(propose_segment(''))
        self.assertIsNone(propose_segment(' -- '))
        self.assertIsNone(propose_segment(None))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'bundle'
        bundle(self.root)
        self.result = audit([self.root], namespace='owner')

    def tearDown(self):
        self.tmp.cleanup()

    def test_canonical_names_pass(self):
        e = by_file(self.result, 'rifle.oalasset')
        self.assertEqual(e['proposed_id'], 'owner:weapon/rifle')
        self.assertEqual([s for s in e['status'] if 'ambiguous' not in s], [])

    def test_legacy_name_needs_an_alias(self):
        e = by_file(self.result, 'Blaster-2.oalasset')
        self.assertEqual(e['proposed_id'], 'owner:weapon/blaster_2')
        self.assertTrue(any('needs an alias' in s for s in e['status']))

    def test_duplicates_and_collisions(self):
        problems = {(p['problem'], p.get('id')) for p in self.result['problems']}
        self.assertIn(('duplicate ID', 'owner:character/copy'), problems)
        self.assertIn(('normalisation collision', 'owner:character/twin'), problems)
        self.assertIn(('duplicate ID', 'owner:world/arena'), problems)

    def test_invalid_and_unknown(self):
        self.assertIsNone(by_file(self.result, 'long.oalasset')['proposed_id'])
        self.assertTrue(any('longer than' in s for s in by_file(self.result, 'long.oalasset')['status']))
        odd = by_file(self.result, 'odd.oalasset')
        self.assertIsNone(odd['proposed_id'])
        self.assertTrue(any("unknown kind 'vehicle'" in s for s in odd['status']))

    def test_map_file_name_is_the_runtime_identity(self):
        e = by_file(self.result, 'arena_lit.oalmap')
        self.assertEqual(e['runtime_key'], 'arena_lit')
        self.assertTrue(any('is not map_id' in s for s in e['status']))

    def test_ownership(self):
        owned = by_file(self.result, 'owned.oalasset')
        self.assertTrue(owned['namespace_declared'])
        self.assertEqual(owned['proposed_id'], 'lab_demo:character/owned')
        self.assertFalse(any('ambiguous' in s for s in owned['status']))
        self.assertFalse(by_file(self.result, 'hero.oalasset')['namespace_declared'])
        self.assertEqual(audit([self.root])['assumed_namespace'], 'unowned')

    def test_references(self):
        refs = {(r['field'], r['legacy']): r for r in self.result['references']}
        self.assertEqual(refs[('loadout[0]', 'Rifle')]['resolves_to'], 'owner:weapon/rifle')
        self.assertEqual(refs[('loadout[1]', 'pistol')]['resolves_to'], 'halo_trial:weapon/pistol')
        self.assertEqual(refs[('base', 'assault rifle')]['resolves_to'], 'halo_trial:weapon/assault_rifle')
        self.assertEqual(refs[('ability_base', 'plasma rifle')]['resolves_to'], 'halo_trial:weapon/plasma_rifle')

    def test_deterministic_and_path_independent(self):
        # The same packages given in another order, or found under another
        # folder, give the same IDs and findings.
        again = audit(sorted(self.root.rglob('*.oal*'), reverse=True), namespace='owner')
        strip = lambda r: [(e['proposed_id'], sorted(s for s in e['status']))
                           for e in sorted(r['entries'], key=lambda e: Path(e['file']).name)]
        self.assertEqual(strip(again), strip(self.result))
        moved = Path(self.tmp.name) / 'elsewhere' / 'deeper'
        moved.parent.mkdir()
        self.root.rename(moved)
        self.assertEqual(strip(audit([moved], namespace='owner')), strip(self.result))
        self.assertEqual(json.dumps(audit([moved], namespace='owner')['summary']),
                         json.dumps(self.result['summary']))

    def test_read_only(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        audit([self.root], namespace='owner')
        text_report(self.result)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)

    def test_unreadable_package_is_reported_not_fatal(self):
        (self.root / 'weapons/broken.oalasset').write_bytes(b'OALA\x01')
        e = by_file(audit([self.root]), 'broken.oalasset')
        self.assertIsNone(e['proposed_id'])
        self.assertTrue(any('unreadable' in s for s in e['status']))


if __name__ == '__main__':
    unittest.main()
