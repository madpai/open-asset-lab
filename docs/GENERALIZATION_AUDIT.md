# Generalization audit — Source map import (2026-09-23)

**Question:** does Open Asset Lab import Source maps by format rules and data, or was it accidentally tuned to de_dust2, the one map that worked?

**Answer:** it had drifted toward de_dust2 in about a dozen places. Some were hardcoded (team rules in the engine). Most were omissions dust2 happened not to need: brush entities, model entities, BSP v19, water, one-way nav links, low ceilings. Those are now refactored into format tables and a translation registry. Eight structurally different maps from four Source games now go through one command and one code path, with no per-map code, and each writes a compatibility report. The dust2 reference still converts, renders, collides and plays; on-phone confirmation of this build is pending.

## 1. The pipeline, traced

```
BSP file ──> SourceBSP (importers/source_bsp.py)
               version table (VERSIONS, FACE_LUMP_VERSION, STATIC_PROP_VERSIONS)
               lump table + lump_report(): consumed / not needed (why) / unsupported (what is lost)
               parse_entities(): tokenizer, case-insensitive keys
               convert(): world model faces + brush entities (translate.BRUSH_CLASSES)
                          surface flags -> excluded-face counts; SURF_WARP -> non-solid
                          displacements (Valve CCoreDispInfo layout)
                          starts (translate.SPAWN_CLASSES) -> grounded or rejected
         ──> compile_map (package.py)
               Resolver: search path = BSP pakfile, --material-root/--game-dir roots, VPKs
               add_models(): static props (lump v4-11) + model entities (translate.MODEL_CLASSES)
               materials: KeyValues VMT parser (incl. patch) -> translate.material_policy
                          VTF table (13 formats, frames/faces/depth) -> RGBA
                          fit_textures(): budget = Open Halo's 128 MiB cap
               vertex dedup, groups by (material, solid), OALMAP v1 + manifest + compatibility
         ──> Open Halo (halo-sandbox branch)
               external_map.c: load (file or mmapped APK asset), solid-index view, manifest "team"
               collision: hta_collision_build_cells(solid view, 255 across)
               nav: hta_nav_build, hta_nav_main_from_spawns, hta_nav_playable (directed)
               external_world.c: starts, spawn lift, flags, item spread on playable nodes
               render: same renderer as Blood Gulch; the sky is Halo's (kept on purpose)
```

All Source→runtime positions go through `assetlab/coords.py`: 1 Source unit = 1 inch, 1 Open Halo unit = 10 ft, same axes. Nothing else scales or reorients anything.

## 2. Findings

Each item: what was wrong, and how it was generalized.

| # | Finding (before) | Kind | Now |
|---|---|---|---|
| 1 | **Team rules hardcoded in the engine**: `external_map.c` mapped `info_player_counterterrorist`/`terrorist` to blue/red by class name | Map/game-specific | Asset Lab's registry writes `"team"` per start; the engine reads only that |
| 2 | Start classes were a fixed CS/TF set; TF2 `TeamNum` ignored; keys case-sensitive (`TeamNum` vs `teamnum`) | Entity special-casing | `translate.SPAWN_CLASSES`, fixed or keyvalue-driven teams, case-insensitive keys |
| 3 | Only BSP v20 accepted, although v19 shares every record read; v21+ would have been an unexplained failure | Version assumption | `VERSIONS` table (v19, v20); v21+ refused with a reason; face lump version checked separately |
| 4 | Entity lump parsed with a regex that breaks on braces inside values | Parser fragility | Tokenizer with errors at an offset; regression test |
| 5 | **Brush entities silently dropped** (func_brush, func_wall, doors, breakables, func_illusionary…) | Silent omission | `translate.BRUSH_CLASSES`: solid/non-solid rule, origin/angles, hidden-at-spawn keyvalues; counts reported |
| 6 | **Model entities silently dropped** (prop_physics/_multiplayer, prop_dynamic…) | Silent omission | `translate.MODEL_CLASSES`, placed like static props, reported |
| 7 | Static prop lump: inspection supported v10 only, placement v4–10 | Version assumption | One reader for v4–11 (shared leading fields); v11's game-specific tail reported as not interpreted |
| 8 | VMTs read with a regex: missed unquoted values, the shader name, `patch` insert/replace | Parser fragility | Valve KeyValues parser; `patch` handled; shader drives policy |
| 9 | Placeholder colours chosen by words in material **names** ("grass", "wood") | Name-keyed | From the VMT's `$surfaceprop` (Source's generic vocabulary), else neutral |
| 10 | VTF: 4 formats; frames, cubemap faces and depth ignored, so animated textures decoded from the wrong offset | Silent corruption | `VTF_FORMATS` table (13 formats), correct offsets; unknown formats named |
| 11 | Water (SURF_WARP, Water shader) was solid | Silent behaviour | Drawn, not collided with; counted |
| 12 | Faces hidden by surface flags vanished without a count | Silent omission | `faces_excluded_by_flag` per flag |
| 13 | Unused lumps (lightmaps, overlays, clip brushes, cubemaps, physics…) ignored silently | Silent omission | `lump_report()`: every non-empty lump classified; unsupported ones listed as features lost |
| 14 | 3D skybox geometry imported without comment | Silent behaviour | Reported ("imported unscaled at its build location"). The **Halo sky** is kept deliberately (owner's call). Since 2026-09-24 the skybox's own BSP area is left out when no start shares it |
| 15 | Bounds sanity limit `1000` wu, arbitrary | Unexplained constant | Derived from Source's MAX_COORD (±16384 in) |
| 16 | Texture data over Open Halo's 128 MiB cap failed only at runtime | Late failure | `fit_textures()` halves the largest textures to the budget; reported per map |
| 17 | Package wrote 3 unshared vertices per triangle; prop-heavy maps exceeded the 256 MiB file cap | Waste | Identical vertices shared (2–3× smaller vertex data); deterministic |
| 18 | Dependencies only via a list of `--vpk`; Open Halo path fixed relative to this checkout | Hardcoded paths | `--game-dir` mounts a game directory like Source does; `OPEN_HALO_ROOT` env; search path and hit counts reported |
| 19 | Starts with no ground were shipped with a warning | Unsafe default | Rejected from the package, listed in `rejected_spawn_points` |
| 20 | Collision triangle count not reported | Missing diagnostic | `collision_triangles` in every report |
| 21 | **Engine re-grounded starts from 1 wu up** (tuned after dust2's roofs): on cs_office that is the top of the ceiling tiles, and 15 of 40 bodies walked off into the void | Tuned to one map | Packages already ground starts; imported maps use `HTA_EXTERNAL_SPAWN_LIFT` 0.1 wu (`hta_game.spawn_lift`); Blood Gulch unchanged |
| 22 | **Items and flags placed per nav region** (undirected): ledges you can drop into but not leave, so every bot path to an item failed and bots stood still (cs_office, de_inferno 0 kills) | Tuned to one map | `hta_nav_playable`: nodes reachable from a main-region start *and* back, following one-way links |
| 23 | Host map test accepted a start if any floor lay within 1.5 wu of a 1 wu snap: it passed cs_office's ceiling spawns | Weak gate | Uses the runtime lift; a body stands 5 s and walks 5 s; "fell out of the map" is counted |
| 24 | Imported collision grid at 256 cells hit the 256 clamp (257 computed) | Latent edge case | 255 across; clamp documented; far-corner test |

**Map-specific hacks remaining: none found.** A search of both repositories' source for map names, Source paths, private paths and fixed coordinates finds only:
- the unit scale in `coords.py`
- the generic Source class names in `translate.py`
- Halo's own words for impact dust

The remaining constants are named and explained where they are defined:
- **Faction convention in `translate.py`:** Terrorist/Rebel/TF RED play red.
- **Start grounding tolerances:** 0.2 wu above and 1.5 wu below the origin.
- **Budgets and caps:** the texture budget equals the runtime cap; `HTA_EXTERNAL_SPAWN_LIFT`.
- **Placeholder palette:** keyed on `$surfaceprop`.

## 3. Maps tested

The same command for every map: `python -m assetlab convert <bsp> --output … --report-dir … --game-dir <each mounted content dir>`. Nothing was staged or bundled except de_dust2 (the existing reference). Sources: the owner's installed CS:S client, Garry's Mod and Black Mesa, the anonymous TF2 dedicated server, and the reference dust2. Packages and reports stayed in private scratch space.

| map | game, character | BSP | triangles | collide | disp | materials ok/placeholder | props placed | spawns R/B/any | package |
|---|---|---|---|---|---|---|---|---|---|
| de_dust2 | CS:S, reference; mounted CS:S only | v20 | 94,605 | 48,665 | 69/69 | 133/0 | 315/321 + 9 ent | 20/20/0 | 120 MiB |
| cs_office | CS:S, indoor brushwork, low ceilings | **v19** | 286,361 | 245,192 | 75/75 | 401/0 | 324/324 + 226 ent | 20/20/0 | 144 MiB |
| de_aztec | CS:S, outdoor displacements, river | **v19** | 60,007 | 45,967 | 283/283 | 167/8 | 128/128 + 16 ent | 20/20/0 (1 rejected) | 133 MiB |
| de_inferno | CS:S, static-prop heavy | v20 | 682,547 | 486,463 | 113/113 | 463/3 | 547/547 + 205 ent | 20/20/0 | 167 MiB |
| koth_bagel_rc2a | TF2, displacement heavy (757), missing textures | v20 | 832,087 | 514,840 | 757/757 | 12/229 | 1211/1211 + 15 ent | 16/16/0 | 97 MiB |
| gm_construct | GMod, mounted *without* HL2 content (missing deps) | v20 | 66,099 | 41,777 | 110/110 | 13/179 | 106/182 + 1 ent | 0/0/33 | 94 MiB |
| gm_flatgrass | GMod, huge flat open map | v20 | 14,361 | 14,361 | 16/16 | 16/0 | 1/1 | 0/0/56 | 31 MiB |
| dm_crossfire | Black Mesa DM, prop lump v11, MDL v49 props | v20 | 1,474,976 | 601,172 | 381/381 | 622/135 | 1808/2215 + 141 ent | 0/0/17 | 206 MiB |

Open Halo host results (lavapipe; the same loader, collision and nav code as Android):

| map | load | GPU | spawns usable | fell out | bot kills, 8 bots team 2 min (seeds 1, 2) | ms/tick |
|---|---|---|---|---|---|---|
| de_dust2 | 92 ms | 164 MiB | 40/40 | 0 | 14, 20 | 1.2 |
| cs_office | 125 ms | 193 MiB | 40/40 | 0 | 6, 24 | 1.2–1.3 |
| de_aztec | 98 ms | 181 MiB | 40/40 | 0 | 15, 13 | 1.3–1.7 |
| de_inferno | 150 ms | 215 MiB | 40/40 | 0 | 17, 20 | 1.7–1.8 |
| koth_bagel_rc2a | 105 ms | 119 MiB | 32/32 | 0 | 16, 15 | 1.4–1.5 |
| gm_construct | 61 ms | 130 MiB | 33/33 | 0 | 37, 33 | 1.2 |
| gm_flatgrass | 23 ms | 47 MiB | 56/56 | 0 | 21, 17 | 1.0–1.1 |
| dm_crossfire | 217 ms | 255 MiB | 17/17 | 0 | 3, 3 | 1.7–2.6 |

Before the audit's runtime fixes, cs_office and de_inferno scored **0** kills. On cs_office 15 of 40 bodies fell out of the map with the old 1 wu snap. dm_crossfire's low score is a real limit: its starts sit in several nav regions joined only by lifts and ladders, which the nav cannot use.

**Your question about dust2:** with the CS:S client's `hl2/` directory also mounted, de_dust2 has **0 missing dependencies**. All 321 static props and all 75 model entities resolve (122,638 triangles, 4 textures downsampled to the cap). The bundled build still mounts CS:S content only, as before; switching is a configuration change, not code.

## 4. What remains Source-version-specific (by table, explicitly)

- **BSP:** v19 and v20; face lump v1 (`dface_t`, 56 bytes). v21+ (L4D2, Portal 2, CS:GO) are refused with a reason.
- **Static prop lump:** v4–11, leading fields only. The v11 tail differs by game (CS:GO scale, Black Mesa something else), so it is not interpreted.
- **Models:** MDL v44–48, VVD v4, DX90 VTX v7, LOD 0, bind pose, body part defaults. **MDL v49** (Black Mesa, later games) is refused per model and listed.
- **Textures:** VTF 7.0–7.5 in 13 formats; HDR and float formats are refused and named.
- **VMT:** KeyValues with `include`/`patch`; `$basetexture` only.

## 5. What remains unsupported (reported per map, never silent)

- **Lighting:** lightmaps, HDR, light entities and cubemaps. Everything uses even daylight.
- **Collision:** clip and playerclip brushes are not imported, so bodies and the nav grid can reach ledges Source forbids. Physics hulls aren't used; collision uses visible triangles.
- **Surfaces:** overlays and decals, translucency, alpha test, normal, detail and environment maps, and blend layers are not drawn (listed per map). Water surfaces with no `$basetexture` get a placeholder colour.
- **3D skybox:** left out since 2026-09-24 (the sky_camera's area, when no start shares it); before that its geometry sat unscaled where it was built. The Halo sky is used and **stays** (owner's decision).
- **Moving parts:** doors, trains, rotators and buttons are frozen in their spawn pose. Ladders, lifts and teleports are not traversable.
- **Game logic:** Source entities, gamemodes and `lua_run` are not run.
- **Scale:** no prop scale and no triangle budget. Prop-heavy maps reach 0.7–1.5 M triangles, a phone performance risk not yet measured.
- **Big open maps:** these build very large nav grids (gm_flatgrass: 689k nodes, 3 s on the desktop). This matters for phone memory and load time.

## 6. Tests added

Asset Lab (`tests/test_pipeline.py`, 25 tests, synthetic fixtures only):
- **Geometry:** coordinate scaling, UV generation, face winding by plane side, displacement row order, shared vertices.
- **Versions and input safety:** BSP versions (v19 accepted; v18/v21 and face lump v0 refused), malformed lump bounds.
- **Entities and spawns:** entity tokenizer (braces in values, case, malformed blocks), team registry incl. TF2 `TeamNum`, rejected floating starts, brush entity registry (placed, hidden, non-solid, unknown class reported).
- **Faces and lumps:** surface flags counted and water non-solid, unused lumps reported.
- **Materials and textures:** KeyValues and `patch` materials, VTF frames and formats, texture budget, missing material colour from `$surfaceprop`.
- **Output:** compatibility report fields, deterministic package bytes.

Open Halo sandbox:
- **`test_external_map`:** team from the manifest.
- **`test_external_world` (19 checks):**
  - rooftop region trap
  - one-way ledge excluded from placement
  - far-corner collision on the fine grid
- **`open-halo-map-test`:** now simulates a body at every start.

## 7. How to reproduce

```sh
cd ~/projects/open-asset-lab
.venv/bin/python -m assetlab convert <map.bsp> --output /tmp/x/package.oalmap --report-dir /tmp/x \
    --game-dir "<Steam>/common/Counter-Strike Source/cstrike" --game-dir "<Steam>/common/Counter-Strike Source/hl2"
.venv/bin/python -m assetlab report /tmp/*/package.oalmap        # table + per-map Markdown
cd ~/projects/halo-trial-android    # branch halo-sandbox
VK_ICD_FILENAMES=$PWD/scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json ./build-host/open-halo-map-test /tmp/x/package.oalmap /tmp/x/view
VK_ICD_FILENAMES=… ./build-host/htamatch <bloodgulch.map> --oalmap /tmp/x/package.oalmap --bots 8 --mode team --seconds 120 --shots 0 --seed 1
```

Black Mesa maps live inside `bms_maps_dir.vpk`; extract one to a private scratch file first. Workshop integration has not been started.
