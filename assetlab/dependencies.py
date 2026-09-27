"""Packages and their dependencies (MegaMod X4): library packages, the
package graph, and what a world's key owes to what it requires.

A package declares itself in its manifest's "package" member
(resources.PackageDecl): its package ID, everything it provides (except
placements), and what it requires -- which packages, and which of their
resources it imports. Two kinds exist:

  world    an OALMAP (assetlab.world): provides its world, its mover
           definitions and its own scripts;
  library  an OALASSET v1 of kind "library", a manifest only: provides
           scripts other packages import. Found by package ID at
           packages/<id>.oalasset -- the file name is where to look, never
           identity: the package found must declare the ID asked for.

The graph is checked the way MegaMod loads it (src/asset/package.c): each
package once, requirements acyclic (a cycle is refused with its path), at
most `depth` requirement links deep and `packages_per_set` packages, every
import provided by the package it is taken from, the set kept in canonical
order (by package ID) however it was walked. Open Asset Lab never runs a
script to check any of this.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import resources as res, scripts as scriptlib
from .resources import PackageDecl, ResourceError

MAGIC = b'OALA'
HEADER = '<4sIIII12x'          # OALASSET v1 (assetlab.character)
LIBRARY_KIND = 'library'
IMPORTER = 'library-0.1.0'


class PackageError(ValueError):
    def __init__(self, diagnostics):
        self.diagnostics = list(diagnostics) if isinstance(diagnostics, (list, tuple)) else [diagnostics]
        super().__init__('\n'.join(self.diagnostics))


@dataclass
class Library:
    """A library package: scripts other packages import."""
    id: str                                        # package ID
    scripts: list = field(default_factory=list)    # scripts.Script
    requires: list = field(default_factory=list)   # resources.Requirement
    display_name: str = ''

    def decl(self):
        return PackageDecl(self.id, sorted(s.id for s in self.scripts), list(self.requires))


def validate_library(lib):
    """Diagnostics for a library before it is written; [] when it is good."""
    errs = []
    why = res.package_id_error(lib.id)
    if why:
        errs.append(f"package '{lib.id}': {why}")
    errs += scriptlib.validate(lib.scripts, None)
    for sc in lib.scripts:
        code, why, rid = res.parse_id(sc.id)
        if code == res.OK and res.reserved_namespace(rid.namespace):
            errs.append(f"{sc.id}: namespace '{rid.namespace}' is reserved for built-in content")
    try:
        res.parse_decl({'package': lib.decl().record()})
    except ResourceError as e:
        errs.append(str(e))
    return errs


def library_manifest(lib):
    return {'kind': LIBRARY_KIND, 'package': lib.decl().record(),
            'scripts': [scriptlib.record(s) for s in sorted(lib.scripts, key=lambda s: s.id.encode())],
            'display_name': lib.display_name or lib.id, 'importer_version': IMPORTER, 'asset_version': 1,
            'source_provenance': 'original content built by Open Asset Lab; no third-party assets'}


def compile_library(lib, output):
    """Validate and write `lib` as packages/<id>.oalasset bytes at `output`.
    Raises PackageError. Returns (manifest, report)."""
    errs = validate_library(lib)
    if errs:
        raise PackageError(errs)
    manifest = library_manifest(lib)
    mb = json.dumps(manifest, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = struct.pack(HEADER, MAGIC, 1, len(mb), 0, 0) + mb
    out.write_bytes(data)
    return manifest, {'package': lib.id, 'scripts': [s.id for s in lib.scripts],
                      'requires': [r.package for r in lib.requires], 'package_bytes': len(data),
                      'library_digest': f'{library_digest(mb):016x}'}


def oalasset_manifest(data):
    """(manifest bytes) of an OALASSET v1, or PackageError."""
    if len(data) < 32 or data[:4] != MAGIC:
        raise PackageError('not an OALASSET v1')
    _, version, ml, mc, sc = struct.unpack_from('<4sIIII', data, 0)
    if version != 1 or ml > 4 * 1024 * 1024 or ml > len(data) - 32:
        raise PackageError('not an OALASSET v1')
    return data[32:32 + ml], mc, sc


# ---- library digests: what a library adds to a world key ------------------------

_OFFSET, _PRIME, _MASK = 14695981039346656037, 1099511628211, (1 << 64) - 1


def _fnv(h, b):
    for c in b:
        h = ((h ^ c) * _PRIME) & _MASK
    return h


def library_digest(manifest: bytes) -> int:
    """FNV-1a 64 over b'OALL', u32 schema, then its played members (package,
    scripts) as key/value bytes, exactly as stored, in manifest order."""
    from .worldkey import manifest_members
    h = _fnv(_OFFSET, b'OALL' + struct.pack('<I', res.PACKAGE_SCHEMA))
    for key, value in manifest_members(manifest):
        if key in res.WORLD_KEY['library_members']:
            k = key.encode()
            h = _fnv(h, struct.pack('<I', len(k)) + k + struct.pack('<I', len(value)) + value)
    return h or 1


# ---- loading and the graph ---------------------------------------------------------

@dataclass
class LoadedLibrary:
    decl: PackageDecl
    scripts: list                  # scripts.Script
    digest: int
    where: str
    direct: bool = False


def read_library(data, where='library'):
    """A LoadedLibrary from OALASSET bytes, checked as MegaMod checks it."""
    manifest_bytes, mc, sc = oalasset_manifest(data)
    try:
        m = json.loads(manifest_bytes)
    except ValueError:
        raise PackageError('malformed manifest')
    if not isinstance(m, dict) or m.get('kind') != LIBRARY_KIND:
        raise PackageError(f"not a library package (kind '{m.get('kind', '') if isinstance(m, dict) else ''}')")
    if mc or sc or len(data) != 32 + len(manifest_bytes):
        raise PackageError('a library carries a manifest only')
    try:
        decl = res.parse_decl(m)
    except ResourceError as e:
        raise PackageError(str(e))
    if decl is None:
        raise PackageError('a library must declare its package')
    name = f'package {decl.id}'
    if 'scripts' not in m or not isinstance(m['scripts'], list):
        raise PackageError(f'{name}: a library has no scripts member')
    scripts = []
    for s in m['scripts']:
        if not isinstance(s, dict) or not all(k in s for k in ('id', 'api', 'callbacks', 'source')):
            raise PackageError(f'{name}: malformed script')
        scripts.append(scriptlib.Script(s['id'], s['source'], list(s['callbacks']), s['api']))
    errs = scriptlib.validate(scripts, None, check_syntax=False)
    if errs:
        raise PackageError([f'{name}: {e}' for e in errs])
    ids = {s.id for s in scripts}
    for p in decl.provides:
        if res.type_of(p) != 'script' or p not in ids:
            raise PackageError(f'{name} lists {p} in provides, but has no such script')
    for s in scripts:
        if s.id not in decl.provides:
            raise PackageError(f'{name} has script {s.id} but does not list it in provides')
    return LoadedLibrary(decl, scripts, library_digest(manifest_bytes), where)


def directory_source(*dirs):
    """A package source over folders holding packages/<id>.oalasset (or the
    packages folder itself): (bytes, where) or None, by package ID only."""
    def fetch(pid):
        where = f'{res.LIBRARY_DIR}/{pid}.oalasset'
        for d in dirs:
            d = Path(d)
            for p in (d / res.LIBRARY_DIR / f'{pid}.oalasset', d / f'{pid}.oalasset'):
                if p.is_file():
                    return p.read_bytes(), where
        return None
    return fetch


def mapping_source(libraries):
    """A package source over Library objects in memory (id -> Library)."""
    def fetch(pid):
        lib = libraries.get(pid)
        if lib is None:
            return None
        m = json.dumps(library_manifest(lib), sort_keys=True, separators=(',', ':')).encode()
        return struct.pack(HEADER, MAGIC, 1, len(m), 0, 0) + m, f'{res.LIBRARY_DIR}/{pid}.oalasset'
    return fetch


def _name(decl, content_id=''):
    if decl is not None:
        return f'package {decl.id}'
    return f'{content_id} (a package with no declaration)' if content_id else 'this package (it has no declaration)'


def load_set(root, fetch, content_id=''):
    """Every package `root` (a PackageDecl or None) requires, transitively,
    loaded through `fetch` (package ID -> (bytes, where) or None) and
    checked: a list of LoadedLibrary in canonical order (by package ID).
    Raises PackageError with MegaMod's message. The walk mirrors the
    engine's (src/asset/package.c) so the same package set is refused the
    same way."""
    if root is None or not root.requires:
        return []
    L = res.PACKAGE_LIMITS
    nodes = [root]                      # 0 = root, then libraries in load order
    loaded = []
    gray = {0}
    stack = [[0, 0]]
    index = {root.id: 0}

    def trail(start, last):
        return ' -> '.join(nodes[stack[i][0]].id for i in range(start, len(stack))) + f' -> {last}'

    while stack:
        node, k = stack[-1]
        d = nodes[node]
        if k >= len(d.requires):
            gray.discard(node)
            stack.pop()
            continue
        stack[-1][1] += 1
        q = d.requires[k]
        name = _name(d)
        found = index.get(q.package)
        if found is not None:
            if found in gray:
                start = next(i for i, f in enumerate(stack) if f[0] == found)
                raise PackageError(f'package cycle: {trail(start, q.package)} (package requirements must not loop)')
            continue
        if len(stack) > L['depth']:
            raise PackageError(f"package requirements deeper than {L['depth']}: {trail(0, q.package)}")
        if len(loaded) >= L['packages_per_set'] - 1:
            raise PackageError(f"{name}: more than {L['packages_per_set']} packages in one set (at {q.package})")
        where = f'{res.LIBRARY_DIR}/{q.package}.oalasset'
        got = fetch(q.package) if fetch else None
        if fetch is None:
            raise PackageError(f'{name} requires package {q.package}, but no package source was given to load it from')
        if got is None:
            raise PackageError(f'{name} requires package {q.package}, but it is not present (looked for {where})')
        data, where = got
        try:
            lib = read_library(data, where)
        except PackageError as e:
            raise PackageError(f'{name} requires package {q.package}: {where}: {e.diagnostics[0]}')
        if lib.decl.id != q.package:
            raise PackageError(f'{name} requires package {q.package}, but {where} declares package {lib.decl.id}')
        loaded.append(lib)
        nodes.append(lib.decl)
        index[lib.decl.id] = len(nodes) - 1
        gray.add(len(nodes) - 1)
        stack.append([len(nodes) - 1, 0])
    for d in nodes:
        for q in d.requires:
            p = nodes[index[q.package]]
            for rid in q.resources:
                if rid not in p.provides:
                    raise PackageError(f'{_name(d)} requires {rid} from package {q.package}, '
                                       f'but package {q.package} does not provide it')
    direct = {q.package for q in root.requires}
    for lib in loaded:
        lib.direct = lib.decl.id in direct
    return sorted(loaded, key=lambda lib: lib.decl.id.encode())


def resource_set(root, deps, providers_self=''):
    """A ResourceSet with the dependencies' resources (providers 1..) and the
    root's imports; the caller adds the root's own (provider 0)."""
    rs = res.ResourceSet([root.id if root else providers_self] + [d.decl.id for d in deps])
    pos = {d.decl.id: i + 1 for i, d in enumerate(deps)}
    if root is not None:
        for q in root.requires:
            rs.required.add(pos[q.package])
            for rid in q.resources:
                rs.imports.add((pos[q.package], rid))
    return rs


def add_dependencies(rs, deps):
    for i, d in enumerate(deps):
        for j, p in enumerate(d.decl.provides):
            rs.add(p, res.type_of(p), i + 1, j)


# ---- checking a built package -------------------------------------------------------

def _check_world(manifest, fetch, errs):
    """Resolve every reference in a built world's manifest the engine's way:
    returns (decl, deps, resolved count). Appends to errs."""
    decl = None
    try:
        decl = res.parse_decl(manifest)
    except ResourceError as e:
        errs.append(f'package: {e}')
        return None, [], 0
    deps = []
    try:
        deps = load_set(decl, fetch, manifest.get('id', ''))
    except PackageError as e:
        errs.append(f'package: {e.diagnostics[0]}')
        decl = PackageDecl(decl.id, decl.provides, []) if decl else None
    section = manifest.get('world_entities') or {}
    entities = section.get('entities') or []
    movers = section.get('mover_definitions') or []
    scripts = section.get('scripts') or []
    rs = resource_set(decl, deps)
    own = {}
    try:
        for i, e in enumerate(entities):
            if res.is_id(e.get('id'), 'entity'):
                rs.add(e['id'], 'entity', 0, i)
        for i, m in enumerate(movers):
            if res.is_id(m.get('id'), 'mover'):
                rs.add(m['id'], 'mover', 0, i)
        for i, s in enumerate(scripts):
            if res.is_id(s.get('id'), 'script'):
                rs.add(s['id'], 'script', 0, i)
                own[s['id']] = s
        if decl is not None and res.is_id(manifest.get('id'), 'world'):
            rs.add(manifest['id'], 'world', 0, 0)
        add_dependencies(rs, deps)
    except ResourceError as e:
        errs.append(str(e))
    callbacks = {k: v.get('callbacks', []) for k, v in own.items()}
    for i, d in enumerate(deps):
        for sc in d.scripts:
            if (i + 1, sc.id) in rs.imports:
                callbacks.setdefault(sc.id, sc.callbacks)
    n = 0

    def ref(field_name, who, target, cb=None):
        nonlocal n
        try:
            rs.resolve(field_name, who, target)
            n += 1
        except ResourceError as x:
            errs.append(str(x))
            return
        if cb and cb not in callbacks.get(target, []):
            errs.append(f'{who}: script {target} does not declare {cb}')

    for e in entities:
        who = e.get('id', '?')
        for ln in e.get('links') or []:
            ref(res.LINK_TARGET, who, ln.get('target', ''))
        if 'definition' in e:
            ref(res.MOVER_DEF, who, e['definition'])
        if 'script' in e:
            ref(res.SCRIPT, who, e['script'], 'on_used')
    if 'ability_script' in section:
        ref(res.ABILITY_SCRIPT, 'ability_script', section['ability_script'], 'on_ability')
    if decl is not None:
        name = f'package {decl.id}'
        wid = manifest.get('id', '')
        if not res.is_id(wid, 'world'):
            errs.append(f"{name}: the manifest's id '{wid}' is not a world ID (namespace:world/name)")
        mine = [wid] + [m.get('id') for m in movers] + list(own)
        for rid in mine:
            if rid and rid not in decl.provides:
                t = res.type_of(rid)
                errs.append(f'{name} defines {res.noun(t) if t else "resource"} {rid} but does not list it in provides')
        for rid in decl.provides:
            if rid not in mine:
                errs.append(f'{name} lists {rid} in provides, but the world defines no such {res.noun(res.type_of(rid))}')
    return decl, deps, n


def check_package(path, fetch=None):
    """A built .oalmap or library .oalasset checked as MegaMod would load it
    -- its declaration, every package it requires, every typed reference --
    without running anything. A report dict with 'errors' ([] when good)."""
    from .package import read_manifest
    from .worldkey import world_digest, fold
    path = Path(path)
    errs = []
    out = {'file': str(path)}
    if path.suffix == '.oalmap':
        manifest = read_manifest(path)
        decl, deps, n = _check_world(manifest, fetch, errs)
        out.update(kind='world', declared=decl is not None, id=decl.id if decl else None,
                   world=manifest.get('id'), provides=decl.provides if decl else [],
                   requires=[{'package': q.package, 'resources': q.resources} for q in decl.requires] if decl else [],
                   references_resolved=n)
        if not errs:
            d = world_digest(path.read_bytes(), fetch)
            out.update(world_digest=f'{d:016x}', world_key=f'{fold(d):08x}')
    else:
        try:
            lib = read_library(path.read_bytes(), str(path))
            deps = load_set(lib.decl, fetch)
            out.update(kind='library', declared=True, id=lib.decl.id, provides=lib.decl.provides,
                       requires=[{'package': q.package, 'resources': q.resources} for q in lib.decl.requires],
                       library_digest=f'{lib.digest:016x}')
        except PackageError as e:
            errs += e.diagnostics
            deps = []
    out['set'] = [{'package': d.decl.id, 'direct': d.direct, 'digest': f'{d.digest:016x}'} for d in deps]
    out['errors'] = errs
    return out
