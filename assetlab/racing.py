"""Bounded authored race route for world_entities schema 8.

This is content validation. The engine owns simulation and checks the same
limits again while loading an untrusted package.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math
from .prefabs import local_id_error
from .resources import parse_id, OK

TUNING_LIMITS={
    'max_speed':(2,120),'reverse_speed':(0,30),'acceleration':(.1,100),
    'brake_acceleration':(.1,150),'coast_drag':(0,30),'grip':(.1,50),
    'drift_grip':(.1,30),'steer_low':(.1,6),'steer_high':(.1,4),
    'steer_fade_speed':(1,120),'drift_yaw':(1,3),'boost_speed':(2,150),
    'boost_acceleration':(.1,150),'boost_seconds':(.1,3),
    'jump_gravity':(1,100),'air_steer':(0,1),'wall_restitution':(0,.5),
    'wall_speed_loss':(0,.8),'radius':(.1,2),'height':(.1,3),
    'ground_clearance':(.05,1),
}


@dataclass
class Gate:
    id: str
    position: tuple
    forward: tuple
    half_width: float
    half_height: float
    recovery: tuple
    recovery_yaw: float

    def record(self):
        return dict(id=self.id,position=list(self.position),forward=list(self.forward),
                    half_width=self.half_width,half_height=self.half_height,
                    recovery=list(self.recovery),recovery_yaw=self.recovery_yaw)


@dataclass
class Pad:
    position: tuple
    radius: float

    def record(self): return dict(position=list(self.position),radius=self.radius)


@dataclass
class RaceConfig:
    laps: int
    grid: list
    gates: list[Gate]
    pads: list[Pad] = field(default_factory=list)
    vehicle: dict = field(default_factory=dict)
    model: str = 'racing:model/hyperkart'

    def record(self):
        return dict(laps=self.laps,grid=[dict(position=list(p),yaw=y) for p,y in self.grid],
                    gates=[g.record() for g in self.gates],pads=[p.record() for p in self.pads],
                    vehicle=dict(sorted(self.vehicle.items())),model=self.model)


def _vec(v,n):
    return isinstance(v,(tuple,list)) and len(v)==n and all(
        isinstance(x,(int,float)) and math.isfinite(x) and abs(x)<=4096 for x in v)


def _number(v,lo,hi):
    return isinstance(v,(int,float)) and math.isfinite(v) and lo<=v<=hi


def errors(c: RaceConfig):
    e=[]
    code,_,rid=parse_id(c.model) if isinstance(c.model,str) else (None,None,None)
    if code!=OK or rid.type!='model':
        e.append('racing: model must name a model resource')
    if not isinstance(c.laps,int) or not 1<=c.laps<=9: e.append('racing: laps must be 1..9')
    if not 1<=len(c.grid)<=8: e.append('racing: grid needs 1..8 slots')
    for i,(p,yaw) in enumerate(c.grid):
        if not _vec(p,3) or not _number(yaw,-360,360): e.append(f'racing: grid slot {i} invalid')
    if not 2<=len(c.gates)<=32: e.append('racing: gates need 2..32 entries')
    seen=set()
    for i,g in enumerate(c.gates):
        why=local_id_error(g.id,'gate id')
        if why: e.append(f'racing: gate {i}: {why}')
        if g.id in seen: e.append(f'racing: duplicate gate id {g.id}')
        seen.add(g.id)
        if not _vec(g.position,3) or not _vec(g.recovery,3) or not _vec(g.forward,2) or (
                _vec(g.forward,2) and abs(math.hypot(*g.forward)-1)>.01) or not (
                _number(g.half_width,.5,30) and _number(g.half_height,.5,10) and
                _number(g.recovery_yaw,-360,360)):
            e.append(f'racing: gate {i} invalid')
        if i and _vec(g.position,3) and _vec(c.gates[i-1].position,3):
            d=math.dist(g.position,c.gates[i-1].position)
            if d<2 or d>1000: e.append(f'racing: gate {i} is too close to or far from gate {i-1}')
    if len(c.pads)>16: e.append('racing: more than 16 boost pads')
    for i,p in enumerate(c.pads):
        if not _vec(p.position,3) or not _number(p.radius,.5,20):
            e.append(f'racing: pad {i} invalid')
    for k,v in c.vehicle.items():
        if k not in TUNING_LIMITS: e.append(f'racing: unknown vehicle tuning {k}')
        elif not _number(v,*TUNING_LIMITS[k]): e.append(f'racing: vehicle {k} out of bounds')
    if (c.vehicle.get('drift_grip',3.2)>=c.vehicle.get('grip',12) or
            c.vehicle.get('steer_high',.9)>c.vehicle.get('steer_low',2.5) or
            c.vehicle.get('boost_speed',52)<c.vehicle.get('max_speed',38)):
        e.append('racing: inconsistent vehicle grip, steering or boost')
    return e
