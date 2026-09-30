"""Bounded read-only BSA v103 provider for owner-supplied classic TES4 files.

No extraction paths, plugin interpretation, or native runtime dependency.
File/folder hashes are retained but not trusted as content integrity checks.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib

class BSAError(ValueError): pass
@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    size: int
    compressed: bool

class Archive:
    def __init__(self,path):
        self.path=Path(path);self.entries={};size=self.path.stat().st_size
        def read(f,n):
            if n<0 or n>64*1024*1024:raise BSAError('BSA: table budget exceeded')
            b=f.read(n)
            if len(b)!=n:raise BSAError('BSA: truncated table')
            return b
        with self.path.open('rb') as f:
            magic,version,offset,flags,folders,files,folder_bytes,name_bytes,_=struct.unpack('<4s8I',read(f,36))
            if magic!=b'BSA\0' or version!=103:raise BSAError('BSA: only v103 is supported')
            if flags&3!=3 or offset<36 or offset>size or folders>100000 or files>1000000:raise BSAError('BSA: invalid header')
            f.seek(offset);directory=[struct.unpack('<QII',read(f,16)) for _ in range(folders)]
            rows=[];measured=0
            for _,count,_ in directory:
                if count>files-len(rows):raise BSAError('BSA: inconsistent folder file count')
                length=read(f,1)[0];raw=read(f,length);measured+=length
                if not raw or raw[-1:]!=b'\0':raise BSAError('BSA: invalid folder name')
                folder=raw[:-1].decode('cp1252').replace('\\','/').lower()
                if folder.startswith('/') or ':' in folder or any(p in ('.','..') for p in folder.split('/')):raise BSAError('BSA: invalid folder path')
                for _ in range(count):
                    _,stored,start=struct.unpack('<QII',read(f,16));amount=stored&0x3fffffff
                    if start+amount>size:raise BSAError('BSA: file exceeds archive')
                    rows.append((folder,start,amount,bool(flags&4)^bool(stored&0x40000000)))
            if len(rows)!=files or measured!=folder_bytes:raise BSAError('BSA: inconsistent table counts')
            names=read(f,name_bytes).split(b'\0');end=f.tell()
            if len(names)!=files+1 or names[-1]!=b'':raise BSAError('BSA: invalid file names table')
            for (folder,start,amount,compressed),name in zip(rows,names):
                path=(folder+'/'+name.decode('cp1252').replace('\\','/').lower()).lstrip('/')
                if not path or any(p in ('','..','.') for p in path.split('/')) or ':' in path or path in self.entries or start<end:raise BSAError('BSA: invalid/duplicate relative path or table overlap')
                self.entries[path]=Entry(path,start,amount,compressed)
            ordered=sorted(self.entries.values(),key=lambda e:e.offset)
            if any(a.offset+a.size>b.offset for a,b in zip(ordered,ordered[1:])):raise BSAError('BSA: overlapping file payloads')
    def read(self,path,limit=64*1024*1024):
        key=str(path).replace('\\','/').lower()
        if key not in self.entries:raise BSAError('BSA: member not found: '+key)
        e=self.entries[key]
        if e.size>limit+4:raise BSAError('BSA: stored payload exceeds budget')
        with self.path.open('rb') as f:f.seek(e.offset);blob=f.read(e.size)
        if len(blob)!=e.size:raise BSAError('BSA: truncated payload')
        if not e.compressed:
            if len(blob)>limit:raise BSAError('BSA: payload exceeds budget')
            return blob
        if len(blob)<4:raise BSAError('BSA: missing compressed length')
        expected=struct.unpack_from('<I',blob)[0]
        if expected>limit:raise BSAError('BSA: decoded payload exceeds budget')
        dec=zlib.decompressobj()
        try:raw=dec.decompress(blob[4:],expected+1)
        except zlib.error as x:raise BSAError('BSA: invalid compressed payload') from x
        if len(raw)!=expected or not dec.eof or dec.unused_data or dec.unconsumed_tail:raise BSAError('BSA: compressed payload length or trailing data invalid')
        return raw
