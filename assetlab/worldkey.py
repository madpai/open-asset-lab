"""The world key: what two MegaMod peers must agree on to share a world.

This is the reference implementation of MegaMod's
`src/asset/external_map.c` world key (schema 1); both must produce the same
value for the same package, and MegaMod's scripts/test_x2.sh checks that
they do. It is computed from the package's own canonical bytes (Asset Lab
writes them deterministically), never from re-derived values:

    FNV-1a 64 over
      b"OALW", u32 schema, u32 package version,
      u32 vertex, index, group and spawn counts,
      the header's world bounds (24 bytes; nav is built inside them),
      every vertex, index and material-group record, as stored,
      every spawn record, as stored,
      then each PLAYED manifest member, in manifest order:
        u32 key length, key, u32 value length, the value's exact bytes.
    (0 becomes 1.) The 32-bit key in MegaMod's v10 map check is
    low 32 bits XOR high 32 bits.

Left out, so they cannot split two otherwise identical worlds: every other
manifest member (source and provenance, importer version, display name,
reports, warnings, geometry statistics) and texture pixels (how the world
looks, not where anything is or what it does).

A manifest member the runtime starts to play by must be added to PLAYED
here and in external_map.c together (and the schema bumped).

Pure Python and byte-at-a-time: instant for original worlds, some seconds
for an imported map of tens of megabytes of geometry.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

WORLD_KEY_SCHEMA = 1
PLAYED = ('breakables', 'flag_points', 'spawn_points', 'weather', 'world_entities')

_OFFSET = 14695981039346656037
_PRIME = 1099511628211
_MASK = (1 << 64) - 1


class _Fnv:
    def __init__(self):
        self.h = _OFFSET

    def bytes(self, b):
        h = self.h
        for c in b:
            h = ((h ^ c) * _PRIME) & _MASK
        self.h = h

    def u32(self, v):
        self.bytes(struct.pack('<I', v & 0xFFFFFFFF))


def manifest_members(manifest: bytes):
    """(key, exact value bytes) for each top-level member, in order."""
    text = manifest.decode('latin-1')          # byte offsets == str offsets
    dec = json.JSONDecoder()
    ws = ' \t\n\r'
    i = 0

    def skip(i):
        while i < len(text) and text[i] in ws:
            i += 1
        return i

    i = skip(i)
    if text[i:i + 1] != '{':
        raise ValueError('manifest is not an object')
    i = skip(i + 1)
    out = []
    if text[i:i + 1] == '}':
        return out
    while True:
        if text[i:i + 1] != '"':
            raise ValueError('malformed manifest')
        key, i = json.decoder.scanstring(text, i + 1)
        i = skip(i)
        if text[i:i + 1] != ':':
            raise ValueError('malformed manifest')
        i = skip(i + 1)
        _, end = dec.raw_decode(text, i)
        out.append((key, manifest[i:end]))
        i = skip(end)
        if text[i:i + 1] == ',':
            i = skip(i + 1)
            continue
        if text[i:i + 1] == '}' and skip(i + 1) == len(text):
            return out
        raise ValueError('malformed manifest')


def world_digest(data: bytes) -> int:
    """The 64-bit world key of an OALMAP's bytes."""
    magic, version, ml, vc, ic, gc, tc, sc = struct.unpack_from('<4s7I', data, 0)
    if magic != b'OALM' or version not in (1, 2, 3):
        raise ValueError('not an OALMAP v1-v3')
    group = 20 if version >= 2 else 16
    f = _Fnv()
    f.bytes(b'OALW'); f.u32(WORLD_KEY_SCHEMA); f.u32(version)
    for v in (vc, ic, gc, sc):
        f.u32(v)
    f.bytes(data[36:60])
    at = 64 + ml
    geo = vc * 40 + ic * 4 + gc * group
    f.bytes(data[at:at + geo])
    at += geo
    for _ in range(tc):
        _, _, n = struct.unpack_from('<3I', data, at)
        at += 12 + n
    f.bytes(data[at:at + sc * 16])
    manifest = data[64:64 + ml]
    if ml:
        try:
            members = manifest_members(manifest)
        except ValueError:
            members = None
        if members is None:                    # counted whole: stricter, never looser
            f.bytes(b'RAW'); f.u32(ml); f.bytes(manifest)
        else:
            for key, value in members:
                if key in PLAYED:
                    k = key.encode()
                    f.u32(len(k)); f.bytes(k); f.u32(len(value)); f.bytes(value)
    return f.h or 1


def fold(digest: int) -> int:
    """The 32 bits MegaMod's v10 map check carries."""
    return (digest ^ (digest >> 32)) & 0xFFFFFFFF


def world_key(path) -> dict:
    d = world_digest(Path(path).read_bytes())
    return {'package': str(path), 'world_digest': f'{d:016x}', 'world_key': f'{fold(d):08x}',
            'schema': WORLD_KEY_SCHEMA}
