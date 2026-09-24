from __future__ import annotations
import argparse
import json
import os
import subprocess
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


def main():
    p = argparse.ArgumentParser(prog='assetlab')
    p.add_argument('--library', type=Path, default=DEFAULT_ROOT)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('inspect'); a.add_argument('source'); a.add_argument('--json', action='store_true'); search_args(a)
    a = sub.add_parser('convert'); a.add_argument('source'); a.add_argument('--output', required=True); search_args(a)
    a.add_argument('--texture-budget-mib', type=float, default=DEFAULT_TEXTURE_BUDGET/2**20)
    a.add_argument('--report-dir', type=Path, help='write compatibility.json/.md here')
    a.add_argument('--prop-lod', type=int, default=0,
                   help='draw props at this model LOD (0 full detail; a model without it uses its coarsest)')
    a = sub.add_parser('character', help='a Source character model into an .oalasset')
    a.add_argument('model'); a.add_argument('--output', required=True); a.add_argument('--hold', default='ak')
    a.add_argument('--name'); a.add_argument('--skin', type=int, default=0); search_args(a)
    a = sub.add_parser('weapon', help='a weapon definition (JSON) into an .oalasset')
    a.add_argument('definition'); a.add_argument('--output', required=True); search_args(a)
    a = sub.add_parser('sounds', help='a sound pack definition (JSON) into an .oalasset')
    a.add_argument('definition'); a.add_argument('--output', required=True); search_args(a)
    a = sub.add_parser('report', help='compatibility report of one or more packages')
    a.add_argument('packages', nargs='+'); a.add_argument('--json', action='store_true')
    sub.add_parser('staged')
    a = sub.add_parser('serve'); a.add_argument('--source-dir', action='append', default=[]); search_args(a)
    a.add_argument('--port', type=int, default=8762); a.add_argument('--tailscale', action='store_true')
    a.add_argument('--host-test', type=Path, default=DEFAULT_ENGINE); a.add_argument('--icd', type=Path, default=DEFAULT_ICD)
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
                               prop_lod=args.prop_lod)
            if args.report_dir:
                args.report_dir.mkdir(parents=True, exist_ok=True); write(r['compatibility'], args.report_dir)
            print(json.dumps({'package': args.output, 'manifest': m, 'report': r}, indent=2))
        elif args.command in ('character', 'weapon', 'sounds'):
            from .character import build_character, build_weapon, build_sounds
            roots, vpks = search_path(args)
            if args.command == 'character':
                m = build_character(args.model, args.output, roots, vpks, args.hold, args.name, args.skin)
            elif args.command == 'sounds':
                m = build_sounds(args.definition, args.output, roots, vpks)
            else:
                m = build_weapon(args.definition, args.output, roots, vpks)
            print(json.dumps(m, indent=2))
        elif args.command == 'report':
            compats = [read_manifest(x)['compatibility'] for x in args.packages]
            if args.json:
                print(json.dumps(compats, indent=2))
            else:
                print(table(compats)); print('\n'.join(markdown(c) for c in compats))
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
            serve(lib, host, args.port)
    except (BSPError, ValueError, FileNotFoundError, KeyError) as e:
        p.exit(1, f'assetlab: {e}\n')


if __name__ == '__main__':
    main()
