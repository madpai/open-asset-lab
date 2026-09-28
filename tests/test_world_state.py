"""X8 world-state budgeting against the engine's exported contract."""
import unittest

from assetlab import world_state


class WorldStateTests(unittest.TestCase):
    def test_channels_and_costs(self):
        kinds = ['interactable', 'relay', 'mover', 'trigger', 'teleport', 'prop', 'mover']
        state = world_state.count(kinds)
        self.assertEqual((state['runtime_objects'], state['spatial'], state['logical'], state['host_only']),
                         (7, 2, 1, 4))
        self.assertEqual([(x['channel'], x['index']) for x in state['objects']],
                         [('host-only', None), ('logical', 0), ('spatial', 0), ('host-only', None),
                          ('host-only', None), ('host-only', None), ('spatial', 1)])
        self.assertEqual(state['snapshot_bytes'], {'at_rest': 5 + 4 + 2 + 5 + 1,
                                                    'all_moving': 5 + 4 + 6 + 5 + 1,
                                                    'packet_at_rest': 5 + 4 + 2 + 5 + 1 + 20})

    def test_run_boundary_and_runtime_limit(self):
        self.assertEqual(world_state.snapshot_bytes(256, 768, 256), 882)
        self.assertEqual(world_state.snapshot_bytes(256, 0, 0), 5 + 8 + 256)
        self.assertEqual(world_state.errors(['interactable'] * 1024), [])
        self.assertIn('1024 runtime objects', world_state.errors(['interactable'] * 1025)[0])
        self.assertIn('257 movers', world_state.errors(['mover'] * 257)[0])
        with self.assertRaises(ValueError):
            world_state.snapshot_bytes(257, 0)


if __name__ == '__main__':
    unittest.main()
