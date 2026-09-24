"""Garry's Mod addon archives (.gma), as the Workshop delivers them.

A GMA is `GMAD`, a format version byte, the author's SteamID64 and a
timestamp (u64 each), a list of required-content strings ended by an empty
one (version > 1), then the addon's name, description and author strings,
an int32 version, the file table -- (u32 index, path string, i64 size, u32
crc) entries ended by index 0 -- and the files' bytes in table order. The
Workshop's legacy `*_legacy.bin` downloads are the same archive in LZMA
"alone" form.
"""
from __future__ import annotations
import lzma
import struct
from pathlib import Path, PurePosixPath

MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_FILES = 20000


class GMAError(ValueError):
    pass


def _cstr(d, at):
    end = d.find(b'\0', at)
    if end < 0:
        raise GMAError('unterminated string')
    return d[at:end].decode('utf-8', 'replace'), end + 1


def load(path):
    """Archive bytes, unpacked from LZMA when the file is a legacy .bin."""
    data = Path(path).read_bytes()
    if data[:4] == b'GMAD':
        return data
    try:
        out = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE, memlimit=MAX_ARCHIVE * 2).decompress(data)
    except lzma.LZMAError as e:
        raise GMAError(f'{path}: not a GMA and not LZMA ({e})') from e
    if out[:4] != b'GMAD':
        raise GMAError(f'{path}: unpacked, but not a GMA')
    return out


class GMA:
    def __init__(self, data):
        if data[:4] != b'GMAD':
            raise GMAError('invalid GMA magic')
        self.version = data[4]
        at = 5 + 16                                   # steamid, timestamp
        if self.version > 1:
            while True:
                s, at = _cstr(data, at)
                if not s:
                    break
        self.name, at = _cstr(data, at)
        self.description, at = _cstr(data, at)
        self.author, at = _cstr(data, at)
        at += 4                                       # addon version
        entries = []
        while True:
            (index,) = struct.unpack_from('<I', data, at); at += 4
            if index == 0:
                break
            name, at = _cstr(data, at)
            size, _crc = struct.unpack_from('<qI', data, at); at += 12
            if size < 0 or len(entries) >= MAX_FILES:
                raise GMAError('file table out of range')
            entries.append((name.replace('\\', '/').lower(), size))
        self.files = {}
        for name, size in entries:
            if at + size > len(data):
                raise GMAError(f'{name}: data past the end of the archive')
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts:
                raise GMAError(f'{name}: unsafe path')
            self.files[name] = (at, size)
            at += size
        self.data = data

    def read(self, name):
        e = self.files.get(name.lower())
        return None if e is None else self.data[e[0]:e[0] + e[1]]

    def extract(self, root):
        """Every file under `root`, as a --game-dir for the importers."""
        root = Path(root)
        for name, (at, size) in self.files.items():
            out = root / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(self.data[at:at + size])
        return root

    def player_models(self):
        return sorted(n for n in self.files if n.startswith('models/') and n.endswith('.mdl')
                      and ('/player/' in n or 'playermodel' in n or n.startswith('models/player')))
