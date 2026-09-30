"""Repeat a content build and compare its compiled worlds with the native loader.

This is package evidence, not a rendering, gameplay or device performance test.
The supplied engine is an already-built megamod-resources executable.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .dependencies import check_package, directory_source


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): sha256(p)
            for p in sorted(root.rglob('*'))
            if p.is_file() and p.suffix in ('.oalmap', '.oalasset')}


def build(path, bundle, evidence, label):
    """Use fresh interpreters so cached sibling imports cannot hide drift."""
    command = [sys.executable, '-m', 'assetlab', 'project', 'build', str(Path(path).resolve()),
               '--output', str(bundle), '--json']
    run = subprocess.run(command, cwd=Path(__file__).resolve().parent.parent,
                         capture_output=True, text=True)
    (evidence / f'{label}.stdout').write_text(run.stdout)
    (evidence / f'{label}.stderr').write_text(run.stderr)
    if run.returncode:
        raise ValueError(f'{label} exited {run.returncode}; see {label}.stdout/.stderr')
    report = json.loads(run.stdout)
    if not isinstance(report, dict):
        raise ValueError(f'{label} did not return a build report object')
    return report


def compare_world(authored, checked, native):
    """Compare the compiler's promises to the native loader's observations."""
    errors = []

    def equal(field, expected, observed):
        if expected != observed:
            errors.append(f'{field}: Asset Lab {expected!r}, engine {observed!r}')

    if native.get('ok') is not True:
        return [f"engine refused world: {native.get('error', 'missing ok=true')}"]
    equal('world_key', authored['world_key'], native.get('world_key'))
    equal('world_digest', checked.get('world_digest'), native.get('world_digest'))
    pk = native.get('package')
    state = native.get('world_state')
    if not isinstance(pk, dict) or not isinstance(state, dict):
        return errors + ['engine report lacks package or world_state object']
    equal('package.declared', bool(authored['package']), pk.get('declared'))
    equal('package.id', authored['package'] or '', pk.get('id'))
    equal('package.set', checked.get('set'), pk.get('set'))
    if state.get('ok') is not True:
        errors.append(f"engine refused world state: {state.get('error', 'missing ok=true')}")
    for field in ('protocol', 'runtime_objects', 'spatial', 'logical', 'host_only', 'snapshot_bytes'):
        equal(f'world_state.{field}', authored['budget']['world_state'][field], state.get(field))
    bindings = native.get('bindings')
    if not isinstance(bindings, list):
        errors.append('engine report lacks bindings array')
    else:
        equal('bindings', authored['budget']['bindings']['total'], len(bindings))
    return errors


def verify(path, output, engine, timeout=30):
    """Build twice into an exclusive evidence directory; never overwrite a run.

    Project files are local Python, executed just as by project build/budget.
    Loader failures, timeouts and mismatches return ok=false with evidence.
    Invalid arguments raise ValueError/OSError before creating the output.
    """
    engine = Path(engine).resolve()
    if not engine.is_file() or not os.access(engine, os.X_OK):
        raise ValueError(f'engine is not an executable file: {engine}')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be a positive finite number of seconds')
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    bundle = root / 'bundle'
    result = {'ok': False, 'scope': 'deterministic packages and native loader agreement',
              'engine': {'file': str(engine), 'sha256': sha256(engine)},
              'errors': [], 'determinism': {}, 'packages': [], 'worlds': []}
    try:
        first = build(path, bundle, root, 'build')
        (root / 'build.json').write_text(json.dumps(first, indent=2) + '\n')
        with tempfile.TemporaryDirectory(prefix='assetlab-repeat-') as tmp:
            again = Path(tmp)
            build(path, again, root, 'repeat')
            a, b = inventory(bundle), inventory(again)
        changed = [f for f in sorted(a.keys() | b.keys()) if a.get(f) != b.get(f)]
        result['determinism'] = {'ok': not changed, 'files': a, 'different': changed}
        if changed:
            result['errors'].append('repeated builds differ: ' + ', '.join(changed))
        if not first['worlds']:
            result['errors'].append('project has no worlds to verify with the engine')
        fetch = directory_source(bundle)
        for file in a:
            checked = check_package(bundle / file, fetch)
            result['packages'].append(checked)
            result['errors'] += [f'{file}: {e}' for e in checked['errors']]
        checks = {Path(p['file']).relative_to(bundle).as_posix(): p for p in result['packages']}
        for world in first['worlds']:
            name = Path(world['file']).stem
            command = [str(engine), '--bundle', str(bundle), '--world', name]
            record = {'world': world['world'], 'command': command, 'errors': []}
            try:
                run = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
                (root / f'{name}.stdout').write_text(run.stdout)
                (root / f'{name}.stderr').write_text(run.stderr)
                record['returncode'] = run.returncode
                if run.returncode:
                    record['errors'].append(f'engine exited {run.returncode}; see {name}.stdout/.stderr')
                else:
                    native = json.loads(run.stdout)
                    if not isinstance(native, dict):
                        raise ValueError('engine JSON must be an object')
                    record['engine'] = native
                    record['errors'] += compare_world(world, checks[world['file']], native)
            except subprocess.TimeoutExpired as e:
                # TimeoutExpired may hold bytes even when text=True.
                for suffix, data in (('stdout', e.stdout), ('stderr', e.stderr)):
                    (root / f'{name}.{suffix}').write_bytes(
                        data if isinstance(data, bytes) else (data or '').encode())
                record['errors'].append(f'engine timed out after {timeout:g} seconds')
            except (OSError, ValueError, KeyError, TypeError) as e:
                record['errors'].append(f'engine inspection failed: {e}')
            record['ok'] = not record['errors']
            result['worlds'].append(record)
            result['errors'] += [f'{world["world"]}: {e}' for e in record['errors']]
    except (OSError, ValueError, KeyError) as e:
        result['errors'].append(f'project verification failed: {e}')
    result['ok'] = not result['errors']
    (root / 'verification.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


def text(result):
    lines = [('PASS' if result['ok'] else 'FAIL') + ': ' + result['scope']]
    d = result['determinism']
    lines.append(f"  repeated build: {'identical' if d.get('ok') else 'failed'} ({len(d.get('files', {}))} packages)")
    for w in result['worlds']:
        key = w.get('engine', {}).get('world_key', '?')
        lines.append(f"  {w['world']}: {'PASS' if w['ok'] else 'FAIL'}, engine key {key}")
    lines += [f'  error: {e}' for e in result['errors']]
    lines.append('  Rendering, gameplay, touch feel and device performance require separate playtests.')
    return '\n'.join(lines)
