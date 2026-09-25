"""Workshop imports as queued jobs, for the web UI: fetch, analyze, build,
validate, stage. The same shape as the map library (library.py): one
SQLite table, one worker thread, jobs survive a restart and requeue."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

from . import workshop as ws

STATES = ('QUEUED', 'FETCHING', 'ANALYZING', 'CONVERTING', 'VALIDATING', 'STAGED', 'FAILED')
KINDS = ('characters', 'weapons', 'maps')
# Unfinished jobs the queue holds at once: a whole collection fits.
MAX_ACTIVE = 64
# Collection items not worth a download: they hold nothing we build.
SKIP_KINDS = {'gamemode': 'a gamemode (Lua, nothing to build)',
              'entity': 'an entity, tool or effects addon (import it by itself to try)'}
MAX_ITEM_BYTES = 4 * 1024**3
ARTIFACT = re.compile(r'[a-z0-9][a-z0-9_.-]{0,120}\.(oalasset|oalmap|json|png)')


class WorkshopJobs:
    def __init__(self, root, api=None, steamcmd_dir=None, game_dirs=(), vpks=(), asset_test=None,
                 map_test=None, icd=None, fetcher=None, importer=None, allow_install=True, start=True):
        self.root = Path(root).expanduser().resolve()
        self.dir = self.root / 'workshop'
        self.downloads = self.dir / 'downloads'
        self.jobdir = self.dir / 'jobs'
        for p in (self.downloads, self.jobdir):
            p.mkdir(parents=True, exist_ok=True)
        self.api = api or ws.WorkshopAPI()
        self.steamcmd = ws.SteamCMD(Path(steamcmd_dir) if steamcmd_dir else self.root / 'steamcmd')
        self.allow_install = allow_install
        self.game_dirs = tuple(game_dirs)
        self.vpks = tuple(vpks)
        self.asset_test = Path(asset_test) if asset_test else None
        self.map_test = Path(map_test) if map_test else None
        self.icd = Path(icd) if icd else None
        self.fetcher = fetcher or self._fetch
        self.importer = importer or ws.import_addon
        self.db = self.root / 'jobs.sqlite3'
        self.lock = threading.RLock()
        self.stop = threading.Event()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS workshop_jobs (id TEXT PRIMARY KEY, item TEXT NOT NULL, '
                       'title TEXT NOT NULL, kinds TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, '
                       'updated REAL NOT NULL, log TEXT NOT NULL, report TEXT, error TEXT)')
            db.execute("UPDATE workshop_jobs SET state='QUEUED', log=substr(log || '\nRecovered after service restart',-65536) "
                       "WHERE state NOT IN ('QUEUED','STAGED','FAILED')")
        self.thread = None
        if start:
            self.thread = threading.Thread(target=self._worker, name='assetlab-workshop', daemon=True)
            self.thread.start()

    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    # ------------------------------------------------------------ public

    def submit(self, item, kinds=KINDS, title=None) -> str:
        iid = ws.parse_id(item)
        kinds = self._kinds(kinds)
        with self.lock, self.connect() as db:
            if self._active(db) >= MAX_ACTIVE:
                raise ValueError('queue is full')
            return self._insert(db, iid, kinds, title)

    def submit_collection(self, collection, kinds=KINDS, limit=50) -> dict:
        """Queue every item of a collection worth importing. Skips what is
        private or removed, banned, a gamemode, over 4 GiB, or already
        queued or staged; stops at `limit` or when the queue is full, and
        says which it did not reach."""
        cid = ws.parse_id(collection)
        kinds = self._kinds(kinds)
        ids = self.api.collection(cid)
        if not ids:
            raise ValueError(f'{cid} is not a collection, or it is empty or private')
        info = {i['id']: i for i in self.api.details(ids)}
        queued, skipped = [], []
        with self.lock, self.connect() as db:
            have = {r['item'] for r in db.execute("SELECT item FROM workshop_jobs WHERE state!='FAILED'")}
            room = MAX_ACTIVE - self._active(db)
            for iid in ids:
                it = info.get(iid)
                title = (it or {}).get('title') or iid
                why = None
                if not it or not it['ok']:
                    why = 'private or removed'
                elif it['banned']:
                    why = 'banned on the Workshop'
                elif it['kind'] in SKIP_KINDS:
                    why = SKIP_KINDS[it['kind']]
                elif it['size'] > MAX_ITEM_BYTES:
                    why = f"too large ({it['size'] / 2**30:.1f} GiB)"
                elif iid in have:
                    why = 'already queued or imported'
                elif len(queued) >= min(limit, room):
                    why = 'queue is full' if len(queued) >= room else f'past the limit of {limit}'
                if why:
                    skipped.append({'id': iid, 'title': title, 'reason': why})
                    continue
                queued.append({'id': iid, 'title': title, 'kind': it['kind'],
                               'job_id': self._insert(db, iid, kinds, title)})
                have.add(iid)
        return {'collection': cid, 'items': len(ids), 'queued': queued, 'skipped': skipped}

    @staticmethod
    def _kinds(kinds):
        kinds = [k for k in kinds if k in KINDS]
        if not kinds:
            raise ValueError('choose at least one of characters, weapons, maps')
        return kinds

    @staticmethod
    def _active(db):
        return db.execute("SELECT count(*) FROM workshop_jobs WHERE state NOT IN ('STAGED','FAILED')").fetchone()[0]

    @staticmethod
    def _insert(db, iid, kinds, title):
        jid = uuid.uuid4().hex
        now = time.time()
        db.execute('INSERT INTO workshop_jobs VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (jid, iid, title or iid, ','.join(kinds), 'QUEUED', now, now, 'Queued', None, None))
        return jid

    def jobs(self):
        with self.lock, self.connect() as db:
            out = []
            for r in db.execute('SELECT * FROM workshop_jobs ORDER BY created DESC LIMIT 100'):
                d = dict(r)
                rep = json.loads(d.pop('report') or '{}')
                d['built'] = rep.get('built', [])
                d['failed'] = rep.get('failed', [])
                d.pop('log')
                out.append(d)
            return out

    def job(self, jid):
        with self.lock, self.connect() as db:
            r = db.execute('SELECT * FROM workshop_jobs WHERE id=?', (jid,)).fetchone()
            if not r:
                return None
            d = dict(r)
            d['report'] = json.loads(d['report'] or 'null')
            return d

    def artifact(self, jid, name):
        """A staged file of a finished job, or None. Only listed kinds of
        file, only directly inside the job's own folder."""
        if not re.fullmatch(r'[0-9a-f]{32}', str(jid)) or not ARTIFACT.fullmatch(str(name)):
            return None
        p = (self.jobdir / jid / name).resolve()
        if p.parent != (self.jobdir / jid).resolve() or not p.is_file():
            return None
        return p

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)

    # ------------------------------------------------------------ worker

    def _update(self, jid, state=None, line=None, report=None, error=None, title=None):
        with self.lock, self.connect() as db:
            r = db.execute('SELECT log FROM workshop_jobs WHERE id=?', (jid,)).fetchone()
            if not r:
                return
            log = (r['log'] + ('\n' + line if line else ''))[-65536:]
            db.execute('UPDATE workshop_jobs SET state=coalesce(?,state), updated=?, log=?, report=coalesce(?,report), '
                       'error=coalesce(?,error), title=coalesce(?,title) WHERE id=?',
                       (state, time.time(), log, json.dumps(report) if report is not None else None, error, title, jid))

    def _fetch(self, item):
        if not item['file_url'] and not self.steamcmd.installed():
            if not self.allow_install:
                raise ws.WorkshopError('SteamCMD is not installed and installing it is disabled')
            self.steamcmd.install()
        return ws.fetch(item, self.downloads, self.steamcmd)

    def _worker(self):
        while not self.stop.is_set():
            with self.lock, self.connect() as db:
                r = db.execute("SELECT id FROM workshop_jobs WHERE state='QUEUED' ORDER BY created LIMIT 1").fetchone()
                if r:
                    db.execute("UPDATE workshop_jobs SET state='FETCHING', updated=? WHERE id=?", (time.time(), r['id']))
            if not r:
                self.stop.wait(0.5)
                continue
            try:
                self.run(r['id'])
            except Exception as e:  # noqa: BLE001 -- a job's failure is its own
                self._update(r['id'], 'FAILED', f'Failed: {e}', error=str(e)[:2000])

    def run(self, jid):
        j = self.job(jid)
        kinds = tuple(j['kinds'].split(','))
        self._update(jid, 'FETCHING', f"Looking up {j['item']}")
        items = self.api.details([j['item']])
        if not items or not items[0]['ok']:
            raise ws.WorkshopError('no such Workshop item, or it is private')
        item = items[0]
        how = 'direct download' if item['file_url'] else 'SteamCMD'
        self._update(jid, line=f"{item['title']} ({item['size'] / 2**20:.1f} MB, {how})", title=item['title'])
        path = self.fetcher(item)
        self._update(jid, 'ANALYZING', f'Fetched {Path(path).name}')
        a = ws.analyze(path)
        self._update(jid, line=f'{len(a.characters)} characters, {len(a.weapons)} weapons, {len(a.maps)} maps'
                               + (f"; {'; '.join(a.warnings[:3])}" if a.warnings else ''))
        if not a.buildable():
            raise ws.WorkshopError('nothing in this addon can be built: ' + '; '.join(a.warnings[:3]))
        out = self.jobdir / jid
        out.mkdir(parents=True, exist_ok=True)
        (out / 'analysis.json').write_text(json.dumps({'item': item, 'analysis': a.to_json()}, indent=2) + '\n')
        root = ws.extract(path, self.downloads / f"{item['id']}_files")
        self._update(jid, 'CONVERTING', 'Building packages')
        report = self.importer(a, root, out, self.game_dirs, self.vpks, kinds)
        report['item'] = item
        self._update(jid, 'VALIDATING', f"Built {len(report['built'])}, failed {len(report['failed'])}", report=report)
        for b in report['built']:
            b['validated'], b['preview'] = self._validate(out, b)
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        if not report['built']:
            self._update(jid, 'FAILED', 'Nothing built', report=report,
                         error='; '.join(f"{f['name']}: {f['error']}" for f in report['failed'])[:2000])
            return
        self._update(jid, 'STAGED', f"Staged {len(report['built'])} package(s)", report=report)
        self._tidy()

    def _validate(self, out, b):
        """Render the package in the engine's own host tool, when built;
        its picture becomes the preview. None when no tool is configured."""
        tool = self.map_test if b['kind'] == 'map' else self.asset_test
        if not tool or not tool.is_file():
            return None, None
        env = os.environ.copy()
        if self.icd and self.icd.is_file():
            env['VK_ICD_FILENAMES'] = str(self.icd)
        prefix = out / (Path(b['package']).stem + '_check')
        r = subprocess.run([str(tool), str(out / b['package']), str(prefix)], capture_output=True, text=True,
                           timeout=240, env=env)
        if r.returncode:
            b['validation_log'] = (r.stdout + r.stderr)[-2000:]
            return False, None
        shots = sorted(out.glob(prefix.name + '*.ppm'))
        preview = None
        if shots:
            try:
                from PIL import Image
                with Image.open(shots[0]) as im:
                    preview = Path(b['package']).stem + '.png'
                    im.save(out / preview)
            except (OSError, ImportError):
                preview = None
        for s in shots:
            s.unlink(missing_ok=True)
        return True, preview

    def _tidy(self, keep_bytes=8 * 1024**3):
        """Downloads are a cache: past 8 GiB, the oldest go."""
        items = sorted((p for p in self.downloads.iterdir()), key=lambda p: p.stat().st_mtime)
        size = lambda p: sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else p.stat().st_size
        total = sum(size(p) for p in items)
        for p in items:
            if total <= keep_bytes:
                break
            total -= size(p)
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
