"""Workshop search, fetch, analysis and import -- offline. Steam is a fake
that answers the way the real endpoints were seen to answer (2026-09);
addons are synthetic GMAs with no Workshop content in them."""
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path

from assetlab import workshop as ws
from assetlab.workshop_jobs import WorkshopJobs


def gma(files, name='test addon'):
    out = bytearray(b'GMAD\x03') + struct.pack('<QQ', 76561198000000000, 0) + b'\0'
    out += name.encode() + b'\0' + b'desc\0' + b'author\0' + struct.pack('<i', 1)
    for i, (n, d) in enumerate(files, 1):
        out += struct.pack('<I', i) + n.encode() + b'\0' + struct.pack('<qI', len(d), 0)
    out += struct.pack('<I', 0)
    for _, d in files:
        out += d
    return bytes(out)


def details_json(*items):
    return json.dumps({'response': {'result': 1, 'resultcount': len(items), 'publishedfiledetails': [
        {'publishedfileid': str(i), 'result': 1, 'title': f'Item {i} ', 'file_size': '1048576', 'file_url': url,
         'filename': 'x.gma' if url else '', 'preview_url': f'https://images.steamusercontent.com/ugc/{i}/',
         'consumer_app_id': 4000, 'lifetime_subscriptions': 10 * i, 'tags': [{'tag': 'Addon'}, {'tag': tag}],
         'description': '[b]Bold[/b] words &amp; more'}
        for i, tag, url in items]}}).encode()


# The 2026 browse page: React, with results as escaped JSON in window.SSR.
SSR_PAGE = ('<html><script>window.SSR={};window.SSR.loaderData = ["{\\"x\\":{\\"childpublishedfileid\\":\\"\\"},'
            '\\"data\\":{\\"eresult\\":1,\\"current_page\\":1,\\"total_pages\\":2,\\"total_count\\":42,\\"results\\":['
            '{\\"publishedfileid\\":\\"222\\",\\"title\\":\\"B\\"},{\\"publishedfileid\\":\\"111\\",\\"title\\":\\"A\\"},'
            '{\\"publishedfileid\\":\\"222\\"}]}}"]</script>'
            '<a href="https://steamcommunity.com/sharedfiles/filedetails/?id=999">featured</a></html>')


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _answer(self, url, arg):
        self.calls.append((url, arg))
        for key, val in self.routes.items():
            if key in url:
                return val(arg) if callable(val) else val
        raise OSError(f'no route for {url}')

    def get(self, url, params=None):
        return self._answer(url, params)

    def post(self, url, data):
        return self._answer(url, data)

    def download(self, url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self._answer(url, None))
        return dest


class SearchTests(unittest.TestCase):
    def test_ids_and_kinds(self):
        self.assertEqual(ws.parse_id('2855665131'), '2855665131')
        self.assertEqual(ws.parse_id('https://steamcommunity.com/sharedfiles/filedetails/?id=2855665131&searchtext='), '2855665131')
        self.assertEqual(ws.parse_id('steam://url/CommunityFilePage/2855665131'), '2855665131')
        with self.assertRaises(ws.WorkshopError):
            ws.parse_id('superman')
        self.assertEqual(ws.kind_from_tags(['Addon', 'Model']), 'character')
        self.assertEqual(ws.kind_from_tags(['Addon', 'NPC']), 'character')
        self.assertEqual(ws.kind_from_tags(['Addon', 'Weapon', 'Fun']), 'weapon')
        self.assertEqual(ws.kind_from_tags(['Map', 'Model']), 'map')
        self.assertEqual(ws.kind_from_tags(['Save']), 'other')

    def test_browse_page_parsing(self):
        self.assertEqual(ws.browse_ids(SSR_PAGE), ['222', '111'])     # rank order, once each, no featured
        self.assertEqual(ws.browse_total(SSR_PAGE), 42)
        old = ('<div class="workshopItem"><a href="https://steamcommunity.com/sharedfiles/filedetails/?id=5">x</a>'
               '</div> </div><p>Showing 1-30 of 1,234 entries</p>')
        self.assertEqual(ws.browse_ids(old), ['5'])
        self.assertEqual(ws.browse_total(old), 1234)

    def test_search_without_a_key(self):
        http = FakeHttp({'workshop/browse': SSR_PAGE.encode(),
                         'GetPublishedFileDetails': lambda d: details_json((222, 'Model', ''), (111, 'Weapon', 'https://x/y'))})
        api = ws.WorkshopAPI(http, api_key='')
        r = api.search('super', ['Model'], sort='popular')
        self.assertEqual(r['source'], 'browse')
        self.assertEqual([i['id'] for i in r['items']], ['222', '111'])
        self.assertEqual(r['total'], 42)
        self.assertEqual(r['items'][0]['kind'], 'character')
        self.assertEqual(r['items'][0]['title'], 'Item 222')                 # trimmed
        self.assertEqual(r['items'][0]['description'], 'Bold words & more')  # BBCode and entities gone
        browse = http.calls[0][1]
        self.assertEqual(browse['requiredtags[]'], ['Model'])
        self.assertEqual(browse['actualsort'], 'trend')
        # Cached: the same search does not go back to Steam.
        n = len(http.calls)
        api.search('super', ['Model'], sort='popular')
        self.assertEqual(len(http.calls), n)
        with self.assertRaises(ws.WorkshopError):
            api.search('x', sort='sideways')

    def test_search_with_a_key(self):
        doc = json.loads(details_json((7, 'Map', '')))
        doc['response']['total'] = 99
        http = FakeHttp({'QueryFiles': json.dumps(doc).encode()})
        r = ws.WorkshopAPI(http, api_key='K').search('gm_', ['Map'])
        self.assertEqual((r['source'], r['total'], r['items'][0]['kind']), ('api', 99, 'map'))
        p = http.calls[0][1]
        self.assertEqual((p['key'], p['requiredtags[0]'], p['query_type']), ('K', 'Map', 12))

    def test_details_batches_and_collections(self):
        http = FakeHttp({'GetPublishedFileDetails': lambda d: details_json(
            *[(int(d[f'publishedfileids[{i}]']), 'Model', '') for i in range(d['itemcount'])]),
            'GetCollectionDetails': json.dumps({'response': {'collectiondetails': [
                {'children': [{'publishedfileid': '1'}, {'publishedfileid': '2'}]}]}}).encode()})
        api = ws.WorkshopAPI(http, api_key='')
        items = api.details([str(i) for i in range(1, 251)])
        self.assertEqual(len(items), 250)
        self.assertEqual(sum('GetPublishedFileDetails' in c[0] for c in http.calls), 3)   # 100 per call
        self.assertEqual(api.collection('https://steamcommunity.com/sharedfiles/filedetails/?id=9'), ['1', '2'])


class LuaTests(unittest.TestCase):
    def test_swep_fields(self):
        src = '''
        --[[ a block
        SWEP.Primary.Damage = 999 ]]
        SWEP.PrintName = "AK-47"   -- the name
        SWEP.Base = "bobs_gun_base"
        SWEP.HoldType = 'ar2'
        SWEP.ViewModelFlip = true
        SWEP.ViewModel = "models/weapons/v_rif_ak47.mdl"
        SWEP.Primary.Damage = 36
        SWEP.Primary.RPM = 60 / 0.1
        SWEP.Primary.Sound = Sound("Weapon_AK47.Single");
        SWEP.Secondary = { ClipSize = -1, Automatic = false }
        '''
        d = ws.parse_swep(src)
        self.assertEqual(d['PrintName'], 'AK-47')
        self.assertEqual(d['Primary.Damage'], 36.0)
        self.assertAlmostEqual(d['Primary.RPM'], 600.0)
        self.assertEqual(d['Primary.Sound'], 'Weapon_AK47.Single')
        self.assertIs(d['ViewModelFlip'], True)
        self.assertEqual(d['Secondary.ClipSize'], -1.0)
        # Arithmetic only: nothing else is evaluated.
        self.assertIsNone(ws._lua_value('os.exit()'))
        self.assertIsNone(ws._lua_value('__import__("os")'))

    def test_sound_scripts(self):
        files = {'lua/autorun/snd.lua': b'sound.Add({ name = "Weapon_X.Fire", channel = CHAN_WEAPON, sound = {")weapons/x/fire1.wav", "weapons/x/fire2.wav"} })',
                 'scripts/sounds/game_sounds_x.txt': b'"Weapon_Y.Single"\n{\n "channel" "CHAN_WEAPON"\n "wave" "^weapons/y/shot.wav"\n}'}
        s = ws.parse_sound_scripts(files)
        self.assertEqual(s['weapon_x.fire'], ')weapons/x/fire1.wav')
        self.assertEqual(ws._sound_path('Weapon_X.Fire', s), 'sound/weapons/x/fire1.wav')
        self.assertEqual(ws._sound_path('Weapon_Y.Single', s), 'sound/weapons/y/shot.wav')
        self.assertIsNone(ws._sound_path('Weapon_Unknown', s))

    def test_draft_bases(self):
        def draft(**kw):
            return ws.draft_weapon('cls', {'ViewModel': 'v.mdl', **kw}, {}, 'test')
        ak = draft(HoldType='ar2', **{'Primary.Damage': 22.0, 'Primary.Delay': 0.1, 'Primary.ClipSize': 30.0,
                                      'Primary.DefaultClip': 120.0, 'ViewModelFlip': True})
        self.assertEqual((ak['base'], ak['stats']['damage_scale'], ak['stats']['rounds_per_second']), ('assault rifle', 1.0, 10.0))
        self.assertEqual((ak['stats']['magazine'], ak['stats']['reserve']), (30, 120))
        self.assertTrue(ak['view_model_mirrored'] and ak['auto_drafted'])
        self.assertEqual(draft(HoldType='shotgun', **{'Primary.NumShots': 8.0, 'Primary.ClipSize': 6.0})['base'], 'shotgun')
        self.assertEqual(draft(HoldType='rpg', **{'Primary.ClipSize': 1.0})['base'], 'rocket launcher')
        self.assertEqual(draft(HoldType='revolver', **{'Primary.ClipSize': 6.0})['base'], 'pistol')
        self.assertEqual(draft(HoldType='ar2', **{'Primary.Damage': 95.0, 'Primary.RPM': 40.0, 'Primary.ClipSize': 5.0})['base'], 'sniper rifle')
        knife = draft(HoldType='knife', **{'Primary.ClipSize': -1.0, 'Primary.Damage': 60.0})
        self.assertTrue(knife['melee'] and knife['base'] == 'pistol' and knife['crosshair'] == 'dot')
        self.assertNotIn('magazine', knife['stats'])
        # Absurd numbers are clamped, not trusted.
        self.assertEqual(draft(**{'Primary.Damage': 1e6, 'Primary.RPM': 1e6})['stats']['damage_scale'], 6.0)


def addon():
    swep = b'''SWEP.PrintName = "Cool Rifle"
SWEP.HoldType = "ar2"
SWEP.Spawnable = true
SWEP.ViewModel = "models/weapons/v_cool.mdl"
SWEP.WorldModel = "models/weapons/w_cool.mdl"
SWEP.Primary.Damage = 30
SWEP.Primary.ClipSize = 25
SWEP.Primary.RPM = 700
SWEP.Primary.Sound = Sound("Cool.Fire")'''
    return gma([
        ('lua/autorun/hero.lua', b'player_manager.AddValidModel( "Super Hero", "models/player/hero/hero.mdl" )\n'
                                 b'player_manager.AddValidHands( "Super Hero", "models/player/hero/hero_arms.mdl", 0, "0000000" )\n'
                                 b'list.Set( "PlayerOptionsModel", "Super Hero", "models/player/hero/hero.mdl" )'),
        ('lua/autorun/hero_npc.lua', b'local Category = "Heroes"\nlocal NPC = { Name = "Hero NPC", Class = "npc_citizen",\n'
                                     b'  Model = "models/player/hero/hero_npc.mdl", KeyValues = { citizentype = 4 } }\n'
                                     b'list.Set( "NPC", "npc_hero", NPC )'),
        ('lua/autorun/sounds.lua', b'sound.Add({ name = "Cool.Fire", sound = "weapons/cool/fire.wav" })'),
        ('lua/weapons/cool_rifle/shared.lua', swep),
        ('lua/weapons/cool_base/shared.lua', b'SWEP.ViewModel = "x.mdl"\nSWEP.Spawnable = false'),
        ('lua/weapons/cool_nade.lua', b'SWEP.HoldType = "grenade"\nSWEP.Spawnable = true\nSWEP.ViewModel = "models/weapons/v_nade.mdl"'),
        ('models/player/hero/hero.mdl', b'IDST'), ('models/player/hero/hero_npc.mdl', b'IDST'),
        ('models/player/hero/hero_arms.mdl', b'IDST'), ('models/player/extra/sidekick.mdl', b'IDST'),
        ('models/weapons/v_cool.mdl', b'IDST'), ('models/props_junk/crate.mdl', b'IDST'),
        ('maps/gm_test.bsp', b'VBSP'), ('materials/hero/body.vmt', b'x'), ('sound/weapons/cool/fire.wav', b'RIFF'),
    ], name='Hero Pack')


class AnalysisTests(unittest.TestCase):
    def test_everything_an_addon_holds(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'hero.gma'
            p.write_bytes(addon())
            a = ws.analyze(p)
            self.assertEqual(a.name, 'Hero Pack')
            chars = {c['display']: c for c in a.characters}
            # Registered, with its hands; the NPC copy is not another
            # character; an unregistered playermodel folder still counts.
            self.assertEqual(chars['Super Hero']['hands'], 'models/player/hero/hero_arms.mdl')
            self.assertIn('Sidekick', chars)
            self.assertEqual(len(a.characters), 2)
            self.assertEqual(a.npcs, [{'class': 'npc_hero', 'display': 'Hero NPC', 'model': 'models/player/hero/hero_npc.mdl'}])
            # The rifle drafted (with its scripted sound), the base and the
            # grenade not.
            self.assertEqual([w['name'] for w in a.weapons], ['cool_rifle'])
            w = a.weapons[0]
            self.assertEqual((w['display_name'], w['base'], w['sounds']['fire']),
                             ('Cool Rifle', 'assault rifle', 'sound/weapons/cool/fire.wav'))
            self.assertEqual(w['needs'], ['models/weapons/w_cool.mdl'])      # its world model is elsewhere
            self.assertTrue(any('cool_nade' in x for x in a.warnings))
            self.assertEqual(a.maps, ['maps/gm_test.bsp'])
            self.assertEqual((a.props, a.lua), (1, 6))
            # Same answers from the unpacked folder.
            root = ws.extract(p, Path(t) / 'files')
            b = ws.analyze(root)
            self.assertEqual([c['model'] for c in b.characters], [c['model'] for c in a.characters])

    def test_nothing_buildable_says_so(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'x.gma'
            p.write_bytes(gma([('materials/a.vmt', b'x')]))
            a = ws.analyze(p)
            self.assertEqual(a.buildable(), 0)
            self.assertTrue(a.warnings)


class FetchTests(unittest.TestCase):
    def test_steamcmd_output(self):
        ok = ws.parse_steamcmd('Loading...\nSuccess. Downloaded item 42 to "/s/steamapps/workshop/content/4000/42" (1234 bytes)')
        self.assertEqual(ok, (True, '/s/steamapps/workshop/content/4000/42', ''))
        bad = ws.parse_steamcmd('ERROR! Download item 42 failed (Access Denied).')
        self.assertFalse(bad[0])
        self.assertIn('private', bad[2])
        libs = ws.parse_steamcmd('steamcmd.sh: line 37: /x/linux32/steamcmd: cannot execute: required file not found')
        self.assertIn('lib32gcc-s1', libs[2])

    def test_steamcmd_download(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / 'steamcmd'
            (root).mkdir()
            (root / 'steamcmd.sh').write_text('#!/bin/sh\n')
            got = root / 'steamapps/workshop/content/4000/77'
            calls = []

            class R:
                def __init__(self, out):
                    self.stdout, self.stderr = out, ''

            def runner(cmd, **kw):
                calls.append(cmd)
                got.mkdir(parents=True, exist_ok=True)
                (got / 'a.gma').write_bytes(b'GMAD')
                return R(f'Success. Downloaded item 77 to "{got}" (4 bytes)')
            sc = ws.SteamCMD(root, runner=runner)
            item = {'id': '77', 'file_url': '', 'app': 4000}
            p = ws.fetch(item, Path(t) / 'dl', sc)
            self.assertTrue((p / 'a.gma').is_file())
            self.assertIn('+workshop_download_item', calls[0])
            self.assertEqual(calls[0][calls[0].index('+workshop_download_item') + 1:][:2], ['4000', '77'])
            self.assertIn('anonymous', calls[0])
            with self.assertRaises(ws.WorkshopError):
                ws.fetch(item, Path(t) / 'dl', None)
            with self.assertRaises(ws.WorkshopError):
                ws.SteamCMD(Path(t) / 'missing').download('1')

    def test_direct_download_for_legacy_items(self):
        with tempfile.TemporaryDirectory() as t:
            http = FakeHttp({'cdn.example/file': b'LEGACY'})
            item = {'id': '5', 'file_url': 'https://cdn.example/file', 'filename': '../../evil/x_legacy.bin'}
            p = ws.fetch(item, Path(t), None, http)
            self.assertEqual(p, Path(t) / '5' / 'x_legacy.bin')              # no path escape
            self.assertEqual(p.read_bytes(), b'LEGACY')


class ImportTests(unittest.TestCase):
    def test_builds_what_it_can_and_records_the_rest(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'hero.gma').write_bytes(addon())
            a = ws.analyze(t / 'hero.gma')
            root = ws.extract(t / 'hero.gma', t / 'files')
            calls = []

            def character(model, out, roots, vpks, **kw):
                calls.append(('character', model, kw))
                if 'sidekick' in model:
                    raise ValueError(f'{model}: no animation for idle, run_front')
                Path(out).write_bytes(b'OALA')
                return {'missing_dependencies': ['materials/x.vtf']}

            def weapon(spec, out, roots, vpks):
                calls.append(('weapon', spec['name'], roots))
                Path(out).write_bytes(b'OALA')
                return {'missing_dependencies': []}

            def compile_map(src, out, roots, vpks=()):
                calls.append(('map', src))
                Path(out).write_bytes(b'OALM')
                return {'missing_dependencies': []}, {}

            b = {'character': character, 'weapon': weapon, 'map': compile_map}
            r = ws.import_addon(a, root, t / 'out', builders=b)
            self.assertEqual(sorted(x['name'] for x in r['built']), ['Cool Rifle', 'Super Hero', 'gm_test'])
            self.assertEqual(len(r['failed']), 1)
            self.assertIn('--game-dir', r['failed'][0]['error'])            # the hint
            # The addon is mounted first on every search path.
            self.assertEqual(Path(calls[[c[0] for c in calls].index('weapon')][2][0]), root)
            self.assertTrue((t / 'out' / 'cool_rifle.json').is_file())      # the draft, for review
            self.assertEqual(calls[0][2]['display'], 'SUPER HERO')
            # --pick narrows it; kinds too.
            r = ws.import_addon(a, root, t / 'out2', builders=b, kinds=('characters',), pick=['super'])
            self.assertEqual([x['name'] for x in r['built']], ['Super Hero'])


class JobTests(unittest.TestCase):
    def test_a_job_runs_stages_and_serves_only_its_files(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'hero.gma').write_bytes(addon())
            api = ws.WorkshopAPI(FakeHttp({'GetPublishedFileDetails': lambda d: details_json((321, 'Model', ''))}), api_key='')

            def importer(a, root, out, game_dirs, vpks, kinds):
                (Path(out) / 'super_hero.oalasset').write_bytes(b'OALA')
                return {'addon': a.name, 'built': [{'kind': 'character', 'name': 'Super Hero', 'package': 'super_hero.oalasset'}],
                        'failed': []}
            j = WorkshopJobs(t / 'lib', api=api, fetcher=lambda item: t / 'hero.gma', importer=importer, start=False)
            with self.assertRaises(ValueError):
                j.submit('321', kinds=['sounds'])
            jid = j.submit('https://steamcommunity.com/sharedfiles/filedetails/?id=321')
            self.assertEqual(j.jobs()[0]['state'], 'QUEUED')
            j.run(jid)
            job = j.job(jid)
            self.assertEqual(job['state'], 'STAGED')
            self.assertEqual(job['title'], 'Item 321')
            self.assertIn('1 characters', job['log'].replace('2 characters', '1 characters'))
            self.assertTrue(j.artifact(jid, 'super_hero.oalasset'))
            self.assertTrue(j.artifact(jid, 'report.json'))
            self.assertIsNone(j.artifact(jid, '../jobs.sqlite3'))
            self.assertIsNone(j.artifact(jid, 'x.sh'))
            self.assertIsNone(j.artifact('nothex', 'report.json'))
            # A job interrupted mid-run requeues on restart.
            jid2 = j.submit('321')
            with j.connect() as db:
                db.execute("UPDATE workshop_jobs SET state='CONVERTING' WHERE id=?", (jid2,))
            j2 = WorkshopJobs(t / 'lib', api=api, start=False)
            self.assertEqual(j2.job(jid2)['state'], 'QUEUED')

    def test_nothing_to_build_fails_the_job(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / 'x.gma').write_bytes(gma([('materials/a.vmt', b'x')]))
            api = ws.WorkshopAPI(FakeHttp({'GetPublishedFileDetails': lambda d: details_json((5, 'Model', ''))}), api_key='')
            j = WorkshopJobs(t / 'lib', api=api, fetcher=lambda item: t / 'x.gma', start=True)
            jid = j.submit('5')
            for _ in range(100):
                if j.job(jid)['state'] in ('STAGED', 'FAILED'):
                    break
                time.sleep(0.05)
            j.close()
            self.assertEqual(j.job(jid)['state'], 'FAILED')
            self.assertIn('nothing', j.job(jid)['error'])


if __name__ == '__main__':
    unittest.main()


class ModernModelTests(unittest.TestCase):
    def test_vtx_strip_group_stride(self):
        from assetlab.importers.source_mdl import vtx_strip_group_stride
        from assetlab.importers.source_bsp import BSPError

        def vtx(stride, groups=2):
            # Mesh header at 0: groups follow at 8; each group points at its
            # own 3 vertices and 3 indices placed after all headers.
            head = 8 + groups * stride
            buf = bytearray(head + groups * (27 + 6) + 16)
            struct.pack_into('<ii', buf, 0, groups, 8)
            for g in range(groups):
                sg = 8 + g * stride
                data = head + g * 33
                struct.pack_into('<iiii', buf, sg, 3, data - sg, 3, data + 27 - sg)
            return bytes(buf)
        self.assertEqual(vtx_strip_group_stride(vtx(33), 0, 2, 8, 49), 33)
        self.assertEqual(vtx_strip_group_stride(vtx(25), 0, 2, 8, 48), 25)
        # The version is a first guess, not the answer: the file decides.
        self.assertEqual(vtx_strip_group_stride(vtx(33), 0, 2, 8, 48), 33)
        self.assertEqual(vtx_strip_group_stride(vtx(25), 0, 2, 8, 49), 25)
        with self.assertRaises(BSPError):
            vtx_strip_group_stride(b'\0' * 16, 0, 2, 8, 49)

    def test_outline_shells_are_recognised(self):
        from assetlab import translate
        black = (2, 2, bytes([3, 3, 3, 255] * 4))
        blue = (2, 2, bytes([20, 40, 200, 255] * 4))
        self.assertTrue(translate.material_outline('models/x/outline', {}, black))
        self.assertTrue(translate.material_outline('models/x/eyes', {'$basetexture': 'models/x/fp_outlinematerial'}, black))
        self.assertFalse(translate.material_outline('models/x/outline_suit', {}, blue))     # a named, coloured costume
        self.assertFalse(translate.material_outline('models/x/boots', {}, black))           # black, but not an outline
