"""Proposed stable content IDs for existing packages: a read-only audit (N2).

Nothing here writes a package or changes what MegaMod loads. It reads the
manifests of .oalmap and .oalasset files, proposes one canonical ID each,
and reports what would stand in the way of using those IDs: duplicates,
names that only collide after normalisation, invalid or overlong names,
packages that name no owning namespace, map files whose name differs from
their map_id, and legacy references (loadouts by display label, weapon
bases by Halo tag path) that would need aliases.

The grammar is `namespace:type/name` (docs/CONTENT_IDS.md):
  namespace  [a-z][a-z0-9_]{0,39}   the owning package lineage
  type       one of TYPES            what kind of definition it is
  name       [a-z][a-z0-9_]{0,47}   unique within namespace and type
  total      at most 96 bytes
Lowercase ASCII only, no hyphens, dots, spaces or path separators; ':' and
'/' are separators only. IDs are compared byte for byte; nothing is folded
at comparison time. A legacy name that is not already canonical gets a
*proposed* canonical form and is reported as needing an alias -- never
silently renamed.
"""
from __future__ import annotations

import json
import re
import struct
from collections import defaultdict
from pathlib import Path

from .package import read_manifest

# `entity` is a placed world entity (assetlab.world): unique within its
# world and in the world's namespace, e.g. x1:entity/door_main. It names a
# placement, not a reusable definition.
# `mover` (X2) is a reusable mover definition inside a world, e.g.
# x2:mover/basic_slide_door: any number of placed movers name it.
TYPES = ('world', 'character', 'weapon', 'sounds', 'entity', 'mover')
_SEGMENT = re.compile(r'[a-z][a-z0-9_]*\Z')
LIMITS = {'namespace': 40, 'type': 24, 'name': 48, 'total': 96}
# Built-in content the runtime provides without a package (the Halo Trial's
# own weapons); loadouts may name these by label.
BUILTIN_NAMESPACE = 'halo_trial'


def valid_id(text):
    """(True, '') or (False, reason) for a full `namespace:type/name`."""
    if not isinstance(text, str) or not text.isascii():
        return False, 'not ASCII text'
    if len(text) > LIMITS['total']:
        return False, f'longer than {LIMITS["total"]} bytes'
    ns, sep, rest = text.partition(':')
    if not sep:
        return False, "missing ':'"
    typ, sep, name = rest.partition('/')
    if not sep:
        return False, "missing '/'"
    for part, value in (('namespace', ns), ('type', typ), ('name', name)):
        if not value:
            return False, f'empty {part}'
        if len(value) > LIMITS[part]:
            return False, f'{part} longer than {LIMITS[part]}'
        if not _SEGMENT.match(value):
            return False, f'{part} {value!r} is not [a-z][a-z0-9_]*'
    if typ not in TYPES:
        return False, f'unknown type {typ!r}'
    return True, ''


def propose_segment(legacy):
    """A canonical segment for a legacy name, or None when none can be made.
    Lowercase; every run of other characters becomes one underscore; leading
    and trailing underscores go; a leading digit gets an 'n' prefix."""
    if not isinstance(legacy, str):
        return None
    s = re.sub(r'[^a-z0-9]+', '_', legacy.lower()).strip('_')
    if not s:
        return None
    if s[0].isdigit():
        s = 'n' + s
    return s


def _asset_manifest(path):
    with Path(path).open('rb') as f:
        head = f.read(32)
        if len(head) != 32:
            raise ValueError('truncated OALASSET header')
        magic, version, mlen, _mc, _sc = struct.unpack('<4sIIII', head[:20])
        if magic != b'OALA' or version != 1:
            raise ValueError('not an OALASSET v1')
        if mlen > 4 * 1024 * 1024:
            raise ValueError('manifest too large')
        m = f.read(mlen)
        if len(m) != mlen:
            raise ValueError('truncated manifest')
        return json.loads(m)


def _packages(paths):
    """Every .oalmap/.oalasset under `paths` (files or folders), sorted by
    path so the report does not depend on the order they were given in."""
    found = set()
    for p in paths:
        p = Path(p).expanduser()
        if p.is_dir():
            found.update(q for q in p.rglob('*') if q.suffix in ('.oalmap', '.oalasset') and q.is_file())
        elif p.is_file():
            found.add(p)
    return sorted(found, key=lambda q: str(q))


def audit(paths, namespace=None):
    """The audit as a plain dict (stable ordering; JSON-ready).

    `namespace` is the owner to assume for packages that declare none; the
    assumption itself is reported ("ambiguous ownership")."""
    entries, problems = [], []
    default_ns = namespace or 'unowned'
    for path in _packages(paths):
        e = {'file': str(path), 'status': []}
        m = {}
        try:
            if path.suffix == '.oalmap':
                m = read_manifest(path)
                e['type'] = 'world'
                e['legacy_name'] = m.get('map_id') or path.stem
                e['runtime_key'] = path.stem          # the runtime picks maps by file name
                e['display'] = m.get('display_name', '')
                if m.get('map_id') and m['map_id'] != path.stem:
                    e['status'].append(f"file name {path.stem!r} is not map_id {m['map_id']!r}: "
                                       'the runtime uses the file name')
            else:
                m = _asset_manifest(path)
                kind = m.get('kind', '')
                e['type'] = kind if kind in TYPES else None
                e['legacy_name'] = m.get('name', '')
                e['runtime_key'] = m.get('name', '')
                e['display'] = m.get('display_name', '')
                if e['type'] is None:
                    e['status'].append(f'unknown kind {kind!r}')
                if m.get('loadout'):
                    e['loadout'] = list(m['loadout'])
                if m.get('base'):
                    e['base'] = m['base']
                if m.get('ability_base'):
                    e['ability_base'] = m['ability_base']
                if m.get('name') and path.stem != m['name']:
                    e['status'].append(f"file name {path.stem!r} is not name {m['name']!r}")
        except (OSError, ValueError, json.JSONDecodeError) as err:
            e['status'].append(f'unreadable: {err}')
            e['type'] = None
            e['legacy_name'] = None
        ns = m.get('namespace') if isinstance(m, dict) else None
        e['namespace_declared'] = bool(ns)
        ns = ns or default_ns
        if not e['namespace_declared']:
            e['status'].append(f'no namespace declared; assumed {ns!r} (ambiguous ownership)')
        seg = propose_segment(e.get('legacy_name'))
        if e.get('type') and seg:
            pid = f"{ns}:{e['type']}/{seg}"
            ok, why = valid_id(pid)
            e['proposed_id'] = pid if ok else None
            if not ok:
                e['status'].append(f'no valid ID: {why}')
            elif seg != e['legacy_name']:
                e['status'].append(f"legacy name {e['legacy_name']!r} needs an alias to {pid}")
        else:
            e['proposed_id'] = None
            if e.get('type'):
                e['status'].append('no valid ID: empty name')
        declared = m.get('id') if isinstance(m, dict) else None
        if declared is not None:            # an original world says its own ID
            ok, why = valid_id(declared)
            if ok and declared.partition(':')[0] == m.get('namespace') and \
                    declared.partition(':')[2].partition('/')[0] == e.get('type'):
                e['proposed_id'] = declared
                e['status'] = [s for s in e['status'] if 'needs an alias' not in s]
            else:
                e['status'].append(f'declared id {declared!r} is invalid: {why or "wrong namespace or type"}')
        entries.append(e)

    # Duplicates and normalisation collisions.
    by_id = defaultdict(list)
    for e in entries:
        if e['proposed_id']:
            by_id[e['proposed_id']].append(e)
    for pid, group in sorted(by_id.items()):
        if len(group) < 2:
            continue
        names = sorted({str(g['legacy_name']) for g in group})
        kind = 'duplicate ID' if len(names) == 1 else 'normalisation collision'
        problems.append({'problem': kind, 'id': pid, 'legacy_names': names,
                         'files': [g['file'] for g in group]})
        for g in group:
            g['status'].append(f'{kind} with {len(group) - 1} other package(s)')

    # Legacy references: loadouts name weapons by display label; weapon and
    # ability bases name Halo weapons by tag path fragment.
    weapon_labels = defaultdict(list)
    for e in entries:
        if e.get('type') == 'weapon':
            weapon_labels[e['display']].append(e)
    for label, group in sorted(weapon_labels.items()):
        if len(group) > 1:
            problems.append({'problem': 'duplicate weapon label', 'label': label,
                             'files': [g['file'] for g in group]})
    references = []
    for e in entries:
        for slot, label in enumerate(e.get('loadout', [])):
            target = weapon_labels.get(label)
            if target and len(target) == 1:
                references.append({'from': e['proposed_id'] or e['file'], 'field': f'loadout[{slot}]',
                                   'legacy': label, 'resolves_to': target[0]['proposed_id'],
                                   'kind': 'package weapon by label'})
            else:
                builtin = propose_segment(label)
                references.append({'from': e['proposed_id'] or e['file'], 'field': f'loadout[{slot}]',
                                   'legacy': label,
                                   'resolves_to': f'{BUILTIN_NAMESPACE}:weapon/{builtin}' if builtin else None,
                                   'kind': 'built-in weapon by label (not in these packages)'})
        for field in ('base', 'ability_base'):
            if e.get(field):
                builtin = propose_segment(e[field])
                references.append({'from': e['proposed_id'] or e['file'], 'field': field,
                                   'legacy': e[field],
                                   'resolves_to': f'{BUILTIN_NAMESPACE}:weapon/{builtin}' if builtin else None,
                                   'kind': 'Halo tag path fragment (substring match today)'})

    counts = defaultdict(int)
    for e in entries:
        counts['packages'] += 1
        counts['ok' if e['proposed_id'] and len(e['status']) == (0 if e['namespace_declared'] else 1)
               else 'needs_attention'] += 1
    return {'grammar': 'namespace:type/name', 'assumed_namespace': default_ns,
            'entries': entries, 'problems': problems, 'references': references,
            'summary': dict(sorted(counts.items()))}


def text_report(result):
    """The audit as readable lines."""
    out = [f"Proposed stable IDs (read-only; grammar {result['grammar']}, "
           f"assumed namespace {result['assumed_namespace']!r})", '']
    for e in result['entries']:
        mark = 'OK ' if not [s for s in e['status'] if 'ambiguous ownership' not in s] else '!! '
        out.append(f"{mark}{e['proposed_id'] or '(none)':<44} {e['type'] or '?':<9} {Path(e['file']).name}")
        for s in e['status']:
            if 'ambiguous ownership' not in s:
                out.append(f'     - {s}')
    unowned = sum(1 for e in result['entries'] if not e['namespace_declared'])
    if unowned:
        out += ['', f"{unowned} package(s) declare no namespace: all assumed {result['assumed_namespace']!r}."]
    if result['problems']:
        out += ['', 'Problems:']
        for p in result['problems']:
            out.append('  - ' + ', '.join(f'{k}: {v}' for k, v in p.items()))
    kinds = defaultdict(int)
    for r in result['references']:
        kinds[r['kind']] += 1
    if kinds:
        out += ['', 'Legacy references that would need aliases:']
        for k, n in sorted(kinds.items()):
            out.append(f'  {n:3} {k}')
        unresolved = [r for r in result['references'] if not r['resolves_to']]
        for r in unresolved:
            out.append(f"  unresolved: {r['from']} {r['field']} = {r['legacy']!r}")
    s = result['summary']
    out += ['', f"{s.get('packages', 0)} packages: {s.get('ok', 0)} ready, "
                f"{s.get('needs_attention', 0)} need attention (beyond the namespace)."]
    return '\n'.join(out)
