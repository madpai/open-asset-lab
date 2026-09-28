"""Content projects: a folder of Python that declares libraries and worlds,
built in one step.

    assetlab project build DIR --output BUNDLE
    assetlab project budget DIR

DIR holds `project.py`, which defines

    libraries()  -> {package ID: assetlab.dependencies.Library}
    worlds()     -> [assetlab.world.OriginalWorld]

and may import sibling modules (DIR goes first on sys.path while it loads).
`build` writes BUNDLE/packages/<id>.oalasset and BUNDLE/maps/<file>.oalmap
-- the layout MegaMod's --bundle reads -- through the same compilers as
`assetlab fixture`, and reports every package and each world's ENTITY
BUDGET: hand-placed and expanded entities by kind and by prefab, against the
runtime, spatial and logical limits from MegaMod's X8 contract.
`budget` validates and reports without writing anything.

Nothing here is a new format: a project is code over the same authoring
model (docs/ORIGINAL_WORLDS.md), so its packages are exactly what that
model compiles.
"""
from __future__ import annotations

import collections
import importlib.util
import sys
import tempfile
from pathlib import Path

from .dependencies import compile_library, mapping_source
from .world import KINDS, MAX_ENTITIES, compile_world
from .world_state import LIMITS

LIMIT_BINDINGS = LIMITS['bindings']


def load(path):
    """Import DIR/project.py (or the file given) as a fresh module."""
    p = Path(path)
    f = p / 'project.py' if p.is_dir() else p
    if not f.is_file():
        raise FileNotFoundError(f'{f}: no project.py')
    here = str(f.parent.resolve())
    sys.path.insert(0, here)
    try:
        spec = importlib.util.spec_from_file_location(f'assetlab_project_{abs(hash(here))}', f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(here)
    for name in ('libraries', 'worlds'):
        if not callable(getattr(mod, name, None)):
            raise ValueError(f'{f}: a project defines {name}()')
    return mod


def budget(world, report):
    """The world's entity budget from its compile report."""
    placed = collections.Counter(e.kind for e in world.entities)
    expanded = report.get('expanded', [])
    inst_of = {i.id: i.prefab for i in world.prefab_instances}
    by_prefab = collections.defaultdict(lambda: {'instances': 0, 'entities': 0, 'kinds': collections.Counter()})
    seen = set()
    for c in expanded:
        inst = c['entity'].partition('/')[2].split('__')[0]
        p = by_prefab[inst_of.get(inst, '?')]
        if inst not in seen:
            seen.add(inst)
            p['instances'] += 1
        p['entities'] += 1
        p['kinds'][c['kind']] += 1
    kinds = collections.Counter(placed)
    for c in expanded:
        kinds[c['kind']] += 1
    total = len(world.entities) + len(expanded)
    own = len(world.bindings)
    state = report['world_state']
    return {
        'limit': MAX_ENTITIES, 'total': total, 'headroom': MAX_ENTITIES - total,
        'world_state': {k: v for k, v in state.items() if k != 'objects'},
        'hand_placed': {'total': len(world.entities), 'kinds': {k: placed[k] for k in KINDS if placed[k]}},
        'prefab_instances': len(world.prefab_instances),
        'expanded': {'total': len(expanded),
                     'by_prefab': {pid: {'instances': v['instances'], 'entities': v['entities'],
                                         'per_instance': v['entities'] // max(1, v['instances']),
                                         'kinds': dict(sorted(v['kinds'].items()))}
                                   for pid, v in sorted(by_prefab.items(), key=lambda kv: -kv[1]['entities'])}},
        'kinds': {k: kinds[k] for k in KINDS if kinds[k]},
        'bindings': {'limit': LIMIT_BINDINGS, 'total': len(report.get('bindings', [])), 'world': own,
                     'from_prefabs': len(report.get('bindings', [])) - own},
    }


def build(path, output=None):
    """Compile every library and world. `output` None: validate only."""
    mod = load(path)
    libraries = mod.libraries()
    worlds = mod.worlds()
    fetch = mapping_source(libraries)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(output) if output else Path(tmp)
        libs = [compile_library(lib, root / 'packages' / f'{pid}.oalasset', fetch)[1]
                for pid, lib in sorted(libraries.items())]
        out = []
        for w in worlds:
            (root / 'maps').mkdir(parents=True, exist_ok=True)
            _, report = compile_world(w, root / 'maps' / f'{w.file_name}.oalmap', fetch)
            out.append({'world': w.id, 'file': f'maps/{w.file_name}.oalmap', 'package': w.package,
                        'world_key': report['world_key'], 'package_bytes': report['package_bytes'],
                        'package_sha256': report['package_sha256'], 'triangles': report['triangles'],
                        'scripts': report['scripts'], 'budget': budget(w, report)})
    for lib in libs:
        if 'assets' in lib:
            lib['asset_counts'] = {k: len(v) for k, v in lib['assets'].items()}
    return {'project': getattr(mod, 'NAME', str(path)), 'output': str(output) if output else None,
            'libraries': libs, 'worlds': out}


def text(report):
    """A short human summary."""
    lines = [f"{report['project']}" + (f" -> {report['output']}" if report['output'] else ' (validated, nothing written)')]
    for lib in report['libraries']:
        extra = ', '.join(f'{n} {k}' for k, n in lib.get('asset_counts', {}).items() if n)
        if lib.get('prefabs'):
            extra = (extra + ', ' if extra else '') + f"{len(lib['prefabs'])} prefabs"
        lines.append(f"  library {lib['package']}: {lib['package_bytes']} bytes, digest {lib['library_digest']}"
                     + (f' ({extra})' if extra else '') + (f"; requires {', '.join(lib['requires'])}" if lib['requires'] else ''))
    for w in report['worlds']:
        b = w['budget']
        lines.append(f"  world {w['world']} ({w['file']}): key {w['world_key']}, {w['package_bytes']} bytes, {w['triangles']} triangles")
        lines.append(f"    entities {b['total']}/{b['limit']} (headroom {b['headroom']}): {b['hand_placed']['total']} hand-placed "
                     f"+ {b['expanded']['total']} from {b['prefab_instances']} prefab instances")
        lines.append('    by kind: ' + ', '.join(f'{k} {n}' for k, n in b['kinds'].items()))
        s = b['world_state']
        lines.append(f"    replication: {s['spatial']} spatial, {s['logical']} logical, {s['host_only']} host-only; "
                     f"WORLD_STATE {s['snapshot_bytes']['at_rest']} bytes at rest, "
                     f"{s['snapshot_bytes']['all_moving']} bytes all moving (payload)")
        for pid, p in b['expanded']['by_prefab'].items():
            lines.append(f"    {pid}: {p['instances']} x {p['per_instance']} = {p['entities']}")
        lines.append(f"    bindings {b['bindings']['total']}/{b['bindings']['limit']} "
                     f"({b['bindings']['world']} the world's, {b['bindings']['from_prefabs']} from prefabs)")
    return '\n'.join(lines)
