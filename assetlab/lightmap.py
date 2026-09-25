"""Static LDR Source lightmaps, atlas packing and the runtime x2 convention."""
import struct
from PIL import Image
from .importers.source_bsp import BSPError


def lightmap_atlases(world, size=1024):
    pages = []; placement = {}; x = y = row = 0
    for face, (w, h, data) in sorted(world.light_samples.items()):
        if w+2 > size or h+2 > size:
            raise BSPError('lightmap exceeds atlas size')
        if x+w+2 > size: x=0; y+=row; row=0
        if not pages or y+h+2 > size:
            if len(pages) >= 8: raise BSPError('lightmap atlas budget exceeded')
            pages.append(Image.new('RGBA', (size,size), (128,128,128,255)))
            x=y=row=0
        rgba=bytearray()
        for r,g,b,e in struct.iter_unpack('<4B',data):
            exponent=e if e<128 else e-256
            # Gamma-encode linear irradiance for the existing legacy texture
            # pipeline, then half brightness for mesh.frag's lightmap x2.
            rgba.extend((*[round(min(1.0,max(0.0,c*2.0**exponent/255.0))**(1/2.2)*127.5) for c in (r,g,b)],255))
        tile=Image.frombytes('RGBA',(w,h),bytes(rgba))
        atlas=pages[-1]; atlas.paste(tile,(x+1,y+1))
        atlas.paste(tile.crop((0,0,w,1)),(x+1,y))
        atlas.paste(tile.crop((0,h-1,w,h)),(x+1,y+h+1))
        atlas.paste(tile.crop((0,0,1,h)),(x,y+1))
        atlas.paste(tile.crop((w-1,0,w,h)),(x+w+1,y+1))
        for xx,yy,tx,ty in ((x,y,0,0),(x+w+1,y,w-1,0),(x,y+h+1,0,h-1),(x+w+1,y+h+1,w-1,h-1)):
            atlas.putpixel((xx,yy),tile.getpixel((tx,ty)))
        placement[face]=(len(pages)-1,x+1,y+1,w,h)
        x+=w+2; row=max(row,h+2)
    uv={}
    for vertex,(face,s,t) in world.light_uv.items():
        page,x,y,w,h=placement[face]
        uv[vertex]=(page,(x+min(w-1,max(0,s))+0.5)/size,(y+min(h-1,max(0,t))+0.5)/size)
    return [(size,size,p.tobytes()) for p in pages],uv
