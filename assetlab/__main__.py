from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from .importers.source_bsp import SourceBSP, BSPError
from .package import DEFAULT_TEXTURE_BUDGET, Resolver, compile_map, read_manifest
from .library import Library
from .report import game_dir_search, markdown, table, write
from .server import serve

DEFAULT_ROOT = Path.home()/'.local/share/open-asset-lab'
# Open Halo checkout used for staging validation. OPEN_HALO_ROOT overrides
# the sibling-checkout default; --host-test/--icd override both.
OPEN_HALO_ROOT = Path(os.environ.get('OPEN_HALO_ROOT', Path(__file__).resolve().parents[2]/'halo-trial-android'))
DEFAULT_ENGINE = OPEN_HALO_ROOT/'build-host/open-halo-map-test'
DEFAULT_ICD = OPEN_HALO_ROOT/'scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json'


def search_args(a):
    a.add_argument('--game-dir', action='append', default=[], help='mount a game directory: the folder and every *_dir.vpk in it')
    a.add_argument('--material-root', action='append', default=[], help='unpacked root containing materials/ and models/')
    a.add_argument('--vpk', action='append', default=[], help='a *_dir.vpk archive')


def search_path(args):
    roots, vpks = game_dir_search(args.game_dir)
    return [*args.material_root, *roots], [*args.vpk, *vpks]


def _addon(args):
    """An existing archive/folder, or a Workshop item fetched now."""
    from . import workshop as ws
    p = Path(args.item).expanduser()
    if p.exists():
        return p, None
    api = ws.WorkshopAPI()
    items = api.details([args.item])
    if not items or not items[0]['ok']:
        raise ws.WorkshopError(f'{args.item}: no such Workshop item (or it is private)')
    sc = ws.SteamCMD(args.steamcmd)
    if not items[0]['file_url'] and not sc.installed():
        if not args.install_steamcmd:
            raise ws.WorkshopError(f'{items[0]["id"]} needs SteamCMD; pass --install-steamcmd or --steamcmd DIR')
        sc.install()
    return ws.fetch(items[0], args.dest, sc), items[0]


def import_collection(args):
    """Every item of a collection, one after another, each into its own
    folder under --output-dir; one failure never stops the rest."""
    from . import workshop as ws
    from .workshop_jobs import SKIP_KINDS, MAX_ITEM_BYTES
    api = ws.WorkshopAPI()
    ids = api.collection(args.collection)
    if not ids:
        raise ws.WorkshopError(f'{args.collection}: not a collection, or empty or private')
    kinds = tuple(k.strip() for k in args.only.split(',') if k.strip())
    sc = ws.SteamCMD(args.steamcmd)
    summary = {'collection': ws.parse_id(args.collection), 'items': len(ids), 'built': [], 'failed': [], 'skipped': []}
    for n, it in enumerate(api.details(ids)[:args.limit], 1):
        why = ('private or removed' if not it['ok'] else 'banned' if it['banned'] else
               SKIP_KINDS.get(it['kind']) or ('too large' if it['size'] > MAX_ITEM_BYTES else None))
        print(f"[{n}/{min(len(ids), args.limit)}] {it['id']} {it['title'][:60]}" + (f' -- skipped: {why}' if why else ''),
              file=sys.stderr)
        if why:
            summary['skipped'].append({'id': it['id'], 'title': it['title'], 'reason': why})
            continue
        try:
            if not it['file_url'] and not sc.installed():
                if not args.install_steamcmd:
                    raise ws.WorkshopError('needs SteamCMD; pass --install-steamcmd or --steamcmd DIR')
                sc.install()
            path = ws.fetch(it, args.dest, sc)
            a = ws.analyze(path)
            if not a.buildable():
                raise ws.WorkshopError('nothing to build: ' + '; '.join(a.warnings[:2]))
            if args.dry_run:
                summary['built'].append({'id': it['id'], 'title': it['title'], 'would_build': {
                    'characters': [c['display'] for c in a.characters], 'weapons': [w['display_name'] for w in a.weapons],
                    'maps': a.maps}})
                continue
            out = args.output_dir / it['id']
            root = ws.extract(path, args.dest / f"{it['id']}_files")
            report = ws.import_addon(a, root, out, [*args.game_dir, *args.material_root], args.vpk, kinds)
            report['item'] = it
            (out / 'workshop_report.json').write_text(json.dumps(report, indent=2) + '\n')
            for b in report['built']:
                summary['built'].append({'id': it['id'], **{k: b.get(k) for k in ('kind', 'name', 'package')},
                                         'path': str(out / b['package']) if b.get('package') else None})
            for f in report['failed']:
                summary['failed'].append({'id': it['id'], 'name': f.get('name'), 'error': f.get('error')})
        except (ws.WorkshopError, OSError, ValueError) as e:
            summary['failed'].append({'id': it['id'], 'name': it['title'], 'error': str(e)})
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / 'collection_report.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


def workshop_command(args):
    from . import workshop as ws
    if args.ws == 'search':
        r = ws.WorkshopAPI().search(args.query, args.tag, args.page, args.sort)
        if args.json:
            print(json.dumps(r, indent=2)); return
        print(f"{r['total']} results (page {r['page']}, via {r['source']})")
        for i in r['items']:
            mb = i['size'] / 2**20
            print(f"{i['id']:>11}  {i['kind']:<9} {mb:7.1f} MB  {i['subscriptions']:>8} subs  {i['title'][:70]}")
    elif args.ws == 'info':
        items = ws.WorkshopAPI().details(args.items)
        print(json.dumps(items, indent=2) if args.json else
              '\n'.join(f"{i['id']}: {i['title']} [{i['kind']}; {', '.join(i['tags'])}] "
                        f"{'direct download' if i['file_url'] else 'SteamCMD'}" for i in items))
    elif args.ws == 'collection':
        api = ws.WorkshopAPI()
        items = api.details(api.collection(args.collection))
        if args.json:
            print(json.dumps(items, indent=2)); return
        for i in items:
            print(f"{i['id']:>11}  {i['kind']:<9} {i['size'] / 2**20:7.1f} MB  "
                  f"{i['title'][:70] if i['ok'] else '(private or removed)'}")
    elif args.ws == 'import-collection':
        import_collection(args)
    elif args.ws == 'fetch':
        path, _ = _addon(args)
        print(path)
    elif args.ws == 'analyze':
        path, item = _addon(args)
        a = ws.analyze(path)
        print(json.dumps({'source': str(path), 'item': item, 'analysis': a.to_json()}, indent=2))
    elif args.ws == 'import':
        path, item = _addon(args)
        a = ws.analyze(path)
        kinds = tuple(k.strip() for k in args.only.split(',') if k.strip())
        if args.dry_run:
            print(json.dumps({'source': str(path), 'would_build': {
                'characters': [c['display'] for c in a.characters] if 'characters' in kinds else [],
                'weapons': [w['display_name'] for w in a.weapons] if 'weapons' in kinds else [],
                'maps': a.maps if 'maps' in kinds else []}, 'warnings': a.warnings}, indent=2))
            return
        root = ws.extract(path, args.dest / f'{(item or {}).get("id") or Path(path).stem}_files')
        # The addon first, then the games' own content (their VPKs too).
        report = ws.import_addon(a, root, args.output_dir, [*args.game_dir, *args.material_root], args.vpk,
                                 kinds, pick=args.pick)
        report['item'] = item
        report['analysis'] = a.to_json()
        (args.output_dir / 'workshop_report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({k: report[k] for k in ('addon', 'built', 'failed')}, indent=2))


def main():
    p = argparse.ArgumentParser(prog='assetlab')
    p.add_argument('--library', type=Path, default=DEFAULT_ROOT)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('inspect'); a.add_argument('source'); a.add_argument('--json', action='store_true'); search_args(a)
    a = sub.add_parser('convert'); a.add_argument('source'); a.add_argument('--output', required=True); search_args(a)
    a.add_argument('--lightmaps', action='store_true', help='preserve static Source LDR lightmaps in OALMAP v2')
    a.add_argument('--texture-budget-mib', type=float, default=DEFAULT_TEXTURE_BUDGET/2**20)
    a.add_argument('--report-dir', type=Path, help='write compatibility.json/.md here')
    a.add_argument('--prop-lod', type=int, default=0,
                   help='draw props at this model LOD (0 full detail; a model without it uses its coarsest)')
    a = sub.add_parser('character', help='a Source character model into an .oalasset')
    a.add_argument('model'); a.add_argument('--output', required=True); a.add_argument('--hold', default='ak')
    a.add_argument('--name'); a.add_argument('--skin', type=int, default=0)
    a.add_argument('--display', help='its name in menus')
    a.add_argument('--loadout', nargs=2, metavar=('PRIMARY', 'SECONDARY'),
                   help='its default class: two weapon names as the game shows them')
    a.add_argument('--stats', nargs='*', default=[], metavar='KEY=VALUE',
                   help='balance and roster metadata: health shield damage speed fly fly_speed fly_damage group unique ability ability_beam'); search_args(a)
    a = sub.add_parser('weapon', help='a weapon definition (JSON) into an .oalasset')
    a.add_argument('definition'); a.add_argument('--output', required=True); search_args(a)
    a = sub.add_parser('gma', help="list or extract a Garry's Mod addon (.gma, or a Workshop *_legacy.bin)")
    a.add_argument('archive'); a.add_argument('--extract', type=Path, help='unpack under this folder (then pass it as --game-dir)')
    a = sub.add_parser('sounds', help='a sound pack definition (JSON) into an .oalasset')
    a.add_argument('definition'); a.add_argument('--output', required=True); search_args(a)
    a = sub.add_parser('ids', help='read-only audit: proposed stable IDs for existing packages')
    a.add_argument('paths', nargs='+', help='.oalmap/.oalasset files or folders (searched recursively)')
    a.add_argument('--namespace', help='owner to assume for packages that declare none')
    a.add_argument('--json', action='store_true')
    a = sub.add_parser('asset-library', help='Source static models as MegaMod asset resources in a library package (X5)')
    a.add_argument('models', nargs='+', help='Source model paths (models/props/x/crate01.mdl)')
    a.add_argument('--package', required=True, help='the library package ID (community.props)')
    a.add_argument('--namespace', required=True, help='the resource namespace (community)')
    a.add_argument('--output', required=True, help='where the .oalasset goes (packages/<package id>.oalasset)')
    a.add_argument('--provenance', nargs='*', default=[], metavar='KEY=VALUE',
                   help='kept with every resource, never played: provider, workshop_item, creator, license...')
    search_args(a)
    a = sub.add_parser('fixture', help='build an original test world (x1_event_lab ... x6_second_world) into an .oalmap')
    a.add_argument('name'); a.add_argument('--output', required=True)
    a.add_argument('--packages', help="where the library packages it requires go (default: packages/ beside --output)")
    a = sub.add_parser('project', help='build a content project (a folder with project.py: libraries() and worlds())')
    psub = a.add_subparsers(dest='project_command', required=True)
    x = psub.add_parser('build', help='write every library and world into a bundle (packages/, maps/) and report')
    x.add_argument('path'); x.add_argument('--output', required=True, help='the bundle directory'); x.add_argument('--json', action='store_true')
    x = psub.add_parser('budget', help="validate and report entity/binding budgets; write nothing")
    x.add_argument('path'); x.add_argument('--json', action='store_true')
    x = psub.add_parser('verify', help='build twice, check packages and compare every world with the native loader')
    x.add_argument('path'); x.add_argument('--output', required=True, help='a new evidence directory (must not exist)')
    x.add_argument('--engine', required=True, type=Path, help='built megamod-resources executable')
    x.add_argument('--timeout', type=float, default=30, help='seconds per native world inspection (default: 30)')
    x.add_argument('--json', action='store_true')
    a = sub.add_parser('world-key', help="MegaMod's world key of .oalmap packages (what two peers must agree on)")
    a.add_argument('packages', nargs='+')
    a.add_argument('--packages-dir', action='append', default=[],
                   help='where required library packages are (packages/<id>.oalasset); default: beside each world')
    a = sub.add_parser('resources', help="MegaMod's resource identity contract, and a checker for built packages (X4)")
    rsub = a.add_subparsers(dest='resources_command', required=True)
    x = rsub.add_parser('contract', help="the engine's contract Open Asset Lab validates against (JSON)")
    x = rsub.add_parser('check', help='check .oalmap/.oalasset packages as MegaMod loads them: declaration, dependencies, typed references')
    x.add_argument('paths', nargs='+')
    x.add_argument('--packages-dir', action='append', default=[],
                   help='where required library packages are; default: beside each package')
    x.add_argument('--json', action='store_true')
    a = sub.add_parser('report', help='compatibility report of one or more packages')
    a.add_argument('packages', nargs='+'); a.add_argument('--json', action='store_true')
    w = sub.add_parser('workshop', help="Steam Workshop: search, fetch, analyze and import (Garry's Mod by default)")
    wsub = w.add_subparsers(dest='ws', required=True)
    x = wsub.add_parser('search', help='search the Workshop')
    x.add_argument('query', nargs='?', default=''); x.add_argument('--tag', action='append', default=[],
                   help='required tag, e.g. Model, Weapon, Map, NPC, Vehicle (repeatable)')
    x.add_argument('--sort', default='relevance', help='relevance, popular, recent, subscribed, rated')
    x.add_argument('--page', type=int, default=1); x.add_argument('--json', action='store_true')
    x = wsub.add_parser('info', help='details of items (IDs or URLs)'); x.add_argument('items', nargs='+'); x.add_argument('--json', action='store_true')
    x = wsub.add_parser('collection', help='the items in a collection'); x.add_argument('collection')
    x.add_argument('--json', action='store_true')
    x = wsub.add_parser('import-collection', help='fetch and build every item of a collection')
    x.add_argument('collection')
    x.add_argument('--output-dir', type=Path, required=True, help='one folder per item under here')
    x.add_argument('--only', default='characters,weapons,maps', help='comma list: characters, weapons, maps')
    x.add_argument('--limit', type=int, default=200, help='at most this many items')
    x.add_argument('--dry-run', action='store_true', help='fetch and analyze, build nothing')
    x.add_argument('--dest', type=Path, default=DEFAULT_ROOT/'workshop/downloads', help='where downloads go')
    x.add_argument('--steamcmd', type=Path, default=Path(os.environ.get('ASSETLAB_STEAMCMD', DEFAULT_ROOT/'steamcmd')))
    x.add_argument('--install-steamcmd', action='store_true', help="fetch Valve's SteamCMD if it is missing")
    search_args(x)
    for name, hlp in (('fetch', 'download an item'), ('analyze', 'what an addon contains (item, archive or folder)'),
                      ('import', 'fetch, analyze and build packages')):
        x = wsub.add_parser(name, help=hlp)
        x.add_argument('item')
        x.add_argument('--dest', type=Path, default=DEFAULT_ROOT/'workshop/downloads', help='where downloads go')
        x.add_argument('--steamcmd', type=Path, default=Path(os.environ.get('ASSETLAB_STEAMCMD', DEFAULT_ROOT/'steamcmd')))
        x.add_argument('--install-steamcmd', action='store_true', help="fetch Valve's SteamCMD if it is missing")
        if name == 'import':
            x.add_argument('--output-dir', type=Path, required=True)
            x.add_argument('--only', default='characters,weapons,maps', help='comma list: characters, weapons, maps')
            x.add_argument('--pick', action='append', help='only candidates whose name contains this (repeatable)')
            x.add_argument('--dry-run', action='store_true', help='analyze and list, build nothing')
            search_args(x)
    sub.add_parser('staged')
    a = sub.add_parser('serve'); a.add_argument('--source-dir', action='append', default=[]); search_args(a)
    a.add_argument('--port', type=int, default=8762); a.add_argument('--tailscale', action='store_true')
    a.add_argument('--host-test', type=Path, default=DEFAULT_ENGINE); a.add_argument('--icd', type=Path, default=DEFAULT_ICD)
    a.add_argument('--steamcmd', type=Path, default=Path(os.environ.get('ASSETLAB_STEAMCMD', DEFAULT_ROOT/'steamcmd')))
    a.add_argument('--no-workshop', action='store_true', help='leave the Workshop panel and its downloads off')
    args = p.parse_args()
    try:
        if args.command == 'inspect':
            roots, vpks = search_path(args)
            b = SourceBSP(args.source); info = b.inspect(); w = b.convert(); res = Resolver(b, roots, vpks)
            for name in sorted(w.report['used_materials']):
                res.material(name)
            info['used_material_count'] = len(w.report['used_materials'])
            info['missing_dependencies'] = sorted(set(res.missing)); info['material_warnings'] = res.warnings
            info['unsupported_features'] = w.report['unsupported_features']
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                for k, v in info.items():
                    if k == 'static_props':
                        v = {'count': v['count'], 'model_count': len(v['models']), 'version': v.get('version')}
                    print(f'{k}: {v}')
        elif args.command == 'convert':
            roots, vpks = search_path(args)
            m, r = compile_map(args.source, args.output, roots, vpks=vpks, texture_budget=int(args.texture_budget_mib*2**20),
                               prop_lod=args.prop_lod, lightmaps=args.lightmaps)
            if args.report_dir:
                args.report_dir.mkdir(parents=True, exist_ok=True); write(r['compatibility'], args.report_dir)
            print(json.dumps({'package': args.output, 'manifest': m, 'report': r}, indent=2))
        elif args.command in ('character', 'weapon', 'sounds'):
            from .character import build_character, build_weapon, build_sounds
            roots, vpks = search_path(args)
            if args.command == 'character':
                m = build_character(args.model, args.output, roots, vpks, args.hold, args.name, args.skin,
                                    args.display, args.loadout, dict(kv.split('=', 1) for kv in args.stats))
            elif args.command == 'sounds':
                m = build_sounds(args.definition, args.output, roots, vpks)
            else:
                m = build_weapon(args.definition, args.output, roots, vpks)
            print(json.dumps(m, indent=2))
        elif args.command == 'asset-library':
            from .assets import AssetError, from_source_model
            from .dependencies import Library, PackageError, compile_library
            from .package import Resolver
            roots, vpks = search_path(args)
            resolver = Resolver(None, roots, vpks)
            lib, reports = Library(args.package, [], display_name=args.package), []
            provider = dict(kv.split('=', 1) for kv in args.provenance)
            try:
                for mdl in args.models:
                    model, materials, textures, report = from_source_model(resolver, mdl, args.namespace, provider=provider)
                    lib.models.append(model)
                    lib.materials += [m for m in materials if m.id not in {x.id for x in lib.materials}]
                    lib.textures += [t for t in textures if t.id not in {x.id for x in lib.textures}]
                    reports.append(report)
                _, built = compile_library(lib, args.output)
            except (AssetError, PackageError) as e:
                p.error(str(e))
            print(json.dumps({'library': built, 'models': reports, 'warnings': resolver.warnings}, indent=2))
        elif args.command == 'gma':
            from .importers.gma import GMA, load
            g = GMA(load(args.archive))
            if args.extract:
                g.extract(args.extract)
            print(json.dumps({'name': g.name, 'author': g.author, 'files': len(g.files),
                              'player_models': g.player_models(),
                              'models': sorted(n for n in g.files if n.endswith('.mdl')),
                              'extracted_to': str(args.extract) if args.extract else None}, indent=2))
        elif args.command == 'ids':
            from .ids import audit, text_report
            result = audit(args.paths, args.namespace)
            print(json.dumps(result, indent=2) if args.json else text_report(result))
        elif args.command == 'fixture':
            from .fixtures import FIXTURES
            from .world import compile_world
            if args.name not in FIXTURES:
                p.error(f"unknown fixture {args.name!r} (one of {', '.join(sorted(FIXTURES))})")
            from .fixtures import FIXTURE_LIBRARIES
            from .dependencies import compile_library, mapping_source
            libraries = FIXTURE_LIBRARIES.get(args.name, dict)()
            where = Path(args.packages) if args.packages else Path(args.output).parent / 'packages'
            built = [compile_library(lib, where / f'{pid}.oalasset', mapping_source(libraries))[1]
                     for pid, lib in sorted(libraries.items())]
            _, report = compile_world(FIXTURES[args.name](), args.output, mapping_source(libraries))
            if built:
                report['libraries'] = built
            print(json.dumps(report, indent=2))
        elif args.command == 'project':
            if args.project_command == 'verify':
                from .project_verify import verify, text
                r = verify(args.path, args.output, args.engine, args.timeout)
                print(json.dumps(r, indent=2) if args.json else text(r))
                if not r['ok']:
                    sys.exit(1)
            else:
                from .project import build, text
                r = build(args.path, args.output if args.project_command == 'build' else None)
                print(json.dumps(r, indent=2) if args.json else text(r))
        elif args.command == 'world-key':
            from .dependencies import directory_source
            from .worldkey import world_key
            print(json.dumps([world_key(x, directory_source(*args.packages_dir, Path(x).parent))
                              for x in args.packages], indent=2))
        elif args.command == 'resources':
            from . import resources as res
            from .dependencies import check_package, directory_source
            if args.resources_command == 'contract':
                print(json.dumps(res.CONTRACT, indent=2))
            else:
                reports = [check_package(x, directory_source(*args.packages_dir, Path(x).parent))
                           for x in args.paths]
                if args.json:
                    print(json.dumps(reports, indent=2))
                else:
                    for r in reports:
                        head = f"{r['file']}: {r.get('kind', '?')} " + (f"package {r['id']}" if r.get('id') else '(no declaration)')
                        print(head + (' -- OK' if not r['errors'] else ' -- REFUSED'))
                        for q in r.get('requires', []):
                            print(f"  requires {q['package']}: {', '.join(q['resources']) or '(no imports)'}")
                        for c in r.get('prefab_instances', []):
                            print(f"  prefab instance {c['instance']} ({c['prefab']} from {c['provider']}): "
                                  f"{c['path']} -> {c['entity']} ({c['kind']}, entity {c['index']})")
                        for e in r['errors']:
                            print(f'  error: {e}')
                if any(r['errors'] for r in reports):
                    sys.exit(1)
        elif args.command == 'report':
            compats = [read_manifest(x)['compatibility'] for x in args.packages]
            if args.json:
                print(json.dumps(compats, indent=2))
            else:
                print(table(compats)); print('\n'.join(markdown(c) for c in compats))
        elif args.command == 'workshop':
            workshop_command(args)
        elif args.command == 'staged':
            idx = args.library/'staged/index.json'
            print(idx.read_text() if idx.exists() else '[]')
        elif args.command == 'serve':
            if not 1024 <= args.port <= 65535:
                p.error('port must be 1024..65535')
            host = '127.0.0.1'
            if args.tailscale:
                host = subprocess.check_output(['tailscale', 'ip', '-4'], text=True, timeout=5).strip().splitlines()[0]
                if not host.startswith('100.'):
                    p.error('no Tailscale IPv4 address available')
            roots, vpks = search_path(args)
            lib = Library(args.library, args.source_dir, args.host_test, args.icd if args.icd.is_file() else None, roots, vpks)
            wsjobs = None
            if not args.no_workshop:
                from .workshop_jobs import WorkshopJobs
                wsjobs = WorkshopJobs(args.library, steamcmd_dir=args.steamcmd, game_dirs=[*args.game_dir, *args.material_root],
                                      vpks=args.vpk, asset_test=args.host_test.parent / 'open-halo-asset-test',
                                      map_test=args.host_test, icd=args.icd if args.icd.is_file() else None)
            serve(lib, host, args.port, wsjobs)
    except (BSPError, ValueError, FileNotFoundError, KeyError, OSError) as e:
        p.exit(1, f'assetlab: {e}\n')


if __name__ == '__main__':
    main()
