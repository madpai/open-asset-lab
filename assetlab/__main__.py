from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from .importers.source_bsp import SourceBSP,BSPError
from .package import Resolver,compile_map
from .library import Library
from .server import serve,token_file

DEFAULT_ROOT=Path.home()/'.local/share/open-asset-lab'
DEFAULT_ENGINE=Path(__file__).resolve().parents[2]/'halo-trial-android/build-host/open-halo-map-test'
DEFAULT_ICD=Path(__file__).resolve().parents[2]/'halo-trial-android/scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json'

def main():
    p=argparse.ArgumentParser(prog='assetlab')
    p.add_argument('--library',type=Path,default=DEFAULT_ROOT)
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('inspect');a.add_argument('source');a.add_argument('--json',action='store_true')
    a=sub.add_parser('convert');a.add_argument('source');a.add_argument('--output',required=True);a.add_argument('--material-root',action='append',default=[])
    a=sub.add_parser('staged')
    a=sub.add_parser('access')
    a=sub.add_parser('serve');a.add_argument('--source-dir',action='append',default=[]);a.add_argument('--port',type=int,default=8762);a.add_argument('--tailscale',action='store_true');a.add_argument('--host-test',type=Path,default=DEFAULT_ENGINE);a.add_argument('--icd',type=Path,default=DEFAULT_ICD)
    args=p.parse_args()
    try:
        if args.command=='inspect':
            b=SourceBSP(args.source);info=b.inspect();w=b.convert();res=Resolver(b)
            for name in sorted(w.report['used_materials']):res.material(name)
            info['used_material_count']=len(w.report['used_materials']);info['missing_dependencies']=sorted(set(res.missing));info['material_warnings']=res.warnings
            if args.json:print(json.dumps(info,indent=2))
            else:
                for k,v in info.items():
                    if k=='static_props':v={'count':v['count'],'model_count':len(v['models']),'version':v.get('version')}
                    print(f'{k}: {v}')
        elif args.command=='convert':
            m,r=compile_map(args.source,args.output,args.material_root)
            print(json.dumps({'package':args.output,'manifest':m,'report':r},indent=2))
        elif args.command=='access':
            args.library.mkdir(parents=True,exist_ok=True)
            print('username: assetlab\npassword: '+token_file(args.library))
        elif args.command=='staged':
            idx=args.library/'staged/index.json'
            print(idx.read_text() if idx.exists() else '[]')
        elif args.command=='serve':
            if not 1024<=args.port<=65535:p.error('port must be 1024..65535')
            host='127.0.0.1'
            if args.tailscale:
                host=subprocess.check_output(['tailscale','ip','-4'],text=True,timeout=5).strip().splitlines()[0]
                if not host.startswith('100.'):p.error('no Tailscale IPv4 address available')
            lib=Library(args.library,args.source_dir,args.host_test,args.icd if args.icd.is_file() else None)
            serve(lib,host,args.port)
    except (BSPError,ValueError,FileNotFoundError) as e:p.exit(1,f'assetlab: {e}\n')
if __name__=='__main__':main()
