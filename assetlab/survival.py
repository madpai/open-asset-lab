"""Authored cooperative wave mode: native world_entities schema 9.

All values are original tuning. Asset names refer to the matched runtime
roster's display names (a remaining compatibility boundary).
"""
from dataclasses import dataclass, field, asdict
import math
import re

UPGRADE, WEAPON, ARMOR, SPELL, HEALTH, MANA = range(6)
DAMAGE, FROST, CHAIN, HEAL, WARD = range(5)

@dataclass
class Item:
    id: str
    name: str
    asset: str = ''
    price: int = 100
    kind: int = WEAPON
    upgrade: int = 0
    effect: int = DAMAGE
    power: float = 0
    range: float = 30
    radius: float = 0
    duration: float = 0
    cost: float = 0

@dataclass
class Enemy:
    name: str
    character: str = ''
    weapon: str = ''
    health: float = 1
    speed: float = 1
    damage: float = 1
    gold: int = 25

@dataclass
class SurvivalConfig:
    shop: tuple
    gates: list
    enemies: list[Enemy]
    items: list[Item]
    rest_seconds: float = 30
    spawn_interval: float = 1.5
    base_enemies: int = 4
    wave_enemies: int = 2

    def record(self):
        return dict(shop=list(self.shop),gates=[list(p) for p in self.gates],
                    rest_seconds=self.rest_seconds,spawn_interval=self.spawn_interval,
                    base_enemies=self.base_enemies,wave_enemies=self.wave_enemies,
                    enemies=[asdict(e) for e in self.enemies],items=[asdict(i) for i in self.items])

def _number(v,lo,hi):
    return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi

def _integer(v,lo,hi): return type(v) is int and lo<=v<=hi

def _text(v): return isinstance(v,str) and len(v.encode('utf8'))<64 and '\0' not in v

def _vec(v): return isinstance(v,(list,tuple)) and len(v)==3 and all(_number(x,-4096,4096) for x in v)

def errors(c):
    e=[]
    if not _vec(c.shop) or not 1<=len(c.gates)<=8 or any(not _vec(p) for p in c.gates): e.append('survival: invalid shop or gates')
    if not (_number(c.rest_seconds,5,300) and _number(c.spawn_interval,.1,10) and _integer(c.base_enemies,1,1000) and _integer(c.wave_enemies,1,1000)): e.append('survival: invalid wave tuning')
    if not 1<=len(c.enemies)<=8: e.append('survival: needs 1..8 enemy types')
    for x in c.enemies:
        if not (all(_text(v) for v in (x.name,x.character,x.weapon)) and x.name and _number(x.health,.01,100) and _number(x.speed,.1,5) and _number(x.damage,.01,100) and _integer(x.gold,1,4294967295)):e.append('survival: invalid enemy')
    if not 1<=len(c.items)<=32: e.append('survival: needs 1..32 items')
    seen=set()
    for i in c.items:
        if not (_text(i.id) and re.fullmatch(r'[a-z0-9_:/\.]+',i.id) and i.id not in seen and _text(i.name) and i.name and _text(i.asset) and _integer(i.price,0,4294967295) and _integer(i.kind,0,5) and _integer(i.upgrade,0,4) and _integer(i.effect,0,4) and _number(i.power,0,.75 if i.kind==ARMOR else 10000) and _number(i.range,0,200) and _number(i.radius,0,50) and _number(i.duration,0,60) and _number(i.cost,0,1000)):e.append(f'survival: invalid item {i.id}')
        seen.add(i.id)
    return e
