"""Resource identity (MegaMod X4): the same grammar, registry and typed
resolution MegaMod Engine loads with, for Open Asset Lab's validators.

Two identities, never confused:

  resource ID   namespace:type/name    x4:script/open_door    a named item
  package ID    segment(.segment)*     x4.resource_lab        what is shipped,
                                                              required, loaded

Where the rules come from. MegaMod is the authority: its registry of
resource types, reference fields, limits and world-key members is printed by
`megamod-resources --json`, and a copy lives in
`data/megamod_resources.json`. Everything table-like here -- which types
exist, which are reserved or importable, every limit -- is READ from that
file, not written again by hand. The grammar has to be code on both sides;
`data/megamod_id_conformance.json` (`megamod-resources --conformance`) is
the engine's own verdict, reason text included, on a corpus of IDs, and
tests/test_resources.py checks this module gives exactly the same for each.
MegaMod's scripts/test_x4.sh checks both copies against the live engine.

Grammar: every segment [a-z][a-z0-9_]*, lowercase ASCII only, compared byte
for byte, never folded or normalised: any other spelling is refused, not
rewritten. The messages below are the engine's, word for word.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).parent / 'data'
CONTRACT = json.loads((DATA / 'megamod_resources.json').read_text())
GRAMMAR = CONTRACT['id_grammar']
LIMITS = GRAMMAR['limits']                       # namespace, type, name, total
RESERVED_NAMESPACES = tuple(GRAMMAR['reserved_namespaces'])
PACKAGE_ID = CONTRACT['package_id_grammar']
PACKAGE = CONTRACT['package']
PACKAGE_LIMITS = PACKAGE['limits']
PACKAGE_SCHEMA = PACKAGE['schema']
LIBRARY_DIR = PACKAGE['library']['location'].partition('/')[0]      # "packages"
TYPES = {t['name']: t for t in CONTRACT['types']}
REFERENCES = {r['field']: r for r in CONTRACT['references']}
SUPPORTED = tuple(n for n, t in TYPES.items() if t['status'] == 'supported')
RESERVED = tuple(n for n, t in TYPES.items() if t['status'] == 'reserved')
IMPORTABLE = tuple(n for n, t in TYPES.items() if t['importable'])
WORLD_KEY = CONTRACT['world_key']

# The engine's result codes (resource.h).
OK, MALFORMED, UNKNOWN_TYPE, RESERVED_TYPE = 'ok', 'malformed', 'unknown_type', 'reserved_type'

# Reference fields, by the engine's names (resource.h hta_ref_field).
LINK_TARGET = 'world_entities.entities[].links[].target'
MOVER_DEF = 'world_entities.entities[].definition'
SCRIPT = 'world_entities.entities[].script'
ABILITY_SCRIPT = 'world_entities.ability_script'
LUA_ENTITY = 'world.entity(id)'
REQUIRE = 'package.requires[].resources[]'


class ResourceError(ValueError):
    pass


def _bytes(text):
    if isinstance(text, bytes):
        return text
    if not isinstance(text, str):
        return b''
    # Every byte as the engine would see it: UTF-8 for real text; a str
    # holding latin-1 code points (as JSON escapes of raw bytes) round-trips.
    try:
        return text.encode('latin-1')
    except UnicodeEncodeError:
        return text.encode('utf-8')


def _shown(c):
    if 0x21 <= c < 0x7F:
        return f"'{chr(c)}'"
    if c == 0x20:
        return 'a space'
    return f'\\x{c:02x}'


def _segment(what, s, mx):
    """None, or why `s` (bytes) is not one [a-z][a-z0-9_]* segment."""
    if not s:
        return f'empty {what}'
    if len(s) > mx:
        return f'{what} longer than {mx} bytes'
    for i, c in enumerate(s):
        if 0x61 <= c <= 0x7A or (i and (0x30 <= c <= 0x39 or c == 0x5F)):
            continue
        if 0x41 <= c <= 0x5A:
            return f'{what} has capital {_shown(c)} (IDs are lowercase; nothing is folded)'
        if not i:
            return f'{what} starts with {_shown(c)}, not a lowercase letter'
        if c in (0x3A, 0x2F):
            return f"{what} has {_shown(c)} (':' and '/' each separate once)"
        return f'{what} has {_shown(c)}, not [a-z0-9_]'
    return None


@dataclass(frozen=True)
class ResourceId:
    text: str
    namespace: str
    type: str
    name: str


def parse_id(text):
    """(code, why, ResourceId or None) -- the engine's hta_rid_parse. The
    ResourceId is filled whenever the shape was readable (also for an
    unknown or reserved type)."""
    b = _bytes(text)
    if not b:
        return MALFORMED, 'empty ID', None
    if b'\x00' in b:
        b = b[:b.index(b'\x00')]
        if not b:
            return MALFORMED, 'empty ID', None
    if len(b) > LIMITS['total']:
        return MALFORMED, f"longer than {LIMITS['total']} bytes", None
    colon = b.find(b':')
    if colon < 0:
        return MALFORMED, "no ':' (namespace:type/name)", None
    slash = b.find(b'/', colon)
    if slash < 0:
        return MALFORMED, "no '/' after the type (namespace:type/name)", None
    ns, typ, name = b[:colon], b[colon + 1:slash], b[slash + 1:]
    for what, part, mx in (('namespace', ns, LIMITS['namespace']), ('type', typ, LIMITS['type']),
                           ('name', name, LIMITS['name'])):
        why = _segment(what, part, mx)
        if why:
            return MALFORMED, why, None
    rid = ResourceId(b.decode(), ns.decode(), typ.decode(), name.decode())
    t = TYPES.get(rid.type)
    if t is None:
        return UNKNOWN_TYPE, f"unknown resource type '{rid.type}'", rid
    if t['status'] == 'reserved':
        return RESERVED_TYPE, f"resource type '{rid.type}' is reserved, not loadable by this engine", rid
    return OK, '', rid


def is_id(text, typ):
    code, _, rid = parse_id(text)
    return code == OK and rid.type == typ


def type_of(text):
    """The type segment of a readable ID, or None."""
    _, _, rid = parse_id(text)
    return rid.type if rid else None


def reserved_namespace(ns):
    return ns in RESERVED_NAMESPACES


def package_id_error(pid):
    """None, or why `pid` is not a package ID (the engine's words)."""
    b = _bytes(pid)
    if not b:
        return 'empty package ID'
    if len(b) > PACKAGE_ID['max_bytes']:
        return f"package ID longer than {PACKAGE_ID['max_bytes']} bytes"
    segs, at = 0, 0
    while at <= len(b):
        dot = b.find(b'.', at)
        seg = b[at:dot] if dot >= 0 else b[at:]
        segs += 1
        if segs > PACKAGE_ID['max_segments']:
            return f"package ID has more than {PACKAGE_ID['max_segments']} segments"
        why = _segment('package ID segment', seg, PACKAGE_ID['max_bytes'])
        if why:
            return why
        at += len(seg) + 1
        if dot < 0:
            break
        if at == len(b):
            return "package ID ends with '.'"
    return None


def _article(noun):
    return 'an' if noun[0] in 'aeiou' else 'a'


def noun(typ):
    return TYPES[typ]['noun']


# ---- a set of provided resources, and typed resolution -------------------------

@dataclass
class Entry:
    id: str
    type: str
    provider: int            # 0: the package being validated
    index: int = 0


class ResourceSet:
    """What one package's references may resolve against: its own
    resources (provider 0) and its dependencies' (1..), plus its imports.
    The engine's hta_res_set, with the same refusals."""

    def __init__(self, providers=('',)):
        self.entries = {}
        self.order = []
        self.providers = list(providers)
        self.imports = set()            # (provider, resource id)
        self.required = set()           # providers provider 0 requires

    def provider_name(self, p):
        if p < len(self.providers) and self.providers[p]:
            return f'package {self.providers[p]}'
        return 'an unnamed package' if p else 'this package'

    def add(self, rid, typ, provider, index=0):
        d = self.entries.get(rid)
        if d is not None:
            if d.provider == provider:
                raise ResourceError(f'{rid}: provided twice by {self.provider_name(provider)}')
            raise ResourceError(f'{rid}: provided by both {self.provider_name(d.provider)} and '
                                f'{self.provider_name(provider)} (duplicate providers are refused, never picked)')
        if len(self.entries) >= PACKAGE_LIMITS['resources_per_set']:
            raise ResourceError(f"more than {PACKAGE_LIMITS['resources_per_set']} resources in one package set")
        e = Entry(rid, typ, provider, index)
        self.entries[rid] = e
        self.order.append(e)
        return e

    def _same_name(self, rid):
        for e in self.order:
            _, _, o = parse_id(e.id)
            if o and o.namespace == rid.namespace and o.name == rid.name and e.type != rid.type:
                return e
        return None

    def resolve(self, field_name, who, ref):
        """The Entry `ref` names, or ResourceError with the engine's words."""
        f = REFERENCES[field_name]
        want = f['expects']
        label = f['label']
        code, why, rid = parse_id(ref)
        if code == MALFORMED:
            raise ResourceError(f"{who}: {label} '{ref}' is not a resource ID: {why} (expected namespace:{want or 'type'}/name)")
        if code != OK:
            what = f'{_article(noun(want))} {noun(want)}' if want else 'an importable resource'
            raise ResourceError(f"{who}: {label} '{ref}': {why} (expected {what})")
        e = self.entries.get(ref)
        if want and rid.type != want:
            if e is not None:
                raise ResourceError(f'{who}: {label} {ref} is {_article(noun(rid.type))} {noun(rid.type)}, '
                                    f'expected {_article(noun(want))} {noun(want)}')
            raise ResourceError(f"{who}: {label} '{ref}' is not {_article(noun(want))} {noun(want)} ID (namespace:{want}/name)")
        if e is None:
            o = self._same_name(rid)
            hint = f' ({o.id} is {_article(noun(o.type))} {noun(o.type)})' if o else ''
            raise ResourceError(f'{who} references missing {noun(rid.type)} {ref}{hint}')
        if e.provider == 0:
            return e
        pa, pb = self.provider_name(e.provider), self.provider_name(0)
        if f['resolves'] == 'same package':
            raise ResourceError(f'{who}: {label} {ref} is provided by {pa}; a {label} must be in the same package')
        if (e.provider, ref) in self.imports:
            return e
        if e.provider in self.required:
            raise ResourceError(f'{who}: {label} {ref} is provided by {pa}, which {pb} requires but does not import it '
                                f'from (list it in requires[].resources)')
        raise ResourceError(f'{who}: {label} {ref} is provided by {pa}, which {pb} does not require')


# ---- package declarations ---------------------------------------------------------

@dataclass
class Requirement:
    package: str                       # a package ID
    resources: list = field(default_factory=list)   # what is imported from it


@dataclass
class PackageDecl:
    """A manifest's "package" member: id, provides, requires."""
    id: str
    provides: list = field(default_factory=list)
    requires: list = field(default_factory=list)     # Requirement

    def record(self):
        """The canonical member (lists sorted: canonical order is a rule,
        so the writer produces it and the reader refuses anything else)."""
        return {'id': self.id, 'provides': sorted(self.provides),
                'requires': [{'package': r.package, 'resources': sorted(r.resources)}
                             for r in sorted(self.requires, key=lambda r: r.package.encode())],
                'schema': PACKAGE_SCHEMA}

    def imports(self):
        return [(r.package, rid) for r in self.requires for rid in r.resources]


def _id_list(pkg, what, values, importable_only, mx):
    if not isinstance(values, list):
        raise ResourceError(f'{pkg}: {what} is not a list')
    prev = None
    for i, v in enumerate(values):
        if not isinstance(v, str) or len(_bytes(v)) > 255:
            raise ResourceError(f'{pkg}: {what}: an entry is not a string (or over 255 bytes)')
        code, why, rid = parse_id(v)
        if code != OK:
            raise ResourceError(f"{pkg}: {what} '{v}': {why}")
        t = TYPES[rid.type]
        if reserved_namespace(rid.namespace):
            raise ResourceError(f"{pkg}: {what} {v}: namespace '{rid.namespace}' is reserved for built-in content")
        if t['scope'] == 'placement':
            raise ResourceError(f"{pkg}: {what} {v}: {_article(t['noun'])} {t['noun']} is a placement, never provided or imported")
        if importable_only and not t['importable']:
            raise ResourceError(f"{pkg}: {what} {v}: {t['noun']} cannot be imported from another package "
                                f'(only importable types: see megamod-resources)')
        if prev is not None and _bytes(prev) >= _bytes(v):
            raise ResourceError(f'{pkg}: {what} lists {v} twice' if prev == v else
                                f'{pkg}: {what} is not in canonical (byte) order at {v}')
        if i >= mx:
            raise ResourceError(f'{pkg}: {what} has more than {mx} entries')
        prev = v
    return list(values)


def parse_decl(manifest):
    """The PackageDecl of a manifest dict, None when it declares none (an
    implicit, pre-X4 package). Strict, as the engine: every field present,
    nothing unknown, IDs valid, lists canonical. Raises ResourceError."""
    if 'package' not in manifest:
        return None
    m = manifest['package']
    if not isinstance(m, dict):
        raise ResourceError('package: not an object')
    pkg = 'package'
    if 'id' in m:
        why = package_id_error(m['id']) if isinstance(m['id'], str) else 'malformed id'
        if why:
            raise ResourceError(f"package '{m['id']}': {why}")
        pkg = f"package {m['id']}"
    known = ('id', 'provides', 'requires', 'schema')
    for k in m:
        if k not in known:
            raise ResourceError(f"{pkg}: unknown field '{k}' (schema {PACKAGE_SCHEMA} has id, provides, requires, schema)")
    if 'schema' in m and m['schema'] != PACKAGE_SCHEMA:
        raise ResourceError(f"{pkg}: unsupported package schema {m['schema']} (this engine has {PACKAGE_SCHEMA})")
    if any(k not in m for k in known):
        raise ResourceError(f'{pkg}: needs id, schema, provides and requires')
    provides = _id_list(pkg, 'provides', m['provides'], False, PACKAGE_LIMITS['provides'])
    if not isinstance(m['requires'], list):
        raise ResourceError(f'{pkg}: requires is not a list')
    requires, prev, total = [], None, 0
    for q in m['requires']:
        if len(requires) >= PACKAGE_LIMITS['requires']:
            raise ResourceError(f"{pkg}: requires more than {PACKAGE_LIMITS['requires']} packages")
        if not isinstance(q, dict):
            raise ResourceError(f'{pkg}: a requirement is not an object')
        for k in q:
            if k not in ('package', 'resources'):
                raise ResourceError(f"{pkg}: unknown requirement field '{k}'")
        if 'package' not in q or 'resources' not in q:
            raise ResourceError(f'{pkg}: a requirement needs package and resources')
        why = package_id_error(q['package']) if isinstance(q['package'], str) else 'malformed requirement package'
        if why:
            raise ResourceError(f"{pkg}: requires '{q['package']}': {why}")
        res = _id_list(pkg, f"requires {q['package']} resources", q['resources'], True,
                       PACKAGE_LIMITS['imports'] - total)
        total += len(res)
        if prev is not None and _bytes(prev) >= _bytes(q['package']):
            raise ResourceError(f"{pkg}: requires package {q['package']} twice" if prev == q['package'] else
                                f"{pkg}: requires is not in canonical (package ID) order at {q['package']}")
        prev = q['package']
        requires.append(Requirement(q['package'], res))
    if any(r.package == m['id'] for r in requires):
        raise ResourceError(f'{pkg}: requires itself')
    return PackageDecl(m['id'], provides, requires)
