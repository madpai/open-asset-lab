"""Animated Source studio models: skeleton, skin weights, attachments,
sequences and their compressed animation, sampled into plain per-frame
bone transforms. mstudioseqdesc_t: animindexindex +60, groupsize +68,
paramindex +76, paramstart +84, paramend +92, weightlistindex +156.

Layouts: Valve source-sdk-2013 public/studio.h (MDL v44-v48; mstudiobone_t
216 bytes, mstudioattachment_t 92, mstudioanimdesc_t 100, mstudioseqdesc_t
212, mstudioposeparamdesc_t 20, mstudioanim_t with RLE mstudioanimvalue_t)
and bone_setup.cpp (CalcBoneQuaternion/CalcBonePosition, ExtractAnimValue).
Nothing here knows any particular model: which sequences make which clip
is the translation registry's job.
"""
from __future__ import annotations
import math
import struct
from .source_bsp import BSPError
from .source_mdl import vtx_strip_group_stride

MAX_MODEL = 64 * 1024 * 1024
STUDIO_DELTA = 0x0004          # sequence/animdesc flag: additive
ANIM_RAWPOS, ANIM_RAWROT, ANIM_ANIMPOS, ANIM_ANIMROT, ANIM_DELTA, ANIM_RAWROT2 = 1, 2, 4, 8, 16, 32


def _u(fmt, data, off):
    size = struct.calcsize(fmt)
    if off < 0 or off + size > len(data):
        raise BSPError(f"model read outside file at {off}")
    return struct.unpack_from(fmt, data, off)


def _cstr(data, off):
    if off < 0 or off >= len(data):
        raise BSPError("model string outside file")
    end = data.find(b"\0", off)
    return data[off:end if end >= 0 else len(data)].decode("utf-8", "replace")


# ---- quaternion helpers (x, y, z, w) -----------------------------------------------

def q_mul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by, aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw, aw*bw - ax*bx - ay*by - az*bz)


def q_norm(q):
    n = math.sqrt(sum(c*c for c in q)) or 1.0
    return tuple(c/n for c in q)


def q_slerp(a, b, t):
    d = sum(x*y for x, y in zip(a, b))
    if d < 0:
        b = tuple(-c for c in b); d = -d
    if d > 0.9995:
        return q_norm(tuple(x + (y-x)*t for x, y in zip(a, b)))
    th = math.acos(max(-1.0, min(1.0, d)))
    s = math.sin(th)
    wa, wb = math.sin((1-t)*th)/s, math.sin(t*th)/s
    return tuple(wa*x + wb*y for x, y in zip(a, b))


def euler_to_quat(x, y, z):
    """Valve AngleQuaternion(RadianEuler)."""
    sy, cy = math.sin(z*.5), math.cos(z*.5)
    sp, cp = math.sin(y*.5), math.cos(y*.5)
    sr, cr = math.sin(x*.5), math.cos(x*.5)
    return (sr*cp*cy - cr*sp*sy, cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy, cr*cp*cy + sr*sp*sy)


def quat48(d, o):
    x, y, zw = _u('<HHH', d, o)
    qx = (x - 32768) / 32768.0; qy = (y - 32768) / 32768.0; qz = ((zw & 0x7fff) - 16384) / 16384.0
    w = math.sqrt(max(0.0, 1.0 - qx*qx - qy*qy - qz*qz))
    return (qx, qy, qz, -w if zw & 0x8000 else w)


def quat64(d, o):
    v = _u('<Q', d, o)[0]
    x = (v & 0x1fffff); y = (v >> 21) & 0x1fffff; z = (v >> 42) & 0x1fffff; wneg = v >> 63
    qx = (x - 1048576) / 1048576.5; qy = (y - 1048576) / 1048576.5; qz = (z - 1048576) / 1048576.5
    w = math.sqrt(max(0.0, 1.0 - qx*qx - qy*qy - qz*qz))
    return (qx, qy, qz, -w if wneg else w)


def half(h):
    return struct.unpack('<e', struct.pack('<H', h))[0]


def anim_value(d, o, frame):
    """ExtractAnimValue: the RLE stream at `o`, sampled at an integer frame."""
    k = frame
    for _ in range(100000):
        valid, total = _u('<BB', d, o)
        if total == 0:
            raise BSPError('corrupt animation value stream')
        if total > k:
            idx = k + 1 if valid > k else valid
            return _u('<h', d, o + 2*idx)[0]
        k -= total
        o += 2*(valid + 1)
    raise BSPError('animation value stream too long')


class Studio:
    """One .mdl (and its .ani, when it has animation blocks)."""

    def __init__(self, data, ani=None, name=''):
        if len(data) > MAX_MODEL or data[:4] != b'IDST':
            raise BSPError(f'{name}: not an MDL')
        self.d, self.ani, self.name = data, ani, name
        self.version = _u('<i', data, 4)[0]
        if not 44 <= self.version <= 49:
            raise BSPError(f'{name}: unsupported MDL version {self.version}')
        self.checksum = _u('<i', data, 8)[0]
        d = data
        nb, bi = _u('<ii', d, 156)
        if not 0 < nb <= 256:
            raise BSPError(f'{name}: bone count {nb} out of range')
        self.bones = []
        for i in range(nb):
            o = bi + i*216
            nm = _cstr(d, o + _u('<i', d, o)[0])
            parent = _u('<i', d, o+4)[0]
            pos = _u('<3f', d, o+32); quat = _u('<4f', d, o+44); rot = _u('<3f', d, o+60)
            posscale = _u('<3f', d, o+72); rotscale = _u('<3f', d, o+84)
            p2b = _u('<12f', d, o+96)
            if parent >= i:
                raise BSPError(f'{name}: bone {i} parent {parent} not before it')
            self.bones.append({'name': nm, 'parent': parent, 'pos': pos, 'quat': quat, 'rot': rot,
                               'posscale': posscale, 'rotscale': rotscale, 'pose_to_bone': p2b})
        self.bone_index = {b['name'].lower(): i for i, b in enumerate(self.bones)}
        na, ai = _u('<ii', d, 240)
        self.attachments = []
        for i in range(max(0, min(na, 256))):
            o = ai + i*92
            self.attachments.append({'name': _cstr(d, o + _u('<i', d, o)[0]), 'bone': _u('<i', d, o+8)[0],
                                     'local': _u('<12f', d, o+12)})
        npp, ppi = _u('<ii', d, 300)
        self.pose_params = []
        for i in range(max(0, min(npp, 64))):
            o = ppi + i*20
            self.pose_params.append({'name': _cstr(d, o + _u('<i', d, o)[0]).lower(),
                                     'start': _u('<f', d, o+8)[0], 'end': _u('<f', d, o+12)[0]})
        ninc, inci = _u('<ii', d, 336)
        self.includes = [_cstr(d, inci + i*8 + _u('<i', d, inci + i*8 + 4)[0]).replace('\\', '/').lower()
                         for i in range(max(0, min(ninc, 64)))]
        blockname, nblk, blki = _u('<iii', d, 348)
        self.ani_name = _cstr(d, blockname).replace('\\', '/').lower() if blockname and nblk else ''
        self.blocks = [_u('<ii', d, blki + i*8) for i in range(max(0, min(nblk, 100000)))] if self.ani_name else []
        n_anim, anim_i = _u('<ii', d, 180)
        self.anims = []
        for i in range(max(0, min(n_anim, 20000))):
            o = anim_i + i*100
            self.anims.append({'at': o, 'name': _cstr(d, o + _u('<i', d, o+4)[0]), 'fps': _u('<f', d, o+8)[0],
                               'flags': _u('<i', d, o+12)[0], 'frames': _u('<i', d, o+16)[0],
                               'nmove': _u('<i', d, o+20)[0], 'moveidx': _u('<i', d, o+24)[0],
                               'block': _u('<i', d, o+52)[0], 'index': _u('<i', d, o+56)[0],
                               'sectionidx': _u('<i', d, o+80)[0], 'sectionframes': _u('<i', d, o+84)[0]})
        n_seq, seq_i = _u('<ii', d, 188)
        self.sequences = []
        for i in range(max(0, min(n_seq, 20000))):
            o = seq_i + i*212
            gs = _u('<ii', d, o+68); pidx = _u('<ii', d, o+76); pst = _u('<ff', d, o+84); pend = _u('<ff', d, o+92)
            nidx = gs[0]*gs[1]
            if not 0 < nidx <= 64:
                continue
            grid = [_u('<h', d, o + _u('<i', d, o+60)[0] + 2*k)[0] for k in range(nidx)]
            wl = _u('<i', d, o+156)[0]
            weights = list(_u(f'<{nb}f', d, o + wl)) if wl else [1.0]*nb
            self.sequences.append({'label': _cstr(d, o + _u('<i', d, o+4)[0]), 'activity': _cstr(d, o + _u('<i', d, o+8)[0]).upper(),
                                   'flags': _u('<i', d, o+12)[0], 'groupsize': gs, 'param': pidx,
                                   'param_start': pst, 'param_end': pend, 'grid': grid, 'weights': weights})

    # ---- animation ----------------------------------------------------------------

    def movement(self, anim):
        """The anim's total root motion (Source units), from its movement
        blocks; None when it has none."""
        if not anim['nmove']:
            return None
        o = anim['at'] + anim['moveidx'] + (anim['nmove'] - 1)*44
        return _u('<3f', self.d, o + 32)

    def _anim_data(self, anim, frame):
        """(bytes, offset) of the bone records for `frame`, and the frame
        within that section."""
        d, off, block = self.d, anim['at'] + anim['index'], anim['block']
        if anim['sectionframes']:
            sf = anim['sectionframes']
            sec = min(frame // sf, (anim['frames'] - 1) // sf)
            block, index = _u('<ii', d, anim['at'] + anim['sectionidx'] + sec*8)
            frame -= sec*sf
            off = anim['at'] + index
        if block:
            if not self.ani or block >= len(self.blocks):
                raise BSPError(f'{self.name}: animation {anim["name"]} needs {self.ani_name or "an .ani file"}')
            start = self.blocks[block][0]
            index = anim['index'] if not anim['sectionframes'] else index
            return self.ani, start + index, frame
        return d, off, frame

    def sample(self, anim_i, frame):
        """{bone index in this file: (pos, quat, delta)} for one frame."""
        anim = self.anims[anim_i]
        frame = max(0, min(int(frame), max(0, anim['frames'] - 1)))
        d, o, frame = self._anim_data(anim, frame)
        out = {}
        delta = bool(anim['flags'] & STUDIO_DELTA)
        for _ in range(512):
            bone, flags, nxt = _u('<BBh', d, o)
            if bone >= len(self.bones):
                break
            b = self.bones[bone]
            p = o + 4
            if flags & ANIM_RAWROT:
                q = quat48(d, p); p += 6
            elif flags & ANIM_RAWROT2:
                q = quat64(d, p); p += 8
            elif flags & ANIM_ANIMROT:
                ang = []
                for j in range(3):
                    vo = _u('<h', d, p + 2*j)[0]
                    ang.append(anim_value(d, p + vo, frame) * b['rotscale'][j] if vo else 0.0)
                p += 6
                if not flags & ANIM_DELTA:
                    ang = [a + r for a, r in zip(ang, b['rot'])]
                q = euler_to_quat(*ang)
            else:
                q = (0.0, 0.0, 0.0, 1.0) if flags & ANIM_DELTA else b['quat']
            if flags & ANIM_RAWPOS:
                pos = tuple(half(h) for h in _u('<3H', d, p))
            elif flags & ANIM_ANIMPOS:
                pos = []
                for j in range(3):
                    vo = _u('<h', d, p + 2*j)[0]
                    pos.append(anim_value(d, p + vo, frame) * b['posscale'][j] if vo else 0.0)
                if not flags & ANIM_DELTA:
                    pos = [a + r for a, r in zip(pos, b['pos'])]
                pos = tuple(pos)
            else:
                pos = (0.0, 0.0, 0.0) if flags & ANIM_DELTA else b['pos']
            out[bone] = (pos, q, bool(flags & ANIM_DELTA) or delta)
            if nxt == 0:
                break
            o += nxt
        return out


class Skinned:
    """The main model's LOD 0 mesh with bone weights, grouped by material."""

    def __init__(self, studio, vvd, vtx, exists=None, skin=0):
        from .source_mdl import Model  # material naming rules are shared
        mdl = studio.d
        if vvd[:4] != b'IDSV' or _u('<i', vvd, 4)[0] != 4 or _u('<i', vvd, 8)[0] != studio.checksum:
            raise BSPError(f'{studio.name}: VVD missing or does not match')
        if _u('<i', vtx, 0)[0] != 7 or _u('<i', vtx, 16)[0] != studio.checksum:
            raise BSPError(f'{studio.name}: VTX missing or does not match')
        ntex, texi, ncd, cdi, nref, nfam, skini, nbody, bodyi = _u('<iiiiiiiii', mdl, 204)
        textures = [_cstr(mdl, texi + i*64 + _u('<i', mdl, texi + i*64)[0]) for i in range(ntex)]
        cdpaths = [_cstr(mdl, _u('<i', mdl, cdi + i*4)[0]) for i in range(ncd)]
        fam = skin if 0 <= skin < nfam else 0
        skins = [_u('<h', mdl, skini + (fam*nref + i)*2)[0] for i in range(nref)]
        nfix, fixi, datai = _u('<iii', vvd, 48)
        raw_n = _u('<i', vvd, 16)[0]

        def vert(i):
            o = datai + i*48
            w = _u('<3f', vvd, o); b = _u('<3B', vvd, o+12); nb = vvd[o+15]
            px, py, pz, nx, ny, nz, uu, vv = _u('<8f', vvd, o+16)
            bones = [(b[k], w[k]) for k in range(max(1, min(nb, 3)))]
            return (px, py, pz), (nx, ny, nz), (uu, vv), bones
        order = []
        if nfix:
            for f in range(nfix):
                lod, src, n = _u('<iii', vvd, fixi + f*12)
                if lod >= 0:
                    order.extend(range(src, src+n))
        else:
            order = list(range(raw_n))
        verts = [vert(i) for i in order]
        self.groups = {}
        vtx_body_n, vtx_body_i = _u('<ii', vtx, 28)
        for b in range(min(nbody, vtx_body_n)):
            mb = bodyi + b*16
            nmodels, _, mi = _u('<iii', mdl, mb+4)
            vb = vtx_body_i + b*8
            vtx_models_n, vtx_models_i = _u('<ii', vtx, vb)
            if nmodels < 1 or vtx_models_n < 1:
                continue
            mm = mb + mi
            nmesh, meshi, _n, verti = _u('<iiii', mdl, mm+72)
            base = verti // 48
            vm = vb + vtx_models_i
            nlod, lodi = _u('<ii', vtx, vm)
            if nlod < 1:
                continue
            vl = vm + lodi
            vmesh_n, vmesh_i = _u('<ii', vtx, vl)
            for m in range(min(nmesh, vmesh_n)):
                ms = mm + meshi + m*116
                material, _, _, vertoff = _u('<iiii', mdl, ms)
                name = Model._material(textures, cdpaths, skins, material, exists)
                tris = self.groups.setdefault(name, [])
                vme = vl + vmesh_i + m*9
                nsg, sgi = _u('<ii', vtx, vme)
                stride = vtx_strip_group_stride(vtx, vme, nsg, sgi, studio.version)
                for g in range(nsg):
                    sg = vme + sgi + g*stride
                    nv, vo, ni, io = _u('<iiii', vtx, sg)
                    if ni % 3:
                        continue
                    for k in range(0, ni, 3):
                        for j in range(3):
                            idx = _u('<H', vtx, sg + io + (k+j)*2)[0]
                            orig = _u('<H', vtx, sg + vo + idx*9 + 4)[0]
                            vi = base + vertoff + orig
                            if idx >= nv or vi >= len(verts):
                                raise BSPError(f'{studio.name}: VTX index out of range')
                            tris.append(verts[vi])
