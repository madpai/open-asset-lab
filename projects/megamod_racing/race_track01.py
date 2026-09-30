"""Cinder Circuit: original elevated ribbon, banked sweep, technical S and jump.

World units are MegaMod units. This project is deliberately generated from
an authored centre line, then compiled to ordinary OALMAP triangles; no
procedural track generation runs in the engine.
"""
from __future__ import annotations

import math
from assetlab.prefabs import PrefabInstance
from assetlab.racing import Gate, Pad, RaceConfig
from assetlab.resources import Requirement
from assetlab.world import Environment, Light, OriginalWorld, Triangle
import race_art as art
import race_trackkit as trackkit

PACKAGE='racing.track01'
FILE='cinder_circuit'
KNOTS=[
    (0,0,0), (145,0,0), (290,25,0), (365,105,0), (380,210,0),
    (300,285,0), (175,305,0), (65,245,0), (-45,215,0),
    (-175,290,4), (-300,280,1), (-385,190,0), (-355,80,0),
    (-230,15,0), (-105,-25,0),
]
SUBDIV=7
WIDTH=11.0
MATERIALS={
    'road':(25,34,52),'road_alt':(35,47,67), 'edge':(26,160,200),
    'rail':(40,100,155),'rail_hot':(220,75,32),'boost':(27,226,185),
    'stripe':(240,217,75),'support':(36,44,62),
}


def cubic(p0,p1,p2,p3,t):
    return 0.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+
                (-p0+3*p1-3*p2+p3)*t*t*t)


def stations():
    out=[]
    n=len(KNOTS)
    for j in range(n):
        a,b,c,d=(KNOTS[(j+k)%n] for k in (-1,0,1,2))
        for i in range(SUBDIV):
            t=i/SUBDIV
            p=tuple(cubic(a[k],b[k],c[k],d[k],t) for k in range(3))
            if j==8 and i in (4,5,6):
                # The gap needs real upward launch velocity at racing speed.
                # These heights are collision vertices, not decorative art.
                rise={4:0.2,5:1.2,6:3.2}[i]
                p=(p[0],p[1],p[2]+rise)
            # Bank the long east-side speed curve. Outer edge rises up to
            # 2.2 wu; the collision is the same triangles the player sees.
            bank=0.0
            if 2<=j<=5:
                bank=(0.0,0.8,2.2,2.2,1.2)[j-2] if j<6 else 0
            out.append((p,bank,j,i))
    return out


def ribbon():
    points=stations(); n=len(points)
    lr=[]
    for i,(p,bank,_,_) in enumerate(points):
        prev=points[(i-1)%n][0]; nex=points[(i+1)%n][0]
        dx=nex[0]-prev[0]; dy=nex[1]-prev[1]
        length=math.hypot(dx,dy)
        lx,ly=-dy/length,dx/length
        # A signed bank changes the road edge heights, not an invisible
        # flat collider. The turn remains approachable in either direction.
        left=(p[0]+lx*WIDTH/2,p[1]+ly*WIDTH/2,p[2]+bank/2)
        right=(p[0]-lx*WIDTH/2,p[1]-ly*WIDTH/2,p[2]-bank/2)
        lr.append((left,right))
    tris=[]
    for i,(p,bank,j,sub) in enumerate(points):
        k=(i+1)%n
        if j==8 and sub==6: continue  # jump gap at the rising ramp crest
        l0,r0=lr[i]; l1,r1=lr[k]
        road='road_alt' if (i//5)%2 else 'road'
        tris += [Triangle((r0,r1,l1),road),Triangle((r0,l1,l0),road)]
        edge_height=1.05 if j not in (9,10) else 0.35
        lu0=(l0[0],l0[1],l0[2]+edge_height)
        lu1=(l1[0],l1[1],l1[2]+edge_height)
        ru0=(r0[0],r0[1],r0[2]+edge_height)
        ru1=(r1[0],r1[1],r1[2]+edge_height)
        rail='rail_hot' if j in (2,3,4,5) else 'rail'
        tris += [Triangle((l0,l1,lu1),rail),Triangle((l0,lu1,lu0),rail),
                 Triangle((r1,r0,ru0),rail),Triangle((r1,ru0,ru1),rail)]
        if i%7==0:
            mid0=tuple((l0[m]+r0[m])*0.5 for m in range(3))
            mid1=tuple((l1[m]+r1[m])*0.5 for m in range(3))
            # Short centre dash, raised only for drawing.
            w=0.06
            o=(-dy/length*w,dx/length*w,0.012)
            a=tuple(mid0[m]-o[m] for m in range(3)); b=tuple(mid1[m]-o[m] for m in range(3))
            c=tuple(mid1[m]+o[m] for m in range(3)); d=tuple(mid0[m]+o[m] for m in range(3))
            tris += [Triangle((a,b,c),'stripe',False),Triangle((a,c,d),'stripe',False)]
    return tris


GATE_STATIONS=(0,14,27,40,54,68,82,96)
PAD_STATIONS=(6,31,59)


def pose(index):
    p=stations()[index][0]
    q=stations()[(index+1)%len(stations())][0]
    return p,math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))


def world():
    tris=ribbon()
    grid=[]
    for i in range(8):
        grid.append({'position':[-3.5-(i//2)*2.4,(-1.8 if i%2 else 1.8),0.6],
                     'yaw_degrees':0.0,'team':0})
    instances=[]
    for n,idx in enumerate(GATE_STATIONS):
        p,yaw=pose(idx)
        instances.append(PrefabInstance(f'gate_{n:02d}',art.rid('prefab','checkpoint_gate'),
                                        (p[0],p[1],p[2]),yaw,1.3))
    for n,idx in enumerate(PAD_STATIONS):
        p,yaw=pose(idx)
        instances.append(PrefabInstance(f'pad_{n:02d}',art.rid('prefab','boost_pad'),
                                        (p[0],p[1],p[2]),yaw,1.0))
    instances.sort(key=lambda x:x.id)
    lights=[]
    for i,idx in enumerate(GATE_STATIONS):
        p,_=pose(idx)
        lights.append(Light(f'gate_{i:02d}','point',(p[0],p[1],p[2]+3.8),
                            (0.12,0.65,1.0) if i%2==0 else (1.0,0.32,0.06),3.5,24))
    gates=[]
    for n,idx in enumerate(GATE_STATIONS):
        p,yaw=pose(idx)
        angle=math.radians(yaw)
        fx,fy=math.cos(angle),math.sin(angle)
        gates.append(Gate(f'gate_{n:02d}',(p[0],p[1],p[2]+0.4),(fx,fy),5.1,3.5,
                          (p[0]-fx*5,p[1]-fy*5,p[2]+0.26),angle))
    pads=[]
    for idx in PAD_STATIONS:
        p,_=pose(idx)
        pads.append(Pad((p[0],p[1],p[2]+0.25),3.2))
    race=RaceConfig(3,[(tuple(s['position']),math.radians(s['yaw_degrees'])) for s in grid],
                    gates,pads,{'max_speed':38,'boost_speed':52,'acceleration':18,
                                'grip':12,'drift_grip':3.2,'steer_low':2.5,'steer_high':0.9})
    return OriginalWorld(
        id='racing:world/cinder_circuit',file_name=FILE,display_name='MegaMod Racing: Cinder Circuit',
        materials=MATERIALS,boxes=[],spawns=grid,entities=[],triangles=tris,
        package=PACKAGE,requires=[Requirement(art.PACKAGE,[art.rid('model','hyperkart')]),
                                  Requirement(trackkit.PACKAGE,[art.rid('prefab','boost_pad'),
                                                               art.rid('prefab','checkpoint_gate')])],
        prefab_instances=instances,environment=Environment((0.23,0.32,0.45),(0.015,0.023,0.062),
                                                             (0.025,0.045,0.12),0.0004,15),
        lights=lights,texture_style='industrial',racing=race)
