"""Static Source models: MDL v44-v48 + VVD v4 + DX90 VTX v7, LOD 0, bind pose.

Layouts follow Valve source-sdk-2013 studio.h and optimize.h. Only what a
static prop needs is read: texture names, the skin table, body part 0's
first model, its meshes' triangle lists and the vertices they index.
"""
from __future__ import annotations
import struct
from .source_bsp import BSPError
from ..coords import angle_matrix  # noqa: F401  (re-exported for callers)

MAX_MODEL = 32 * 1024 * 1024


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


class Model:
    """Triangles per material in model space: {material: [(pos, normal, uv) * 3n]}."""

    def __init__(self, mdl, vvd, vtx, skin=0, exists=None):
        for blob in (mdl, vvd, vtx):
            if len(blob) > MAX_MODEL:
                raise BSPError("model file exceeds 32 MiB")
        if mdl[:4] != b"IDST":
            raise BSPError("invalid MDL magic")
        version = _u("<i", mdl, 4)[0]
        if not 44 <= version <= 48:
            raise BSPError(f"unsupported MDL version {version}")
        if vvd[:4] != b"IDSV" or _u("<i", vvd, 4)[0] != 4:
            raise BSPError("unsupported VVD")
        if _u("<i", vtx, 0)[0] != 7:
            raise BSPError("unsupported VTX version")
        checksum = _u("<i", mdl, 8)[0]
        if _u("<i", vvd, 8)[0] != checksum or _u("<i", vtx, 16)[0] != checksum:
            raise BSPError("MDL/VVD/VTX checksums differ")

        ntex, texi, ncd, cdi, nref, nfam, skini, nbody, bodyi = _u("<iiiiiiiii", mdl, 204)
        if not (0 < ntex <= 256 and 0 <= ncd <= 64 and 0 < nbody <= 64 and 0 < nfam <= 64 and 0 < nref <= 256):
            raise BSPError("model table counts out of range")
        textures = [_cstr(mdl, texi + i * 64 + _u("<i", mdl, texi + i * 64)[0]) for i in range(ntex)]
        cdpaths = [_cstr(mdl, _u("<i", mdl, cdi + i * 4)[0]) for i in range(ncd)]
        fam = skin if 0 <= skin < nfam else 0
        skins = [_u("<h", mdl, skini + (fam * nref + i) * 2)[0] for i in range(nref)]

        # VVD LOD 0 vertices, through the fixup table when there is one.
        nfix, fixi, datai = _u("<iii", vvd, 48)
        raw_n = _u("<i", vvd, 16)[0]
        if not 0 < raw_n <= 200000 or datai + raw_n * 48 > len(vvd):
            raise BSPError("VVD vertex data out of range")
        def vert(i):
            o = datai + i * 48 + 16
            px, py, pz, nx, ny, nz, u, v = _u("<8f", vvd, o)
            return (px, py, pz), (nx, ny, nz), (u, v)
        if nfix:
            if not 0 < nfix <= 10000:
                raise BSPError("VVD fixup count out of range")
            order = []
            for f in range(nfix):
                lod, src, n = _u("<iii", vvd, fixi + f * 12)
                if lod >= 0:
                    order.extend(range(src, src + n))
            verts = [vert(i) for i in order]
        else:
            verts = [vert(i) for i in range(raw_n)]

        self.groups = {}
        vtx_body_n, vtx_body_i = _u("<ii", vtx, 28)
        body_n = min(nbody, vtx_body_n)
        for b in range(body_n):
            mb = bodyi + b * 16
            nmodels, _, mi = _u("<iii", mdl, mb + 4)
            vb = vtx_body_i + b * 8
            vtx_models_n, vtx_models_i = _u("<ii", vtx, vb)
            if nmodels < 1 or vtx_models_n < 1:
                continue
            # A static prop draws its body parts' first (default) model.
            mm = mb + mi
            nmesh, meshi, _nverts, verti = _u("<iiii", mdl, mm + 72)
            model_base = verti // 48
            vm = vb + vtx_models_i
            nlod, lodi = _u("<ii", vtx, vm)
            if nlod < 1:
                continue
            vl = vm + lodi
            vmesh_n, vmesh_i = _u("<ii", vtx, vl)
            for m in range(min(nmesh, vmesh_n)):
                ms = mm + meshi + m * 116
                material, _, _, vertoff = _u("<iiii", mdl, ms)
                name = self._material(textures, cdpaths, skins, material, exists)
                tris = self.groups.setdefault(name, [])
                vme = vl + vmesh_i + m * 9
                nsg, sgi = _u("<ii", vtx, vme)
                for g in range(nsg):
                    sg = vme + sgi + g * 25
                    nv, vo, ni, io = _u("<iiii", vtx, sg)
                    if ni % 3 or ni > 600000:
                        continue  # a strip, not a list; CS:S props compile to lists
                    for k in range(0, ni, 3):
                        tri = []
                        for j in (0, 1, 2):
                            idx = _u("<H", vtx, sg + io + (k + j) * 2)[0]
                            if idx >= nv:
                                raise BSPError("VTX index out of range")
                            orig = _u("<H", vtx, sg + vo + idx * 9 + 4)[0]
                            vi = model_base + vertoff + orig
                            if vi >= len(verts):
                                raise BSPError("VTX vertex out of range")
                            tri.append(verts[vi])
                        tris.extend(tri)

    @staticmethod
    def _material(textures, cdpaths, skins, ref, exists):
        tex = textures[skins[ref] if 0 <= ref < len(skins) and 0 <= skins[ref] < len(textures) else 0]
        tex = tex.replace("\\", "/").lower().strip("/")
        dirs = [c.replace("\\", "/").lower().strip("/") for c in cdpaths] or [""]
        names = ["/".join(x for x in (d, tex) if x) for d in dirs]
        # studiomdl searches $cdmaterials in order; the first that exists wins.
        return next((n for n in names if exists and exists(n)), names[0])


