"""X9 authored presentation data remains bounded and part of package identity."""
import copy
import math
import tempfile
import unittest
from pathlib import Path

from assetlab.assets import Material, validate as validate_assets
from assetlab.fixtures import x1_event_lab
from assetlab.package import read_manifest
from assetlab.world import Environment, Light, compile_world, validate


class VisualAuthoringTests(unittest.TestCase):
    def world(self):
        w = x1_event_lab()
        w.environment = Environment((.2, .25, .3), (.01, .02, .03), (.03, .04, .05), .07, 2)
        w.lights = [Light('door', 'point', (0, 0, 1), (1, .6, .2), 3, 4,
                          relay='x1:entity/relay_main')]
        return w

    def test_visual_fields_change_world_identity(self):
        w = self.world()
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.oalmap', Path(d) / 'b.oalmap'
            compile_world(w, a)
            manifest = read_manifest(a)
            self.assertEqual(manifest['world_entities']['schema'], 7)
            self.assertEqual(manifest['world_entities']['lights'][0]['relay'], 'x1:entity/relay_main')
            w.environment.fog_density = .09
            compile_world(w, b)
            self.assertNotEqual(a.read_bytes(), b.read_bytes())

    def test_rejects_malformed_lights_and_environment(self):
        for edit, phrase in (
                (lambda w: setattr(w.lights[0], 'intensity', math.nan), 'intensity or range'),
                (lambda w: setattr(w.lights[0], 'range', -1), 'intensity or range'),
                (lambda w: setattr(w.lights[0], 'relay', 'x1:entity/door_main'), 'not a relay'),
                (lambda w: setattr(w.lights[0], 'type', 'laser'), 'point or spot'),
                (lambda w: setattr(w.environment, 'fog_density', math.inf), 'fog density/start'),
                (lambda w: w.lights.extend([copy.copy(w.lights[0]) for _ in range(32)]), 'more than 32')):
            w = self.world()
            edit(w)
            self.assertIn(phrase, '\n'.join(validate(w)))

    def test_rejects_bad_material_response(self):
        for field, value, phrase in [('emissive', math.inf, 'emissive'),
                                     ('emissive', -1, 'emissive'),
                                     ('roughness', 2, 'roughness')]:
            m = Material('v:material/panel', 'v:texture/panel')
            setattr(m, field, value)
            self.assertIn(phrase, '\n'.join(validate_assets(materials=[m])))


if __name__ == '__main__':
    unittest.main()
