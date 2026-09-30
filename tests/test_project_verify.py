"""Process failures and disagreement must never become successful evidence.

The tiny response is a recorded subset of megamod-resources' output for
the original TINY fixture at engine 7b6b566 (protocol 13, with the current protocol field supplied below). The fake process
lets CI exercise failure paths without requiring an Engine checkout.
Real Night Shift/Racing integration remains the native evidence.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from assetlab import project_verify
from tests.test_project import ROOT, TINY


NATIVE_TINY = {
    'ok': True, 'world_key': '0a8229e5', 'world_digest': 'cd11db3cc793f2d9',
    'package': {'declared': False, 'id': '', 'set': []}, 'bindings': [],
    'world_state': {'ok': True, 'protocol': 14, 'runtime_objects': 1,
                    'spatial': 0, 'logical': 1, 'host_only': 0,
                    'snapshot_bytes': {'at_rest': 11, 'all_moving': 11, 'packet_at_rest': 31}},
}


class ProjectVerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'project'
        self.source.mkdir()
        (self.source / 'project.py').write_text(TINY)
        self.engine = self.root / 'engine'
        self.output = self.root / 'evidence'

    def executable(self, body):
        self.engine.write_text(f'#!{sys.executable}\n' + body)
        self.engine.chmod(0o700)

    def reply(self, native):
        self.executable('print(' + repr(json.dumps(native)) + ')\n')

    def run_verify(self, **kwargs):
        return project_verify.verify(self.source, self.output, self.engine, **kwargs)

    def test_recorded_native_agreement_and_durable_report(self):
        self.reply(NATIVE_TINY)
        r = self.run_verify()
        self.assertTrue(r['ok'], r['errors'])
        self.assertEqual(len(r['determinism']['files']), 1)
        self.assertTrue((self.output / 'bundle/maps/tiny_room.oalmap').is_file())
        self.assertEqual(json.loads((self.output / 'verification.json').read_text()), r)
        self.assertEqual(json.loads((self.output / 'native/tiny_room.stdout').read_text()), NATIVE_TINY)

    def test_world_named_build_cannot_overwrite_compiler_evidence(self):
        (self.source / 'project.py').write_text(TINY.replace("file_name='tiny_room'", "file_name='build'"))
        self.reply(NATIVE_TINY)
        self.run_verify()
        self.assertIn('worlds', json.loads((self.output / 'build.stdout').read_text()))
        self.assertEqual(json.loads((self.output / 'native/build.stdout').read_text()), NATIVE_TINY)

    def test_key_closure_and_replication_disagreements_fail(self):
        wrong = copy.deepcopy(NATIVE_TINY)
        wrong['world_key'] = '00000000'
        wrong['package']['set'] = [{'package': 'unexpected', 'digest': '00', 'direct': True}]
        wrong['world_state']['logical'] = 0
        self.reply(wrong)
        r = self.run_verify()
        self.assertFalse(r['ok'])
        for field in ('world_key', 'package.set', 'world_state.logical'):
            self.assertTrue(any(field in e for e in r['errors']), r['errors'])

    def test_native_refusal_and_non_json_output_fail(self):
        for i, body in enumerate(("print('refused'); raise SystemExit(1)\n", "print('not JSON')\n",
                                  "print('[]')\n", "print('{\"ok\": false, \"error\": \"old schema\"}')\n")):
            with self.subTest(body=body):
                self.output = self.root / f'failure-{i}'
                self.executable(body)
                r = self.run_verify()
                self.assertFalse(r['ok'])
                self.assertTrue(r['worlds'][0]['errors'])
                self.assertTrue((self.output / 'verification.json').is_file())

    def test_timeout_fails_and_preserves_output(self):
        self.executable("import time\nprint('starting', flush=True)\ntime.sleep(30)\n")
        r = self.run_verify(timeout=0.2)
        self.assertFalse(r['ok'])
        self.assertIn('timed out', r['errors'][0])
        self.assertIn('starting', (self.output / 'native/tiny_room.stdout').read_text())

    def test_repeated_build_drift_is_detected(self):
        self.reply(NATIVE_TINY)
        # A sibling's import-time value is cached by in-process repeat builds.
        # Fresh interpreters must reveal the non-reproducible source instead.
        (self.source / 'unstable.py').write_text(
            "from pathlib import Path\nmarker = Path(__file__).with_name('build-marker')\n"
            "COLOR = (91, 90, 90) if marker.exists() else (90, 90, 90)\nmarker.touch()\n")
        (self.source / 'project.py').write_text('from unstable import COLOR\n' +
                                               TINY.replace('(90, 90, 90)', 'COLOR'))
        r = self.run_verify()
        self.assertFalse(r['ok'])
        self.assertEqual(r['determinism']['different'], ['maps/tiny_room.oalmap'])

    def test_compiler_failure_is_recorded(self):
        self.reply(NATIVE_TINY)
        (self.source / 'project.py').write_text('def libraries():\n    return {}\n')
        r = self.run_verify()
        self.assertFalse(r['ok'])
        self.assertIn('build exited', r['errors'][0])
        self.assertIn('a project defines worlds()', (self.output / 'build.stderr').read_text())

    def test_all_worlds_are_inspected_even_after_one_fails(self):
        (self.source / 'project.py').write_text(TINY.replace('return [w]',
            "from dataclasses import replace\n    return [w, replace(w, id='tiny:world/second', file_name='second')]"))
        self.reply({'ok': False, 'error': 'test refusal'})
        r = self.run_verify()
        self.assertEqual(len(r['worlds']), 2)
        self.assertTrue(all(not w['ok'] for w in r['worlds']))

    def test_invalid_inputs_and_existing_run_are_preserved(self):
        with self.assertRaisesRegex(ValueError, 'not an executable'):
            self.run_verify()
        self.assertFalse(self.output.exists())
        self.reply(NATIVE_TINY)
        for timeout in (0, -1, float('nan'), float('inf')):
            with self.assertRaisesRegex(ValueError, 'positive finite'):
                self.run_verify(timeout=timeout)
        self.output.mkdir()
        sentinel = self.output / 'previous.json'
        sentinel.write_text('previous evidence')
        with self.assertRaises(FileExistsError):
            self.run_verify()
        self.assertEqual(sentinel.read_text(), 'previous evidence')

    def test_cli_failure_returns_nonzero_and_json_evidence(self):
        self.reply({'ok': False, 'error': 'schema unsupported'})
        p = subprocess.run([sys.executable, '-m', 'assetlab', 'project', 'verify', str(self.source),
                            '--engine', str(self.engine), '--output', str(self.output), '--json'],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertFalse(json.loads(p.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
