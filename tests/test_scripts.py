"""Host-side gameplay scripts as content (assetlab.scripts, MegaMod X3)."""
import tempfile
import unittest
from pathlib import Path

from assetlab import scripts as scriptlib, worldkey
from assetlab.fixtures import eid, x2_definition_lab, x3_script_lab
from assetlab.package import read_manifest
from assetlab.world import Entity, Link, WorldError, compile_world, validate

LUA54 = scriptlib.lua54_compiler()


def x3(name):
    return eid(name, 'x3')


def script(w, name):
    return next(s for s in w.scripts if s.id == f'x3:script/{name}')


class X3ScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.n = 0

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, world):
        self.n += 1
        out = self.dir / f'w{self.n}.oalmap'
        _, report = compile_world(world, out)
        return out, report

    def errors(self, world):
        return '\n'.join(validate(world))

    def test_fixture_is_schema_3_with_its_scripts(self):
        out, report = self.build(x3_script_lab())
        section = read_manifest(out)['world_entities']
        self.assertEqual(section['schema'], 3)
        self.assertEqual(section['ability_script'], 'x3:script/pulse_ability')
        self.assertEqual([s['id'] for s in section['scripts']], ['x3:script/button_logic', 'x3:script/pulse_ability'])
        for s in section['scripts']:
            self.assertEqual(s['api'], 'megamod.v1')
            self.assertEqual(s['source'], scriptlib.load_source(f"x3/{s['id'].partition('/')[2]}.lua"))
        button = next(e for e in section['entities'] if e['id'] == x3('button_script'))
        # Mediated by the script alone: no authored link opens door A.
        self.assertEqual(button['links'], [])
        self.assertEqual(button['script'], 'x3:script/button_logic')
        self.assertFalse(any(ln['target'] == x3('door_a') for e in section['entities'] for ln in e['links']))
        self.assertEqual(report['scripts'], ['x3:script/button_logic', 'x3:script/pulse_ability'])

    def test_deterministic_and_older_worlds_unchanged(self):
        a, _ = self.build(x3_script_lab())
        b, _ = self.build(x3_script_lab())
        self.assertEqual(a.read_bytes(), b.read_bytes())
        x2, _ = self.build(x2_definition_lab())
        self.assertEqual(read_manifest(x2)['world_entities']['schema'], 2)
        self.assertNotIn('scripts', read_manifest(x2)['world_entities'])

    def test_valid(self):
        self.assertEqual(validate(x3_script_lab()), [])

    def test_references(self):
        w = x3_script_lab()
        next(e for e in w.entities if e.id == x3('button_script')).script = 'x3:script/button_logik'
        self.assertIn('x3:entity/button_script references missing script x3:script/button_logik', self.errors(w))
        w = x3_script_lab()
        next(e for e in w.entities if e.id == x3('button_script')).script = x3('door_a')
        self.assertIn('x3:entity/button_script: script x3:entity/door_a is not a script', self.errors(w))
        w = x3_script_lab()
        next(e for e in w.entities if e.id == x3('relay_b')).script = 'x3:script/button_logic'
        self.assertIn('x3:entity/relay_b: only an interactable takes a script (it is a relay)', self.errors(w))
        w = x3_script_lab()
        w.ability_script = 'x3:script/button_logic'
        self.assertIn('ability_script: script x3:script/button_logic does not declare on_ability', self.errors(w))
        w = x3_script_lab()
        next(e for e in w.entities if e.id == x3('relay_b')).links = [Link('fired', 'x3:script/button_logic', 'open')]
        self.assertIn('x3:entity/relay_b: link target x3:script/button_logic is a script, expected a placed entity',
                      self.errors(w))

    def test_script_rules(self):
        w = x3_script_lab()
        s = script(w, 'button_logic')
        w.scripts.append(scriptlib.Script(s.id, s.source, ['on_used']))
        w.scripts.append(scriptlib.Script('x3:script/Bad', 'function on_used() end\n', ['on_used']))
        w.scripts.append(scriptlib.Script('zz:script/elsewhere', 'function on_used() end\n', ['on_used']))
        w.scripts.append(scriptlib.Script('x3:script/v2', 'function on_used() end\n', ['on_used'], api='megamod.v2'))
        w.scripts.append(scriptlib.Script('x3:script/tick', 'function on_tick() end\n', ['on_tick']))
        w.scripts.append(scriptlib.Script('x3:script/missing', 'function other() end\n', ['on_used']))
        w.scripts.append(scriptlib.Script('x3:script/accent', 'function on_used() end -- café\n', ['on_used']))
        w.scripts.append(scriptlib.Script('x3:script/bytecode', '\x1bLua\x54\x00', ['on_used']))
        w.scripts.append(scriptlib.Script('x3:script/huge', '-- ' + 'x' * 40000 + '\nfunction on_used() end\n', ['on_used']))
        e = self.errors(w)
        for want in ('x3:script/button_logic: duplicate script ID', "'x3:script/Bad': malformed script ID",
                     "zz:script/elsewhere: scripts belong to the world's namespace 'x3'",
                     "x3:script/v2: unsupported script API 'megamod.v2' (MegaMod has megamod.v1)",
                     "x3:script/tick: unknown callback 'on_tick'",
                     'x3:script/missing: declares on_used but defines no function on_used',
                     'x3:script/accent: source must be ASCII text',
                     'x3:script/bytecode: source has control characters (bytecode is never packaged)',
                     'x3:script/huge: source is'):
            self.assertIn(want, e)

    @unittest.skipUnless(LUA54, 'no Lua 5.4 compiler (luac5.4) on PATH for the parse-only preflight')
    def test_syntax_preflight(self):
        w = x3_script_lab()
        script(w, 'pulse_ability').source += 'function broken(\n'
        self.assertIn('x3:script/pulse_ability: syntax error:', self.errors(w))

    def test_never_executes_scripts(self):
        # A script that would leave a mark if anything ran it: compiling,
        # validating (parse-only preflight included) and keying must not.
        mark = self.dir / 'ran'
        w = x3_script_lab()
        s = script(w, 'button_logic')
        s.source = (f'io.open("{mark}", "w"):write("x")\nos.execute("touch {mark}")\n' + s.source)
        out, _ = self.build(w)
        worldkey.world_digest(out.read_bytes())
        self.assertFalse(mark.exists())

    def test_compile_refuses_and_writes_nothing(self):
        w = x3_script_lab()
        w.ability_script = 'x3:script/nope'
        with self.assertRaises(WorldError):
            compile_world(w, self.dir / 'bad.oalmap')
        self.assertFalse((self.dir / 'bad.oalmap').exists())

    def test_world_key_covers_script_bytes(self):
        base = worldkey.world_digest(self.build(x3_script_lab())[0].read_bytes())

        def changed(edit):
            w = x3_script_lab()
            edit(w)
            return worldkey.world_digest(self.build(w)[0].read_bytes())

        cases = {
            'one character': lambda w: setattr(script(w, 'pulse_ability'), 'source',
                                               script(w, 'pulse_ability').source.replace('150', '151')),
            'comment only': lambda w: setattr(script(w, 'pulse_ability'), 'source', script(w, 'pulse_ability').source + '-- note\n'),
            'callbacks': lambda w: (setattr(script(w, 'button_logic'), 'source', script(w, 'button_logic').source
                                            + 'function on_ability(p) end\n'),
                                    setattr(script(w, 'button_logic'), 'callbacks', ['on_used', 'on_ability'])),
            'which script a button runs': lambda w: (w.scripts.append(scriptlib.Script('x3:script/other', 'function on_used() end\n', ['on_used'])),
                                                     setattr(next(e for e in w.entities if e.id == x3('button_script')), 'script', 'x3:script/other')),
            'ability script dropped': lambda w: setattr(w, 'ability_script', None),
        }
        for name, edit in cases.items():
            with self.subTest(name):
                self.assertNotEqual(changed(edit), base, name)
        self.assertEqual(changed(lambda w: setattr(w, 'display_name', 'Renamed')), base)


if __name__ == '__main__':
    unittest.main()
