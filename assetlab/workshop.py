"""Steam Workshop: search, fetch, understand and convert addons -- chiefly
Garry's Mod (app 4000), where most of the content lives.

The pipeline, each step usable alone:

    search   -> Workshop items (id, title, tags, size, preview, kind)
    fetch    -> the addon on disk: a direct download for legacy items that
                still carry a file URL, otherwise SteamCMD's anonymous
                `workshop_download_item`
    analyze  -> what is inside: playermodels (with the names and hands the
                addon registers in its own Lua), SWEPs (read into draft
                weapon definitions), maps, NPCs, props
    import   -> packages: characters, weapons and maps built with the addon
                itself mounted first on the search path, and a report of
                what was built, what failed and what is missing

Searching needs no key: Steam's public browse page gives item IDs in rank
order, and ISteamRemoteStorage/GetPublishedFileDetails (no key) gives the
metadata. With STEAM_WEB_API_KEY set, IPublishedFileService/QueryFiles is
used instead, which is faster and pages properly.

Nothing here decides what you may use. Workshop availability grants no
redistribution rights; downloads and packages stay in the private library.
"""
from __future__ import annotations

import ast
import html
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

GMOD_APPID = 4000
API = 'https://api.steampowered.com'
BROWSE = 'https://steamcommunity.com/workshop/browse/'
ITEM_URL = 'https://steamcommunity.com/sharedfiles/filedetails/?id={}'
STEAMCMD_URL = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz'
USER_AGENT = 'OpenAssetLab/0.2 (+local converter)'
MAX_DOWNLOAD = 1024 * 1024 * 1024

# Garry's Mod's own Workshop tags. The first group says what an addon IS,
# the second what it is like.
GMOD_TYPE_TAGS = ('Addon', 'Gamemode', 'Map', 'Weapon', 'Vehicle', 'NPC', 'Entity', 'Tool',
                  'Effects', 'Model', 'ServerContent', 'Save', 'Dupe', 'Demo')
GMOD_STYLE_TAGS = ('Fun', 'Roleplay', 'Scenic', 'Movie', 'Realism', 'Cartoon', 'Water', 'Comic', 'Build')
SORTS = {'relevance': 'textsearch', 'popular': 'trend', 'recent': 'mostrecent',
         'subscribed': 'totaluniquesubscribers', 'rated': 'toprated'}
# QueryFiles' query_type for each sort.
QUERY_TYPES = {'textsearch': 12, 'trend': 3, 'mostrecent': 1, 'totaluniquesubscribers': 9, 'toprated': 0}


class WorkshopError(ValueError):
    pass


# --------------------------------------------------------------------- http

class Http:
    """The smallest client that does the job, swappable in tests."""

    def __init__(self, timeout=30):
        self.timeout = timeout

    def _open(self, req):
        req.add_header('User-Agent', USER_AGENT)
        return urllib.request.urlopen(req, timeout=self.timeout)

    def get(self, url, params=None) -> bytes:
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params, doseq=True)
        with self._open(urllib.request.Request(url)) as r:
            return r.read(MAX_DOWNLOAD + 1)

    def post(self, url, data) -> bytes:
        body = urllib.parse.urlencode(data).encode()
        with self._open(urllib.request.Request(url, data=body, method='POST')) as r:
            return r.read(MAX_DOWNLOAD + 1)

    def download(self, url, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + '.part')
        with self._open(urllib.request.Request(url)) as r, tmp.open('wb') as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise WorkshopError('download exceeds 1 GiB')
                f.write(chunk)
        tmp.replace(dest)
        return dest


# ---------------------------------------------------------------------- ids

def parse_id(text) -> str:
    """An item ID from an ID, a Workshop URL or a steam:// link."""
    s = str(text).strip()
    if s.isdigit():
        return s
    m = re.search(r'[?&]id=(\d+)', s) or re.search(r'/(\d{6,})/?$', s)
    if not m:
        raise WorkshopError(f'not a Workshop item: {text!r}')
    return m.group(1)


def kind_from_tags(tags) -> str:
    """What the addon mostly is, for sorting and for what to build."""
    t = {x.lower() for x in tags}
    if 'map' in t:
        return 'map'
    if 'weapon' in t:
        return 'weapon'
    if 'model' in t or 'npc' in t:
        return 'character'
    if 'vehicle' in t:
        return 'vehicle'
    if t & {'entity', 'tool', 'effects'}:
        return 'entity'
    if 'gamemode' in t:
        return 'gamemode'
    return 'other'


def _item(d) -> dict:
    tags = [t.get('tag', '') for t in d.get('tags', []) if isinstance(t, dict)]
    desc = re.sub(r'\[/?[a-z0-9*]+(?:=[^\]]*)?\]', '', d.get('description', '') or '')
    return {
        'id': str(d.get('publishedfileid', '')),
        'ok': d.get('result', 1) == 1,
        'title': (d.get('title', '') or '').strip(),
        'description': html.unescape(desc).strip()[:600],
        'preview': d.get('preview_url', ''),
        'tags': tags,
        'kind': kind_from_tags(tags),
        'size': int(d.get('file_size') or 0),
        'subscriptions': int(d.get('lifetime_subscriptions') or d.get('subscriptions') or 0),
        'favorited': int(d.get('favorited') or 0),
        'created': int(d.get('time_created') or 0),
        'updated': int(d.get('time_updated') or 0),
        'file_url': d.get('file_url', '') or '',
        'filename': d.get('filename', '') or '',
        'creator': str(d.get('creator', '')),
        'app': int(d.get('consumer_app_id') or d.get('creator_app_id') or 0),
        'banned': bool(d.get('banned')),
        'url': ITEM_URL.format(d.get('publishedfileid', '')),
    }


class WorkshopAPI:
    def __init__(self, http=None, api_key=None, appid=GMOD_APPID, cache_seconds=600):
        self.http = http or Http()
        self.key = api_key if api_key is not None else os.environ.get('STEAM_WEB_API_KEY') or None
        self.appid = appid
        self.cache_seconds = cache_seconds
        self._cache = {}

    def _cached(self, key, fn):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < self.cache_seconds:
            return hit[1]
        v = fn()
        self._cache[key] = (time.time(), v)
        return v

    def details(self, ids) -> list[dict]:
        ids = [parse_id(i) for i in ids]
        if not ids:
            return []
        out = []
        for start in range(0, len(ids), 100):
            chunk = ids[start:start + 100]
            data = {'itemcount': len(chunk)}
            for i, x in enumerate(chunk):
                data[f'publishedfileids[{i}]'] = x
            raw = self._cached(('details', tuple(chunk)),
                               lambda: self.http.post(f'{API}/ISteamRemoteStorage/GetPublishedFileDetails/v1/', data))
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError as e:
                raise WorkshopError(f'Steam returned something that is not JSON: {e}') from e
            out += [_item(d) for d in doc.get('response', {}).get('publishedfiledetails', [])]
        return out

    def collection(self, cid, depth=3) -> list[str]:
        """The items a collection holds, in its order. A collection inside
        it (Steam's file type 2) is opened in turn, `depth` deep, each
        collection once; an item listed twice appears once."""
        seen, out, done = set(), [], set()

        def walk(c, d):
            if c in done:
                return
            done.add(c)
            raw = self.http.post(f'{API}/ISteamRemoteStorage/GetCollectionDetails/v1/',
                                 {'collectioncount': 1, 'publishedfileids[0]': c})
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError as e:
                raise WorkshopError(f'Steam returned something that is not JSON: {e}') from e
            for col in doc.get('response', {}).get('collectiondetails', []):
                for k in col.get('children', []):
                    kid = str(k.get('publishedfileid') or '')
                    if not kid.isdigit():
                        continue
                    if int(k.get('filetype') or 0) == 2:
                        if d > 1:
                            walk(kid, d - 1)
                    elif kid not in seen:
                        seen.add(kid)
                        out.append(kid)

        walk(parse_id(cid), max(1, depth))
        return out

    def search(self, text='', tags=(), page=1, sort='relevance', per_page=30) -> dict:
        """One page of results, in Steam's order."""
        sort = SORTS.get(sort, sort)
        if sort not in QUERY_TYPES:
            raise WorkshopError(f'unknown sort {sort!r} (use one of {", ".join(SORTS)})')
        page = max(1, int(page))
        tags = [t for t in tags if t]
        if self.key:
            return self._search_key(text, tags, page, sort, per_page)
        params = {'appid': self.appid, 'searchtext': text, 'browsesort': sort if text or sort != 'textsearch' else 'trend',
                  'section': 'readytouseitems', 'p': page, 'actualsort': sort, 'numperpage': per_page}
        if tags:
            params['requiredtags[]'] = tags
        page_html = self._cached(('browse', json.dumps(params, sort_keys=True)),
                                 lambda: self.http.get(BROWSE, params)).decode('utf-8', 'replace')
        ids = browse_ids(page_html)
        total = browse_total(page_html)
        items = self.details(ids) if ids else []
        return {'items': [i for i in items if i['ok']], 'page': page, 'total': total, 'source': 'browse'}

    def _search_key(self, text, tags, page, sort, per_page):
        params = {'key': self.key, 'appid': self.appid, 'query_type': QUERY_TYPES[sort], 'page': page,
                  'numperpage': per_page, 'search_text': text, 'return_tags': 1, 'return_previews': 1,
                  'return_short_description': 1, 'return_metadata': 1, 'match_all_tags': 1}
        for i, t in enumerate(tags):
            params[f'requiredtags[{i}]'] = t
        doc = json.loads(self.http.get(f'{API}/IPublishedFileService/QueryFiles/v1/', params))
        r = doc.get('response', {})
        items = [_item(d) for d in r.get('publishedfiledetails', []) or []]
        return {'items': [i for i in items if i['ok']], 'page': page, 'total': int(r.get('total', 0)), 'source': 'api'}


def browse_ids(page_html: str) -> list[str]:
    """Item IDs on a browse page, in rank order, once each.

    The current Workshop (2026) is a React page whose results arrive as
    escaped JSON in window.SSR -- `total_count` then `results: [{
    publishedfileid ...}]`. That is the data the page itself renders, so it
    is read first; its class names are build hashes and useless. The older
    page's `workshopItem` tiles come second, any filedetails link last."""
    m = re.search(r'total_count\W+\d+', page_html)
    if m:
        seg = page_html[m.end():]
        r = seg.find('results')
        if r >= 0:
            ids = []
            for k in re.finditer(r'(?<![a-z])publishedfileid\W+(\d+)', seg[r:]):
                if k.group(1) not in ids:
                    ids.append(k.group(1))
            if ids:
                return ids
    ids = []
    blocks = re.findall(r'class="workshopItem".*?</div>\s*</div>', page_html, re.S)
    for chunk in blocks or [page_html]:
        for k in re.finditer(r'sharedfiles/filedetails/\?id=(\d+)', chunk):
            if k.group(1) not in ids:
                ids.append(k.group(1))
    return ids


def browse_total(page_html: str) -> int:
    m = re.search(r'total_count\W+(\d+)', page_html)
    if m:
        return int(m.group(1))
    m = re.search(r'Showing\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)', page_html)
    return int(m.group(1).replace(',', '')) if m else 0


# ------------------------------------------------------------------- steamcmd

@dataclass
class SteamCMD:
    """Anonymous SteamCMD, which is how Garry's Mod items whose pages carry
    no file URL are fetched (the Workshop's UGC depot)."""
    root: Path
    runner: object = subprocess.run
    http: Http | None = None

    @property
    def binary(self) -> Path:
        return Path(self.root) / 'steamcmd.sh'

    def installed(self) -> bool:
        return self.binary.is_file()

    def install(self):
        """Fetches Valve's SteamCMD tarball into `root`."""
        root = Path(self.root)
        root.mkdir(parents=True, exist_ok=True)
        data = (self.http or Http(timeout=120)).get(STEAMCMD_URL)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
            for m in t.getmembers():
                p = PurePosixPath(m.name)
                if p.is_absolute() or '..' in p.parts or not (m.isfile() or m.isdir()):
                    raise WorkshopError(f'refusing tar member {m.name!r}')
            t.extractall(root)
        self.binary.chmod(0o755)

    def content_dir(self, appid, item) -> Path:
        # SteamCMD installs into its own tree unless told otherwise.
        return Path(self.root) / 'steamapps' / 'workshop' / 'content' / str(appid) / str(item)

    def download(self, item, appid=GMOD_APPID, timeout=1800) -> Path:
        if not self.installed():
            raise WorkshopError(f'SteamCMD is not installed at {self.root} '
                                '(pass --install-steamcmd, or install it and pass --steamcmd DIR)')
        cmd = [str(self.binary), '+force_install_dir', str(Path(self.root).resolve()), '+login', 'anonymous',
               '+workshop_download_item', str(appid), str(item), 'validate', '+quit']
        r = self.runner(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or '') + (r.stderr or '')
        ok, where, why = parse_steamcmd(out)
        if not ok:
            raise WorkshopError(f'SteamCMD could not download {item}: {why}')
        path = Path(where) if where else self.content_dir(appid, item)
        if not path.exists():
            raise WorkshopError(f'SteamCMD reported success but {path} is missing')
        return path


def parse_steamcmd(output: str):
    """(ok, path, reason) from SteamCMD's console output."""
    m = re.search(r'Success\. Downloaded item \d+ to "([^"]+)"', output)
    if m:
        return True, m.group(1), ''
    m = re.search(r'ERROR! Download item \d+ failed \(([^)]+)\)', output)
    if m:
        why = m.group(1)
        hints = {'Access Denied': 'the item is private, removed or needs a Steam account that owns Garry\'s Mod',
                 'Failure': 'Steam refused it (removed item, or a temporary Steam error; try again)',
                 'No Connection': 'Steam could not be reached', 'Timeout': 'Steam took too long'}
        return False, '', f'{why}: {hints.get(why, "see SteamCMD output")}'
    if 'cannot execute' in output or 'No such file or directory' in output and 'linux32' in output:
        return False, '', ('SteamCMD is a 32-bit program and this system lacks 32-bit libraries '
                           '(Debian/Ubuntu: sudo apt install lib32gcc-s1; Fedora: sudo dnf install glibc.i686 libstdc++.i686)')
    return False, '', (output.strip().splitlines() or ['no output'])[-1][:300]


def fetch(item: dict, dest: Path, steamcmd: SteamCMD | None, http: Http | None = None) -> Path:
    """The addon on disk: a file (.gma / _legacy.bin) or a folder."""
    dest = Path(dest)
    iid = item['id']
    if item.get('file_url'):
        name = item.get('filename') or f'{iid}_legacy.bin'
        name = PurePosixPath(name.replace('\\', '/')).name or f'{iid}_legacy.bin'
        out = dest / iid / name
        if not out.exists():
            (http or Http(timeout=300)).download(item['file_url'], out)
        return out
    if steamcmd is None:
        raise WorkshopError(f'{iid} has no direct download; SteamCMD is needed')
    got = steamcmd.download(iid, item.get('app') or GMOD_APPID)
    target = dest / iid
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(got, target)
    return target


# ------------------------------------------------------------------ analysis

def _strip_lua_comments(src: str) -> str:
    src = re.sub(r'--\[(=*)\[.*?\]\1\]', '', src, flags=re.S)
    return re.sub(r'--[^\n]*', '', src)


def _lua_value(expr: str):
    """A Lua scalar: a string, a number, or simple arithmetic (60/600)."""
    e = expr.strip().rstrip(',;').strip()
    m = re.fullmatch(r'''(?:Sound|Path)?\s*\(?\s*(["'])(.*?)\1\s*\)?''', e, re.S)
    if m:
        return m.group(2)
    if e in ('true', 'false'):
        return e == 'true'
    if re.fullmatch(r'[\d\s.+\-*/()]+', e):
        try:
            node = ast.parse(e, mode='eval')
            if all(isinstance(n, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.operator,
                                  ast.unaryop)) for n in ast.walk(node)):
                return float(eval(compile(node, '<lua>', 'eval'), {'__builtins__': {}}))
        except (SyntaxError, ZeroDivisionError, ValueError, TypeError):
            return None
    return None


def _braced(src: str, at: int) -> str:
    """The text inside the balanced { } starting at src[at] == '{'."""
    depth = 0
    for i in range(at, len(src)):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[at + 1:i]
    return src[at + 1:]


def parse_swep(src: str) -> dict:
    """The fields of a SWEP definition that matter for a draft: `SWEP.X = v`
    and `SWEP.Primary.X = v`, whichever base it is written for (the stock
    base, M9K, TFA, CW 2.0 and ArcCW all use these names)."""
    src = _strip_lua_comments(src)
    out = {}
    for m in re.finditer(r'^\s*SWEP\.([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\s*=\s*([^\n]+)', src, re.M):
        v = _lua_value(m.group(2))
        if v is not None:
            out[m.group(1)] = v
    # Tables: SWEP.Primary = { Damage = 10, ClipSize = 30 }
    for m in re.finditer(r'SWEP\.(Primary|Secondary)\s*=\s*\{(.*?)\}', src, re.S):
        for k in re.finditer(r'([A-Za-z_]\w*)\s*=\s*([^,\n}]+)', m.group(2)):
            v = _lua_value(k.group(2))
            if v is not None:
                out.setdefault(f'{m.group(1)}.{k.group(1)}', v)
    return out


def parse_sound_scripts(files: dict) -> dict:
    """Sound script names to their first wave: `sound.Add{...}` in Lua and
    scripts/*.txt KeyValues, both common in weapon packs."""
    sounds = {}
    for name, data in files.items():
        if name.endswith('.lua'):
            src = _strip_lua_comments(data.decode('utf-8', 'replace'))
            for m in re.finditer(r'sound\.Add\s*\(\s*\{(.*?)\}\s*\)', src, re.S):
                body = m.group(1)
                n = re.search(r'''name\s*=\s*(["'])(.+?)\1''', body)
                w = re.search(r'''sound\s*=\s*\{?\s*(["'])(.+?)\1''', body)
                if n and w:
                    sounds[n.group(2).lower()] = w.group(2)
        elif name.startswith('scripts/') and name.endswith('.txt'):
            src = data.decode('utf-8', 'replace')
            for m in re.finditer(r'"([^"]+)"\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', src, re.S):
                w = re.search(r'"wave"\s*"([^"]+)"', m.group(2))
                if w:
                    sounds[m.group(1).lower()] = w.group(1)
    return sounds


def _sound_path(ref, scripts: dict):
    if not ref or not isinstance(ref, str):
        return None
    wav = scripts.get(ref.lower(), ref)
    wav = wav.lstrip(')^*#@<>!?').replace('\\', '/')
    if not re.search(r'\.(wav|mp3|ogg)$', wav, re.I):
        return None
    return wav if wav.lower().startswith('sound/') else 'sound/' + wav


# Per-round damage that a damage_scale of 1.0 stands for, per base. OURS,
# from the hand-tuned definitions in data/weapons (AK-47 36 -> 1.6 on the
# assault rifle; .357 75 -> 1.6 on the pistol).
DAMAGE_REF = {'assault rifle': 22.0, 'pistol': 47.0, 'shotgun': 9.0, 'sniper rifle': 70.0,
              'rocket launcher': 120.0, 'plasma rifle': 22.0}
RELOAD_DEFAULT = {'assault rifle': 2.4, 'pistol': 1.8, 'shotgun': 3.5, 'sniper rifle': 3.0,
                  'rocket launcher': 3.5}
MELEE_HOLDS = {'melee', 'melee2', 'knife', 'fist', 'normal'}


def draft_weapon(cls: str, swep: dict, scripts: dict, source: str) -> dict:
    """A weapon definition (the data/weapons format) from what a SWEP says
    about itself. Marked as drafted: review the numbers before shipping."""
    hold = str(swep.get('HoldType', 'ar2')).lower()
    dmg = swep.get('Primary.Damage')
    clip = swep.get('Primary.ClipSize')
    shots = swep.get('Primary.NumShots') or swep.get('Primary.NumBullets') or 1
    rpm = swep.get('Primary.RPM')
    delay = swep.get('Primary.Delay')
    rps = (rpm / 60.0) if isinstance(rpm, float) and rpm > 0 else (1.0 / delay) if isinstance(delay, float) and delay > 0 else None
    melee = hold in MELEE_HOLDS and (not isinstance(clip, float) or clip <= 0)
    if melee:
        base = 'pistol'
    elif isinstance(shots, float) and shots > 1:
        base = 'shotgun'
    elif hold == 'rpg':
        base = 'rocket launcher'
    elif hold == 'crossbow' or (isinstance(dmg, float) and dmg >= 60 and (rps or 1) <= 1.5 and hold in ('ar2', 'smg', 'crossbow')):
        base = 'sniper rifle'
    elif hold in ('pistol', 'revolver', 'duel'):
        base = 'pistol'
    else:
        base = 'assault rifle'
    stats = {}
    if rps:
        stats['rounds_per_second'] = round(min(max(rps, 0.2), 20.0), 2)
    if not melee and isinstance(clip, float) and clip > 0:
        stats['magazine'] = int(clip)
        dc = swep.get('Primary.DefaultClip')
        stats['reserve'] = int(dc) if isinstance(dc, float) and dc > clip else int(clip) * 3
        stats['reload_seconds'] = RELOAD_DEFAULT.get(base, 2.5)
    if isinstance(dmg, float) and dmg > 0:
        ref = 30.0 if melee else DAMAGE_REF.get(base, 25.0)
        stats['damage_scale'] = round(min(max(dmg / ref, 0.2), 6.0), 2)
    cone = swep.get('Primary.Cone', swep.get('Primary.Spread'))
    if isinstance(cone, float) and cone > 0 and not melee:
        stats['spread_scale'] = round(min(max(cone / 0.02, 0.3), 3.0), 2)
    if melee:
        stats.setdefault('rounds_per_second', 2.0)
        stats['knockback'] = 4.0
    sounds = {}
    fire = _sound_path(swep.get('Primary.Sound'), scripts)
    if fire:
        sounds['fire'] = fire
    rel = _sound_path(swep.get('ReloadSound') or swep.get('Primary.ReloadSound'), scripts)
    if rel:
        sounds['reload'] = rel
    name = re.sub(r'[^a-z0-9_]+', '_', cls.lower()).strip('_') or 'weapon'
    d = {
        'name': name,
        'display_name': str(swep.get('PrintName') or cls),
        'base': base,
        'world_model': str(swep.get('WorldModel') or 'none').replace('\\', '/').lower(),
        'view_model': str(swep.get('ViewModel') or '').replace('\\', '/').lower(),
        'stats': stats,
        'sounds': sounds,
        'view_model_mirrored': bool(swep.get('ViewModelFlip', False)),
        'crosshair': 'dot' if melee else 'arms+dot',
        'crosshair_size': 12 if melee else 22,
        'hold_type': hold,
        'auto_drafted': True,
        'stats_provenance': (f'Drafted by assetlab workshop from {source}: '
                             + ', '.join(f'{k}={swep[k]:g}' if isinstance(swep[k], float) else f'{k}={swep[k]}'
                                         for k in ('Primary.Damage', 'Primary.RPM', 'Primary.Delay', 'Primary.ClipSize',
                                                   'Primary.NumShots', 'HoldType', 'Base') if k in swep)
                             + '. Review before shipping.'),
    }
    if melee:
        d['melee'] = True
    return d


@dataclass
class Analysis:
    name: str = ''
    author: str = ''
    files: int = 0
    characters: list = field(default_factory=list)   # {model, display, hands}
    weapons: list = field(default_factory=list)      # draft definitions
    maps: list = field(default_factory=list)         # maps/*.bsp
    npcs: list = field(default_factory=list)         # {class, display, model}
    props: int = 0
    materials: int = 0
    sounds: int = 0
    lua: int = 0
    warnings: list = field(default_factory=list)

    def to_json(self):
        return dict(self.__dict__)

    def buildable(self):
        return len(self.characters) + len(self.weapons) + len(self.maps)


def _files_of(path: Path) -> tuple[dict, str, str]:
    """{lowercase posix name: bytes} of an addon, and its name and author."""
    from .importers.gma import GMA, load
    path = Path(path)
    if path.is_dir():
        archives = sorted([*path.glob('*.gma'), *path.glob('*_legacy.bin')])
        if archives:
            return _files_of(archives[0])
        files = {}
        for p in sorted(path.rglob('*')):
            if p.is_file() and not p.is_symlink():
                rel = p.relative_to(path).as_posix().lower()
                if p.stat().st_size <= 256 * 1024 * 1024:
                    files[rel] = p.read_bytes() if rel.endswith(('.lua', '.txt', '.json')) else b''
        return files, path.name, ''
    g = GMA(load(path))
    files = {n: (g.read(n) if n.endswith(('.lua', '.txt', '.json')) else b'') for n in g.files}
    return files, g.name, g.author


def analyze(path) -> Analysis:
    files, name, author = _files_of(path)
    a = Analysis(name=name, author=author, files=len(files))
    a.lua = sum(n.endswith('.lua') for n in files)
    a.materials = sum(n.startswith('materials/') for n in files)
    a.sounds = sum(n.startswith('sound/') for n in files)
    mdls = sorted(n for n in files if n.endswith('.mdl'))
    lua = {n: d.decode('utf-8', 'replace') for n, d in files.items() if n.endswith('.lua')}

    # Playermodels, by the addon's own registration.
    reg, hands = {}, {}
    for n, src in lua.items():
        src = _strip_lua_comments(src)
        for m in re.finditer(r'''player_manager\.AddValidModel\s*\(\s*(["'])(.+?)\1\s*,\s*(["'])(.+?)\3''', src):
            reg[m.group(4).replace('\\', '/').lower()] = m.group(2)
        for m in re.finditer(r'''list\.Set\s*\(\s*["']PlayerOptionsModel["']\s*,\s*(["'])(.+?)\1\s*,\s*(["'])(.+?)\3''', src):
            reg.setdefault(m.group(4).replace('\\', '/').lower(), m.group(2))
        for m in re.finditer(r'''player_manager\.AddValidHands\s*\(\s*(["'])(.+?)\1\s*,\s*(["'])(.+?)\3''', src):
            hands[m.group(2)] = m.group(4).replace('\\', '/').lower()
        # NPCs: list.Set("NPC", id, { ... }) or a local table passed by name.
        tables = {}
        for m in re.finditer(r'(?:local\s+)?([A-Za-z_]\w*)\s*=\s*\{', src):
            tables[m.group(1)] = _braced(src, m.end() - 1)
        for m in re.finditer(r'''list\.Set\s*\(\s*["']NPC["']\s*,\s*(["'])(.+?)\1\s*,\s*''', src):
            rest = src[m.end():]
            if rest.startswith('{'):
                body = _braced(rest, 0)
            else:
                v = re.match(r'([A-Za-z_]\w*)', rest)
                body = tables.get(v.group(1), '') if v else ''
            dn = re.search(r'''Name\s*=\s*(["'])(.+?)\1''', body)
            md = re.search(r'''Model\s*=\s*(["'])(.+?)\1''', body)
            a.npcs.append({'class': m.group(2), 'display': dn.group(2) if dn else m.group(2),
                           'model': md.group(2).replace('\\', '/').lower() if md else None})
    # An addon that registers a playermodel and an NPC of it ships the NPC as
    # a second copy; that is not another character.
    npc_models = {n['model'] for n in a.npcs if n.get('model')}
    seen = set(npc_models) if reg else set()
    for model, display in sorted(reg.items()):
        if model not in files:
            a.warnings.append(f'{display}: registers {model}, which is not in this addon (needs another addon)')
        seen.add(model)
        a.characters.append({'model': model, 'display': display, 'hands': hands.get(display)})
    # Unregistered playermodels (packs that rely on the folder name).
    for model in mdls:
        if model in seen:
            continue
        if model.startswith('models/player/') or '/playermodel' in model or '/pm_' in model:
            if re.search(r'(_arms|c_arms|/v_|/w_|_hands)', model):
                continue
            a.characters.append({'model': model, 'display': PurePosixPath(model).stem.replace('_', ' ').title(),
                                 'hands': None})
    for npc in a.npcs if not reg else ():
        m = npc.get('model')
        if m and m in files and m not in {c['model'] for c in a.characters}:
            a.characters.append({'model': m, 'display': npc['display'], 'hands': None, 'npc': True})

    # SWEPs: lua/weapons/<class>/shared.lua or lua/weapons/<class>.lua.
    scripts = parse_sound_scripts({n: files[n] for n in files if n.endswith('.lua') or n.startswith('scripts/')})
    classes = {}
    for n, src in lua.items():
        m = re.fullmatch(r'lua/weapons/([^/]+)/(shared|init|cl_init)\.lua', n) or re.fullmatch(r'lua/weapons/([^/]+)\.lua', n)
        if not m:
            continue
        cls = m.group(1)
        prev = classes.get(cls, {})
        prev.update({k: v for k, v in parse_swep(src).items() if k not in prev})
        classes[cls] = prev
        classes[cls].setdefault('_source', n)
    for cls, swep in sorted(classes.items()):
        if not swep.get('ViewModel') and not swep.get('WorldModel'):
            continue
        # Bases (M9K's bobs_*, TFA's, CW's) are code other weapons build on.
        if cls.endswith('_base') or cls.startswith('bobs_') or (
                swep.get('Spawnable') is False and swep.get('AdminSpawnable') is not True and
                swep.get('AdminOnly') is not True):
            continue
        hold = str(swep.get('HoldType', '')).lower()
        if hold in ('grenade', 'slam', 'physgun', 'camera', 'magic'):
            a.warnings.append(f'{cls}: a {hold} weapon; the game has no base to build it on (skipped)')
            continue
        d = draft_weapon(cls, swep, scripts, swep.get('_source', cls))
        for key in ('view_model', 'world_model'):
            if d[key] not in ('', 'none') and d[key] not in files:
                d.setdefault('needs', []).append(d[key])
        a.weapons.append(d)

    a.maps = sorted(n for n in files if n.startswith('maps/') and n.endswith('.bsp'))
    a.props = sum(1 for n in mdls if n.startswith('models/props') or '/props/' in n)
    if not a.buildable():
        a.warnings.append('nothing buildable found: no playermodels, SWEPs with models, or maps')
    return a


# -------------------------------------------------------------------- import

def extract(path: Path, dest: Path) -> Path:
    """The addon's files on disk, laid out as a game directory."""
    from .importers.gma import GMA, load
    path = Path(path)
    if path.is_dir():
        archives = sorted([*path.glob('*.gma'), *path.glob('*_legacy.bin')])
        if not archives:
            return path
        path = archives[0]
    dest = Path(dest)
    if not dest.exists():
        GMA(load(path)).extract(dest)
    return dest


def import_addon(analysis: Analysis, root: Path, out_dir: Path, game_dirs=(), vpks=(),
                 kinds=('characters', 'weapons', 'maps'), builders=None, pick=None) -> dict:
    """Build every candidate of the chosen kinds. `root` is the extracted
    addon (mounted first); `game_dirs` are Garry's Mod's own (garrysmod,
    sourceengine) and any content the addon depends on. Failures are
    recorded, not raised: one broken model must not lose the rest."""
    from .report import game_dir_search
    if builders is None:
        from .character import build_character, build_weapon
        from .package import compile_map
        builders = {'character': build_character, 'weapon': build_weapon, 'map': compile_map}
    roots, found_vpks = game_dir_search([str(root), *map(str, game_dirs)])
    vpks = [*vpks, *found_vpks]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    built, failed = [], []

    def slug(s):
        return re.sub(r'[^a-z0-9_-]+', '_', s.lower()).strip('_')[:60] or 'item'

    def chosen(label):
        return pick is None or any(p.lower() in label.lower() for p in pick)

    if 'characters' in kinds:
        for c in analysis.characters:
            if not chosen(c['display'] + ' ' + c['model']):
                continue
            out = out_dir / f"{slug(c['display'])}.oalasset"
            try:
                m = builders['character'](c['model'], str(out), roots, vpks, name=slug(c['display']),
                                          display=c['display'].upper())
                built.append({'kind': 'character', 'name': c['display'], 'package': out.name,
                              'missing': m.get('missing_dependencies', []) if isinstance(m, dict) else []})
            except Exception as e:  # noqa: BLE001 -- recorded per item
                err = str(e)[:400]
                if 'no animation' in err:
                    err += (' -- Garry\'s Mod playermodels take their animations from the game: mount its '
                            'garrysmod and sourceengine folders with --game-dir (in that order)')
                failed.append({'kind': 'character', 'name': c['display'], 'error': err})
    if 'weapons' in kinds:
        for d in analysis.weapons:
            if not chosen(d['display_name'] + ' ' + d['name']):
                continue
            out = out_dir / f"{d['name']}.oalasset"
            (out_dir / f"{d['name']}.json").write_text(json.dumps(d, indent=2) + '\n')
            try:
                spec = {k: v for k, v in d.items() if k != 'needs'}
                m = builders['weapon'](spec, str(out), roots, vpks)
                built.append({'kind': 'weapon', 'name': d['display_name'], 'package': out.name,
                              'definition': f"{d['name']}.json",
                              'missing': m.get('missing_dependencies', []) if isinstance(m, dict) else []})
            except Exception as e:  # noqa: BLE001
                failed.append({'kind': 'weapon', 'name': d['display_name'], 'error': str(e)[:400],
                               'definition': f"{d['name']}.json"})
    if 'maps' in kinds:
        for bsp in analysis.maps:
            if not chosen(bsp):
                continue
            src = Path(root) / bsp
            out = out_dir / f"{PurePosixPath(bsp).stem}.oalmap"
            try:
                m, r = builders['map'](str(src), str(out), roots, vpks=vpks)
                built.append({'kind': 'map', 'name': PurePosixPath(bsp).stem, 'package': out.name,
                              'missing': (m or {}).get('missing_dependencies', [])})
            except Exception as e:  # noqa: BLE001
                failed.append({'kind': 'map', 'name': bsp, 'error': str(e)[:400]})
    return {'addon': analysis.name, 'built': built, 'failed': failed,
            'search_path': [str(root), *map(str, game_dirs)]}
