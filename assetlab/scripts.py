"""Host-side gameplay scripts (MegaMod X3): packaging and preflight.

A script is CONTENT: an authored ID `namespace:script/name`, the API it was
written for (`megamod.v1`), the callbacks it declares, and its Lua source
text. Open Asset Lab never runs a script. It checks the text (ASCII, size,
the declared callbacks are defined) and -- when a Lua 5.4 compiler is on
PATH -- has `luac5.4 -p` parse it: parse only, nothing executes. MegaMod
loads the source (never bytecode: bytecode is not portable between its
ARM64 and x86-64 builds and can crash a VM) and runs it on the host only.
See MegaMod docs/SCRIPTING.md for what a script may do.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

API = 'megamod.v1'
CALLBACKS = ('on_used', 'on_ability')      # MegaMod's megamod.v1 callbacks
MAX_SCRIPTS = 16
MAX_SOURCE = 32 * 1024                      # bytes per script
MAX_POOL = 64 * 1024                        # bytes for all of a world's scripts

SCRIPT_DIR = Path(__file__).parent / 'data' / 'scripts'


@dataclass
class Script:
    id: str                     # namespace:script/name
    source: str                 # Lua text
    callbacks: list = field(default_factory=list)
    api: str = API


def load_source(rel):
    """An original script shipped with Open Asset Lab (data/scripts/...)."""
    return (SCRIPT_DIR / rel).read_text(encoding='ascii')


def lua54_compiler():
    """A Lua 5.4 `luac` for a parse-only check, or None. A 5.5 compiler is
    not used: its grammar is not the runtime's."""
    for name in ('luac5.4', 'luac54', 'luac'):
        path = shutil.which(name)
        if not path:
            continue
        try:
            out = subprocess.run([path, '-v'], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if re.search(r'Lua 5\.4\.', out.stdout + out.stderr):
            return path
    return None


def syntax_errors(sc, compiler):
    """`luac -p` (parse, never run) on the source: [] or its message."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / 'script.lua'
        f.write_text(sc.source, encoding='ascii')
        r = subprocess.run([compiler, '-p', str(f)], capture_output=True, text=True, timeout=30)
    if r.returncode == 0:
        return []
    msg = (r.stderr or r.stdout).strip().replace(str(f), sc.id)
    return [f'{sc.id}: syntax error: {msg}']


def _defines(source, name):
    return re.search(rf'^\s*function\s+{name}\s*\(', source, re.M) is not None


def validate(scripts, ns, check_syntax=True):
    """Diagnostics for a world's scripts (`ns`: the world's namespace) or a
    library's (`ns` None: any namespace); each names the script."""
    from . import ids
    errs, seen, total = [], set(), 0
    if len(scripts) > MAX_SCRIPTS:
        errs.append(f'{len(scripts)} scripts; the runtime takes at most {MAX_SCRIPTS}')
    compiler = lua54_compiler() if check_syntax else None
    for sc in scripts:
        ok, why = ids.valid_id(sc.id)
        if not ok:
            errs.append(f'{sc.id!r}: malformed script ID: {why}')
            continue
        s_ns, _, rest = sc.id.partition(':')
        if rest.partition('/')[0] != 'script':
            errs.append(f'{sc.id}: a script ID has type script')
            continue
        if ns is not None and s_ns != ns:
            errs.append(f"{sc.id}: scripts belong to the world's namespace {ns!r}")
        if sc.id in seen:
            errs.append(f'{sc.id}: duplicate script ID')
            continue
        seen.add(sc.id)
        if sc.api != API:
            errs.append(f"{sc.id}: unsupported script API {sc.api!r} (MegaMod has {API})")
        if not sc.callbacks:
            errs.append(f'{sc.id}: declares no callbacks')
        for cb in sc.callbacks:
            if cb not in CALLBACKS:
                errs.append(f"{sc.id}: unknown callback {cb!r} ({API} has {', '.join(CALLBACKS)})")
            elif not _defines(sc.source, cb):
                errs.append(f'{sc.id}: declares {cb} but defines no function {cb}')
        try:
            raw = sc.source.encode('ascii')
        except UnicodeEncodeError:
            errs.append(f'{sc.id}: source must be ASCII text')
            continue
        if any(c < 0x20 and c not in (9, 10, 13) or c == 0x7F for c in raw):
            errs.append(f'{sc.id}: source has control characters (bytecode is never packaged)')
            continue
        if len(raw) > MAX_SOURCE:
            errs.append(f'{sc.id}: source is {len(raw)} bytes; at most {MAX_SOURCE}')
        total += len(raw)
        if compiler:
            errs += syntax_errors(sc, compiler)
    if total > MAX_POOL:
        errs.append(f"a world's scripts are {total} bytes; at most {MAX_POOL}")
    return errs


def record(sc):
    return {'id': sc.id, 'api': sc.api, 'callbacks': list(sc.callbacks), 'source': sc.source}
