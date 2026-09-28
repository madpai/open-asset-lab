# MegaMod: Night Shift (content project)

The source of MegaMod's first production vertical slice: a co-op horror
scenario in HARROW ANNEX. Every asset is original and generated here
(GPL-3.0-or-later); nothing built is committed.

```sh
python -m assetlab project budget projects/night_shift            # validate + entity/binding budget
python -m assetlab project build projects/night_shift --output BUNDLE
python -m assetlab project build projects/night_shift/project_x8.py --output X8_BUNDLE
python -m assetlab project build projects/night_shift/project_x9.py --output X9_BUNDLE
```

| File | Package |
|---|---|
| `art.py` | `nightshift.assets` -- 17 textures/materials/models, 18 sounds, the sign font |
| `facility.py` | `nightshift.facility` -- 11 prefabs (security door, breaker, console, valve, lamps, lights, shutter, data core, steam vent, pump) |
| `world01.py` | `nightshift.world01` -- the world `nightshift:world/harrow_annex` (file `night_shift`) |
| `scripts/anomaly.lua` | `nightshift:script/anomaly`, the one Lua script |
| `project.py` | what `assetlab project` builds |
| `world_x8.py`, `project_x8.py` | a separate X8 world that restores D2 and D5: 74 runtime objects, 23 spatial, 11 logical, 40 host-only; original world01 bytes unchanged |
| `art_x9.py`, `facility_x9.py`, `world_x9.py`, `project_x9.py` | X9 visual package with authored light, fog, industrial surfaces and richer materials; X8 remains byte stable |

## X9 visual authoring

The X9 world uses `assetlab.world.Environment` and `Light`. Environment is
world scoped; lights are placed in world coordinates and sorted by local ID.
Up to 32 may be authored, and MegaMod selects the nearest eight active lights
each frame. A light may name a placed relay (including a prefab child) so the
existing host action and X8 logical state control it. Static visual trim uses
`Box(..., solid=False)` and therefore adds no runtime or replication ID.

```python
from assetlab.world import Environment, Light

world.environment = Environment(
    ambient=(.36, .39, .45), clear=(.015, .022, .034),
    fog_color=(.045, .055, .075), fog_density=.08, fog_start=2.5)
world.lights = [
    Light('aux_emergency', 'point', (-11.7, -5.8, 1.72),
          (1, .18, .08), 1.9, 2.8),
    Light('aux_main', 'spot', (-12.6, -4.2, 1.82),
          (1, .68, .31), 4.8, 4.6, relay='nightshift:entity/aux_power',
          direction=(0, 0, -1), inner_degrees=32, outer_degrees=67),
]
world.texture_style = 'industrial'
```

`assetlab.assets.Material` accepts `emissive` (0..4) and `roughness` (0..1):

```python
Material('nightshift:material/door_lamp',
         'nightshift:texture/door_lamp', emissive=1.4, roughness=.55)
```

Emissive makes the surface visible in darkness. It does not cast light; pair
it with a `Light` when nearby geometry should be lit. Materials using either
new parameter emit assets schema 2. Old materials continue to emit schema 1.
The package digest and world key include visual fields and texture bytes.
All visual values and references are validated by `project build`.

Design, findings and the end-to-end test live in MegaMod:
`docs/night_shift/` and `scripts/test_night_shift.sh`
(https://github.com/madpai/megamod-showdown/tree/main/docs/night_shift).
Tests here: `tests/test_project.py`.
