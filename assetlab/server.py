"""Standard-library HTTP UI with no login. Bind localhost unless --tailscale is explicit;
the private tailnet is the access boundary."""
from __future__ import annotations
import json
import os
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .library import Library
from .importers.source_bsp import SourceBSP,BSPError

MAX_UPLOAD=128*1024*1024
HTML=r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Open Asset Lab</title>
<style>body{font:16px system-ui;background:#121924;color:#ecf3fc;margin:0 auto;max-width:900px;padding:1.5rem}h1{color:#8dd6ff}section{background:#202b3b;border-radius:8px;padding:1rem;margin:1rem 0}button,input{font:inherit;padding:.5rem;margin:.2rem}button{background:#6bbbf0;border:0;border-radius:5px;cursor:pointer}li{margin:.5rem 0}small{color:#b5c4d4}pre{white-space:pre-wrap;overflow:auto;background:#0c1220;padding:1rem}a{color:#8dd6ff}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.6rem}.card{background:#121924;border-radius:6px;padding:.4rem;font-size:.85rem}.card img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:4px;background:#0c1220}.card button{width:100%;margin:.3rem 0 0}.kind{color:#ffcf6b}select{font:inherit;padding:.5rem;margin:.2rem}</style>
<h1>Open Asset Lab</h1><p id="status">Connecting…</p><section><h2>Registered maps</h2><ul id="sources"></ul><label>Upload Source BSP <input type="file" id="file" accept=".bsp"></label><button onclick="upload()">Upload</button></section>
<section id="ws"><h2>Steam Workshop</h2><p><small>Garry's Mod addons: search, then Import builds characters, weapons and maps from them. Your downloads and packages stay on this machine.</small></p>
<form onsubmit="wsSearch(1);return false"><input id="wq" placeholder="Search (e.g. superman, ak47, gm_)" size="28"><select id="wtag"><option value="">Any type</option><option>Model</option><option>Weapon</option><option>Map</option><option>NPC</option><option>Vehicle</option></select><select id="wsort"><option value="relevance">Relevance</option><option value="popular">Popular now</option><option value="subscribed">Most subscribed</option><option value="recent">Newest</option></select><button>Search</button></form>
<form onsubmit="wsImport(document.getElementById('wid').value);return false"><input id="wid" placeholder="…or a Workshop ID / URL" size="28"><button>Import</button></form>
<p id="wstatus"></p><div id="wresults" class="grid"></div><p id="wpager"></p><h3>Imports</h3><ul id="wjobs"></ul><div id="wdetail"></div></section>
<section><h2>Jobs</h2><ul id="jobs"></ul><div id="detail"></div></section><section><h2>Staged maps</h2><ul id="staged"></ul></section>
<script>
const H={'X-OAL-Request':'1'};async function api(path,options={}){let r=await fetch('/api/'+path,{...options,headers:{...H,...options.headers}});if(!r.ok)throw new Error(await r.text());return r.json()}
async function refresh(){try{let [st,src,job,stage]=await Promise.all(['status','sources','jobs','staged'].map(x=>api(x)));document.getElementById('status').textContent=`${st.service} · ${st.active_jobs} active · ${st.staged_maps} staged`;
let a=document.getElementById('sources');a.replaceChildren();for(let s of src){let li=document.createElement('li');li.textContent=`${s.name} (${(s.bytes/1048576).toFixed(1)} MiB, ${s.source}) `;let b=document.createElement('button');b.textContent='Convert';b.onclick=async()=>{await api('jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:s.id})});refresh()};li.append(b);a.append(li)}
let j=document.getElementById('jobs');j.replaceChildren();for(let x of job){let li=document.createElement('li'),b=document.createElement('button');b.textContent=`${x.source_name}: ${x.state}`;b.onclick=()=>detail(x.id);li.append(b);j.append(li)}
let q=document.getElementById('staged');q.replaceChildren();for(let x of stage){let li=document.createElement('li');let a=document.createElement('a');a.href='/api/staged/'+x.id+'/preview.png';a.textContent=x.map_id+' preview';li.append(a);let note=document.createElement('small');note.textContent=` · ${x.resolved_textures??'?'} textures resolved · ${x.missing_dependencies??'?'} dependencies missing`;li.append(note);for(let f of ['package.oalmap','compatibility.md','report.json','manifest.json','dependencies.json']){let z=document.createElement('a');z.href='/api/staged/'+x.id+'/'+f;z.textContent=' · '+f;li.append(z)}q.append(li)}}catch(e){document.getElementById('status').textContent=e.message}}
async function detail(id){let x=await api('jobs/'+id);let d=document.getElementById('detail');d.replaceChildren();let h=document.createElement('h3');h.textContent=x.source_name+' · '+x.state;d.append(h);let p=document.createElement('pre');p.textContent=x.log+(x.error?'\nERROR: '+x.error:'')+'\n'+(x.report||'');d.append(p)}
async function upload(){let f=document.getElementById('file').files[0];if(!f)return alert('Select a BSP');if(f.size>134217728)return alert('128 MiB upload limit');let r=await fetch('/api/upload/'+encodeURIComponent(f.name),{method:'PUT',headers:H,body:f});if(!r.ok)alert(await r.text());refresh()}
let wpage=1;function el(t,txt){let e=document.createElement(t);if(txt!==undefined)e.textContent=txt;return e}
async function wsSearch(p){wpage=p;let q=document.getElementById('wq').value,t=document.getElementById('wtag').value,so=document.getElementById('wsort').value;let st=document.getElementById('wstatus');st.textContent='Searching…';try{let r=await api('workshop/search?'+new URLSearchParams({q:q,tag:t,sort:so,page:p}));st.textContent=`${r.total} results · page ${r.page}`;let g=document.getElementById('wresults');g.replaceChildren();for(let i of r.items){let c=el('div');c.className='card';let im=el('img');im.loading='lazy';im.alt='';im.onerror=()=>{im.style.visibility='hidden'};if(i.preview)im.src=i.preview+(i.preview.includes('?')?'&':'?')+'imw=256&imh=256&ima=fit';c.append(im);let a=el('a',i.title);a.href=i.url;a.target='_blank';a.rel='noopener';let t=el('div');t.append(a);c.append(t);let k=el('div',`${i.kind} · ${(i.size/1048576).toFixed(1)} MB · ${i.subscriptions.toLocaleString()} subs`);k.className='kind';c.append(k);let b=el('button','Import');b.onclick=()=>wsImport(i.id,i.title);c.append(b);g.append(c)}let pg=document.getElementById('wpager');pg.replaceChildren();if(p>1){let b=el('button','◀ Prev');b.onclick=()=>wsSearch(p-1);pg.append(b)}if(r.items.length){let b=el('button','Next ▶');b.onclick=()=>wsSearch(p+1);pg.append(b)}}catch(e){st.textContent=e.message}}
async function wsImport(id,title){if(!id)return;try{await api('workshop/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:String(id)})});document.getElementById('wstatus').textContent=`Queued ${title||id}`;wsJobs()}catch(e){alert(e.message)}}
async function wsJobs(){try{let js=await api('workshop/jobs');let u=document.getElementById('wjobs');u.replaceChildren();for(let j of js){let li=el('li');let b=el('button',`${j.title}: ${j.state}`);b.onclick=()=>wsDetail(j.id);li.append(b);for(let x of j.built||[]){let a=el('a',` · ${x.kind} ${x.name}`);a.href=`/api/workshop/jobs/${j.id}/${x.package}`;li.append(a);if(x.preview){let p=el('a',' (preview)');p.href=`/api/workshop/jobs/${j.id}/${x.preview}`;li.append(p)}}if((j.failed||[]).length)li.append(el('small',` · ${j.failed.length} failed`));u.append(li)}}catch(e){}}
async function wsDetail(id){let x=await api('workshop/jobs/'+id);let d=document.getElementById('wdetail');d.replaceChildren();d.append(el('h3',x.title+' · '+x.state));let p=el('pre');p.textContent=x.log+(x.error?'\nERROR: '+x.error:'')+(x.report?'\n'+JSON.stringify({built:x.report.built,failed:x.report.failed},null,1):'');d.append(p);for(let f of ['report.json','analysis.json']){let a=el('a',' '+f);a.href=`/api/workshop/jobs/${id}/${f}`;d.append(a)}}
refresh();setInterval(refresh,3000);if(document.getElementById('ws'))setInterval(wsJobs,3000);
</script></html>'''


def serve(library,host='127.0.0.1',port=8762,workshop=None):
    class Handler(BaseHTTPRequestHandler):
        server_version='OpenAssetLab/0.1'
        def _pre(self,mutate=False):
            if mutate and self.headers.get('X-OAL-Request')!='1':self._error(403,'missing request header');return False
            origin=self.headers.get('Origin')
            if mutate and origin and origin not in (f'http://{self.headers.get("Host")}',f'https://{self.headers.get("Host")}'):
                self._error(403,'invalid origin');return False
            return True
        def _send(self,code,data,kind='application/json'):
            if isinstance(data,(dict,list)):data=json.dumps(data).encode()
            elif isinstance(data,str):data=data.encode()
            self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self' 'unsafe-inline'; img-src 'self' https://images.steamusercontent.com https://steamuserimages-a.akamaihd.net; object-src 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(data)
        def _error(self,code,msg):self._send(code,{'error':msg})
        def do_GET(self):
            if not self._pre():return
            path=urlsplit(self.path).path
            if path=='/':return self._send(200,HTML,'text/html; charset=utf-8')
            if path=='/api/status':
                jobs=library.jobs();return self._send(200,{'service':'running','active_jobs':sum(j['state'] not in ('STAGED','FAILED') for j in jobs),'staged_maps':len(library.staged_items()),'host_test':str(library.host_test) if library.host_test else None})
            if path=='/api/sources':return self._send(200,library.sources())
            if path=='/api/jobs':return self._send(200,library.jobs())
            if path=='/api/staged':return self._send(200,library.staged_items())
            if path.startswith('/api/workshop/'):
                return self._workshop_get(path)
            m=re.fullmatch(r'/api/jobs/([0-9a-f]{32})',path)
            if m:
                j=library.job(m[1]);return self._send(200,j) if j else self._error(404,'job not found')
            m=re.fullmatch(r'/api/staged/([a-z0-9_-]+)/([a-z0-9_.]+)',path)
            if m:
                p=library.stage_path(m[1],m[2])
                if not p:return self._error(404,'artifact not found')
                kind='image/png' if p.suffix=='.png' else 'application/json' if p.suffix=='.json' else 'text/plain; charset=utf-8' if p.suffix=='.md' else 'application/octet-stream'
                return self._send(200,p.read_bytes(),kind)
            self._error(404,'not found')
        def _workshop_get(self,path):
            from urllib.parse import parse_qs
            if not workshop:return self._error(404,'the Workshop is not enabled on this server')
            from .workshop import WorkshopError
            try:
                if path=='/api/workshop/search':
                    q=parse_qs(urlsplit(self.path).query)
                    one=lambda k,d='':(q.get(k) or [d])[0][:200]
                    page=int(one('page','1')) if one('page','1').isdigit() else 1
                    return self._send(200,workshop.api.search(one('q'),[one('tag')] if one('tag') else [],max(1,min(page,200)),one('sort','relevance')))
                if path=='/api/workshop/jobs':return self._send(200,workshop.jobs())
                m=re.fullmatch(r'/api/workshop/jobs/([0-9a-f]{32})',path)
                if m:
                    j=workshop.job(m[1]);return self._send(200,j) if j else self._error(404,'job not found')
                m=re.fullmatch(r'/api/workshop/jobs/([0-9a-f]{32})/([^/]+)',path)
                if m:
                    p=workshop.artifact(m[1],m[2])
                    if not p:return self._error(404,'artifact not found')
                    kind='image/png' if p.suffix=='.png' else 'application/json' if p.suffix=='.json' else 'application/octet-stream'
                    return self._send(200,p.read_bytes(),kind)
                m=re.fullmatch(r'/api/workshop/item/(\d{1,20})',path)
                if m:return self._send(200,workshop.api.details([m[1]]))
            except (WorkshopError,ValueError) as e:return self._error(400,str(e))
            except OSError as e:return self._error(502,f'Steam could not be reached: {e}')
            self._error(404,'not found')
        def do_POST(self):
            if not self._pre(True):return
            if urlsplit(self.path).path=='/api/workshop/import':
                if not workshop:return self._error(404,'the Workshop is not enabled on this server')
                try:
                    n=int(self.headers.get('Content-Length','0'))
                    if n<1 or n>2048:raise ValueError('invalid request size')
                    body=json.loads(self.rfile.read(n))
                    if not isinstance(body,dict) or 'id' not in body or set(body)-{'id','kinds'}:raise ValueError('invalid request fields')
                    kinds=body.get('kinds') or ['characters','weapons','maps']
                    if not isinstance(kinds,list):raise ValueError('kinds must be a list')
                    return self._send(202,{'job_id':workshop.submit(str(body['id']),kinds)})
                except (ValueError,TypeError,json.JSONDecodeError) as e:return self._error(400,str(e))
            if urlsplit(self.path).path!='/api/jobs':return self._error(404,'not found')
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n<1 or n>2048:raise ValueError('invalid request size')
                body=json.loads(self.rfile.read(n))
                if set(body)!={'source_id'}:raise ValueError('invalid request fields')
                jid=library.submit(body['source_id'])
                self._send(202,{'job_id':jid})
            except (ValueError,TypeError,json.JSONDecodeError) as e:self._error(400,str(e))
        def do_PUT(self):
            if not self._pre(True):return
            path=urlsplit(self.path).path
            m=re.fullmatch(r'/api/upload/([A-Za-z0-9_.-]{1,100}\.bsp)',path,re.I)
            if not m or m[1].startswith('.'):return self._error(400,'invalid BSP filename')
            try:n=int(self.headers.get('Content-Length','0'))
            except ValueError:return self._error(400,'invalid upload size')
            if n<1036 or n>MAX_UPLOAD:return self._error(413,'upload must be between 1036 bytes and 128 MiB')
            if sum(p.stat().st_size for p in library.uploads.glob('*.bsp'))+n>2*1024*1024*1024:return self._error(413,'upload library limit reached')
            name=m[1];dest=library.uploads/name
            if dest.exists():return self._error(409,'upload name already exists')
            tmp=library.uploads/('.upload-'+secrets.token_hex(12))
            try:
                with tmp.open('xb') as f:
                    remaining=n
                    while remaining:
                        chunk=self.rfile.read(min(1024*1024,remaining))
                        if not chunk:raise ValueError('truncated upload')
                        f.write(chunk);remaining-=len(chunk)
                if tmp.open('rb').read(4)!=b'VBSP':raise ValueError('not a Source BSP')
                SourceBSP(tmp)
                os.link(tmp,dest)
                self._send(201,{'name':name,'bytes':n})
            except (ValueError,BSPError,FileExistsError) as e:self._error(400,str(e))
            finally:tmp.unlink(missing_ok=True)
        def log_message(self,fmt,*args):
            print(f'HTTP {self.address_string()} {fmt%args}',flush=True)
    http=ThreadingHTTPServer((host,port),Handler)
    print(f'Open Asset Lab listening on http://{host}:{port}',flush=True)
    try:http.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:pass
    finally:
        http.server_close();library.close()
        if workshop:workshop.close()
