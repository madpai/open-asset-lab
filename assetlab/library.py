"""Persistent single-worker conversion library and staging."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path
from PIL import Image
from .importers.source_bsp import BSPError, SourceBSP
from .package import compile_map, read_manifest
from .providers import LocalDirectories

STATES=('QUEUED','VALIDATING','RESOLVING_DEPENDENCIES','IMPORTING','CONVERTING','COMPILING','VALIDATING_OUTPUT','STAGED','FAILED')
ACTIVE=set(STATES[1:-2])

class Library:
    def __init__(self,root,source_dirs=(),host_test=None,icd=None,material_roots=(),vpks=()):
        self.root=Path(root).expanduser().resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.uploads=self.root/'uploads';self.staged=self.root/'staged';self.work=self.root/'work'
        for p in (self.uploads,self.staged,self.work):p.mkdir(exist_ok=True)
        self.provider=LocalDirectories([*source_dirs,self.uploads])
        self.host_test=Path(host_test).resolve() if host_test else None
        self.icd=Path(icd).resolve() if icd else None
        self.material_roots=tuple(Path(p).resolve() for p in material_roots)
        self.vpks=tuple(Path(p).resolve() for p in vpks)
        self.db=self.root/'jobs.sqlite3';self.lock=threading.RLock();self.stop=threading.Event()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_name TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, log TEXT NOT NULL, report TEXT, stage_id TEXT, error TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS staged (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, map_id TEXT NOT NULL, source_sha256 TEXT NOT NULL, created REAL NOT NULL, package_sha256 TEXT NOT NULL)')
            db.execute("UPDATE jobs SET state='QUEUED', log=substr(log || '\nRecovered after service restart',-65536) WHERE state NOT IN ('QUEUED','STAGED','FAILED')")
        self.thread=threading.Thread(target=self._worker,name='assetlab-worker',daemon=True)
        self.thread.start()

    def connect(self):
        db=sqlite3.connect(self.db,timeout=10)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def sources(self):
        return self.provider.sources()

    def source_path(self,source_id):
        return self.provider.resolve(source_id)

    def submit(self,source_id):
        path=self.source_path(source_id)
        if not path:raise ValueError('source is not registered')
        with self.lock,self.connect() as db:
            n=db.execute("SELECT count(*) FROM jobs WHERE state NOT IN ('STAGED','FAILED')").fetchone()[0]
            if n>=16:raise ValueError('queue is full')
            jid=uuid.uuid4().hex;now=time.time()
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(jid,source_id,path.name,'QUEUED',now,now,'Queued',None,None,None))
        return jid

    def jobs(self):
        with self.lock,self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]

    def job(self,jid):
        with self.lock,self.connect() as db:
            r=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            return dict(r) if r else None

    def staged_items(self):
        with self.lock,self.connect() as db:
            items=[]
            for row in db.execute('SELECT staged.*,jobs.report FROM staged LEFT JOIN jobs ON jobs.id=staged.job_id ORDER BY staged.created DESC'):
                item=dict(row);report=json.loads(item.pop('report') or '{}')
                item['resolved_textures']=report.get('resolved_textures')
                item['missing_dependencies']=len(report.get('missing_dependencies',[]))
                items.append(item)
            return items

    def stage_path(self,sid,filename):
        if not isinstance(sid,str) or not sid or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in sid):return None
        if filename not in ('package.oalmap','manifest.json','report.json','dependencies.json','preview.png'):return None
        with self.lock,self.connect() as db:
            if not db.execute('SELECT 1 FROM staged WHERE id=?',(sid,)).fetchone():return None
        p=self.staged/sid/filename
        return p if p.is_file() else None

    def _update(self,jid,state=None,line=None,report=None,stage_id=None,error=None):
        with self.lock,self.connect() as db:
            r=db.execute('SELECT log FROM jobs WHERE id=?',(jid,)).fetchone()
            if not r:return
            log=(r['log']+('\n'+line if line else ''))[-65536:]
            db.execute('UPDATE jobs SET state=coalesce(?,state), updated=?, log=?, report=coalesce(?,report),stage_id=coalesce(?,stage_id),error=coalesce(?,error) WHERE id=?',(state,time.time(),log,json.dumps(report,sort_keys=True) if report is not None else None,stage_id,error,jid))

    def _worker(self):
        while not self.stop.is_set():
            with self.lock,self.connect() as db:
                r=db.execute("SELECT id,source_id FROM jobs WHERE state='QUEUED' ORDER BY created LIMIT 1").fetchone()
                if r:db.execute("UPDATE jobs SET state='VALIDATING',updated=? WHERE id=?",(time.time(),r['id']))
            if r:
                try:self._run(r['id'],r['source_id'])
                except Exception as e:self._update(r['id'],'FAILED',f'Failed: {e}',error=str(e))
            else:self.stop.wait(0.3)

    def _run(self,jid,source_id):
        path=self.source_path(source_id)
        if not path:raise BSPError('source was removed after submission')
        self._update(jid,'VALIDATING',f'Validating {path.name}')
        bsp=SourceBSP(path)
        info=bsp.inspect()
        self._update(jid,'RESOLVING_DEPENDENCIES',f"BSP v{bsp.version}, {info['world_face_count']} world faces, {info['displacement_count']} displacements")
        self._update(jid,'IMPORTING','Reading Source geometry and entities')
        self._update(jid,'CONVERTING','Converting geometry, materials, and spawns')
        work=self.work/jid;work.mkdir(exist_ok=True)
        package=work/'package.oalmap'
        start=time.perf_counter()
        manifest,report=compile_map(path,package,self.material_roots,vpks=self.vpks)
        report['import_seconds']=round(time.perf_counter()-start,3)
        report['source_sha256']=manifest['source_sha256']
        self._update(jid,'COMPILING',f"Compiled {report['converted_triangles']} triangles and {report['converted_displacements']} displacements",report=report)
        self._update(jid,'VALIDATING_OUTPUT','Validating runtime package and Open Halo render/collision')
        if read_manifest(package)['source_sha256']!=manifest['source_sha256']:raise BSPError('package manifest mismatch')
        if not self.host_test or not self.host_test.is_file():raise BSPError('Open Halo host map test is not configured or built')
        env=os.environ.copy()
        if self.icd:env['VK_ICD_FILENAMES']=str(self.icd)
        cmd=[str(self.host_test),str(package),str(work/'preview')]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=180,env=env)
        report['open_halo_test_log']=(result.stdout+result.stderr)[-16000:]
        if result.returncode:raise BSPError(f'Open Halo map test failed (exit {result.returncode}): {result.stderr[-1000:]}')
        self._update(jid,line='Open Halo collision and Vulkan rendering passed')
        sid=f"{manifest['map_id']}-{manifest['source_sha256'][:12]}-{jid[:8]}"
        dst=self.staged/sid
        if dst.exists():raise BSPError('staging ID collision')
        dst.mkdir()
        shutil.move(str(package),str(dst/'package.oalmap'))
        with Image.open(work/'preview_spawn.ppm') as im:im.save(dst/'preview.png')
        for name,obj in (('manifest.json',manifest),('report.json',report),('dependencies.json',{'missing':manifest['missing_dependencies'],'static_prop_models':manifest['static_prop_models']})):
            (dst/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
        entry={'id':sid,'job_id':jid,'map_id':manifest['map_id'],'source_sha256':manifest['source_sha256'],'created':time.time(),'package_sha256':report['runtime_package_sha256']}
        with self.lock,self.connect() as db:
            db.execute('INSERT INTO staged VALUES (?,?,?,?,?,?)',tuple(entry.values()))
        (self.staged/'index.json').write_text(json.dumps(self.staged_items(),indent=2,sort_keys=True)+'\n')
        self._update(jid,'STAGED',f'Staged as {sid}',report=report,stage_id=sid)
        shutil.rmtree(work,ignore_errors=True)

    def close(self):
        self.stop.set();self.thread.join(timeout=2)
