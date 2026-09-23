"""Acquisition boundary: providers register local, permitted sources for the queue."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Protocol

class Provider(Protocol):
    def sources(self) -> list[dict]: ...
    def resolve(self,source_id: str) -> Path | None: ...

class LocalDirectories:
    def __init__(self,roots):
        self.roots=[Path(p).expanduser().resolve() for p in roots]

    def _entries(self):
        for root in self.roots:
            if not root.is_dir():continue
            for p in sorted(root.glob('*.bsp')):
                if p.is_symlink() or not p.is_file() or p.stat().st_size>512*1024*1024:continue
                yield root,p

    def sources(self):
        return [{'id':hashlib.sha256(str(p).encode()).hexdigest()[:20],
                 'name':p.name,'bytes':p.stat().st_size,'source':root.name}
                for root,p in self._entries()]

    def resolve(self,source_id):
        if not isinstance(source_id,str) or len(source_id)!=20:return None
        for _,p in self._entries():
            if hashlib.sha256(str(p).encode()).hexdigest()[:20]==source_id:return p
        return None
