"""Gatebound: original arena and tunable RPG shop, with no donor assets."""
from assetlab.world import OriginalWorld,Box,Environment,Light
from assetlab.survival import SurvivalConfig,Enemy,Item,UPGRADE,WEAPON,ARMOR,SPELL,HEALTH,MANA,DAMAGE,FROST,CHAIN,HEAL,WARD
NAME='Gatebound: The Borrowed Apocalypse'

def libraries(): return {}

def worlds():
    materials={'floor':(54,59,68),'stone':(90,87,80),'gate':(230,45,12),'shop':(40,170,210),'trim':(218,178,70)}
    boxes=[Box((-12,-12,-.4),(12,12,0),'floor')]
    boxes += [Box((-12,-12,0),(-11.6,12,4),'stone'),Box((11.6,-12,0),(12,12,4),'stone'),Box((-12,11.6,0),(12,12,4),'stone'),Box((-12,-12,0),(12,-11.6,4),'stone')]
    for x,y in [(-4,0),(4,0),(-4,5),(4,5)]:boxes.append(Box((x-.4,y-.4,0),(x+.4,y+.4,2.5),'stone'))
    gates=[(-8,8,0),(8,8,0),(0,9,0)]
    for x,y,z in gates:
        boxes += [Box((x-1.4,y-.3,0),(x-1,y+.3,2.8),'stone'),Box((x+1,y-.3,0),(x+1.4,y+.3,2.8),'stone'),Box((x-1.4,y-.3,2.8),(x+1.4,y+.3,3.2),'stone'),Box((x-.9,y+.12,.1),(x+.9,y+.16,2.7),'gate',solid=False)]
    boxes += [Box((-1,-8,0),(1,-7.5,.7),'shop'),Box((-1.1,-8.1,.7),(1.1,-7.4,.8),'trim')]
    items=[Item('gatebound:item/sidearm','Borrowed Sidearm',asset='weapons\\pistol\\pistol',price=0),
           Item('gatebound:spell/ember','Ember Bolt',price=0,kind=SPELL,power=.35,cost=20),
           Item('gatebound:weapon/rifle','Assault Rifle',asset='weapons\\assault rifle\\assault rifle',price=180),
           Item('gatebound:weapon/shotgun','Shotgun',asset='weapons\\shotgun\\shotgun',price=350),
           Item('gatebound:armor/leather','Patchwork Armor',price=120,kind=ARMOR,power=.15),
           Item('gatebound:armor/plate','Gatekeeper Plate',price=600,kind=ARMOR,power=.4),
           Item('gatebound:spell/frost','Frostbite',price=200,kind=SPELL,effect=FROST,power=.2,duration=4,cost=25),
           Item('gatebound:spell/chain','Chain Lightning',price=400,kind=SPELL,effect=CHAIN,power=.3,radius=3,cost=40),
           Item('gatebound:spell/mend','Mend Wounds',price=150,kind=SPELL,effect=HEAL,power=.35,cost=25),
           Item('gatebound:spell/ward','Borrowed Aegis',price=300,kind=SPELL,effect=WARD,duration=6,cost=35),
           Item('gatebound:item/health','Health Potion',price=35,kind=HEALTH,power=.5),
           Item('gatebound:item/mana','Magicka Potion',price=30,kind=MANA,power=60)]
    for i,(name,price) in enumerate([('Vitality',150),('Stamina',100),('Magicka',125),('Power',200),('Fortune',250)]):items.append(Item('gatebound:upgrade/'+name.lower(),name,price=price,kind=UPGRADE,upgrade=i))
    config=SurvivalConfig((0,-7,0),gates,[Enemy('Gate Marauder',weapon='weapons\\pistol\\pistol',health=.65,speed=.9,damage=.35,gold=25),Enemy('Gate Enforcer',weapon='weapons\\assault rifle\\assault rifle',health=1.2,speed=.7,damage=.3,gold=40)],items)
    starts=[dict(position=(x,-6,0),yaw_degrees=90,team_index=0) for x in [-2,-1,0,1,2,3,4,5]]
    return [OriginalWorld(id='gatebound:world/arena',file_name='gatebound',display_name=NAME,materials=materials,boxes=boxes,spawns=starts,entities=[],survival=config,environment=Environment((.3,.28,.24),(.03,.03,.05),(.04,.025,.02),.001,10),lights=[Light('gate_'+str(n),'point',(x,y,1.5),(1,.12,.02),2,4) for n,(x,y,z) in enumerate(gates)],texture_style='industrial')]
