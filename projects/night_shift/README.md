# MegaMod: Night Shift (content project)

The source of MegaMod's first production vertical slice: a co-op horror
scenario in HARROW ANNEX. Every asset is original and generated here
(GPL-3.0-or-later); nothing built is committed.

```sh
python -m assetlab project budget projects/night_shift            # validate + entity/binding budget
python -m assetlab project build projects/night_shift --output BUNDLE
python -m assetlab project build projects/night_shift/project_x8.py --output X8_BUNDLE
```

| File | Package |
|---|---|
| `art.py` | `nightshift.assets` -- 17 textures/materials/models, 18 sounds, the sign font |
| `facility.py` | `nightshift.facility` -- 11 prefabs (security door, breaker, console, valve, lamps, lights, shutter, data core, steam vent, pump) |
| `world01.py` | `nightshift.world01` -- the world `nightshift:world/harrow_annex` (file `night_shift`) |
| `scripts/anomaly.lua` | `nightshift:script/anomaly`, the one Lua script |
| `project.py` | what `assetlab project` builds |
| `world_x8.py`, `project_x8.py` | a separate X8 world that restores D2 and D5: 74 runtime objects, 23 spatial, 11 logical, 40 host-only; original world01 bytes unchanged |

Design, findings and the end-to-end test live in MegaMod:
`docs/night_shift/` and `scripts/test_night_shift.sh`
(https://github.com/madpai/megamod-showdown/tree/main/docs/night_shift).
Tests here: `tests/test_project.py`.
