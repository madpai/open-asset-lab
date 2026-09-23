# Map import playbook

How de_dust2 went from a Counter-Strike: Source BSP to a playable Open Halo match (2026-09-23), and the checklist for the next map. Real maps, packages and textures stay private under `~/assetlab-private/`; nothing here is published except code and these notes.

## The pipeline

1. **Source files.** SteamCMD anonymous login installs the CS:S dedicated server (app 232330) at `~/assetlab-private/css-server/`. It has every stock CS:S map (`cstrike/maps/*.bsp`), the CS:S content VPK (`cstrike/cstrike_pak_dir.vpk` + numbered archives), and HL2 **models** (`hl2/hl2_misc_dir.vpk` + archives). It does **not** have HL2 **texture data** (`hl2_textures_dir.vpk` is present but its numbered archives are not), so HL2-shared textures become placeholders.
2. **Convert.** Through the portal (`http://100.89.1.14:8762/`, no login, Tailscale only): tap Convert on a registered map. Or on the desktop:
   ```sh
   cd ~/projects/open-asset-lab
   H=~/assetlab-private/css-server
   .venv/bin/python -m assetlab convert $H/cstrike/maps/<map>.bsp --output /tmp/<map>.oalmap \
       --vpk $H/cstrike/cstrike_pak_dir.vpk   # add --vpk $H/hl2/hl2_misc_dir.vpk for HL2 props
   ```
   The portal job also runs Open Halo's host render/collision test and stages `package.oalmap`, `preview.png`, `report.json`, `manifest.json` under `~/.local/share/open-asset-lab/staged/<map>-<hash>-<job>/`. Conversion is deterministic: the portal package and a desktop conversion of the same inputs are byte-identical, so a desktop test result also applies to the portal stage.
3. **Check the report** (`report.json`): `static_props_placed` / `static_props_unresolved`, `placeholder_materials`, `missing_dependencies`, `texture_bytes` (**must stay under 128 MiB**: Open Halo refuses more), `runtime_package_bytes` (under 256 MiB), `warnings` (spawns without ground).
4. **Look at it on the desktop** before any phone build (from `~/projects/halo-trial-android`, with `VK_ICD_FILENAMES` set to the lavapipe ICD in `scratch/lvp`):
   - `build-host/open-halo-map-test pkg.oalmap /tmp/out` — load, collision (`N of M triangles solid`), every spawn's ground, two renders.
   - `OALMAP_CAMERA="x y z yaw pitch" build-host/open-halo-map-test pkg.oalmap /tmp/out` — render the exact spot from a phone screenshot (the HUD's debug line shows `x y z`; eye height is about z+0.6).
   - `build-host/htamatch <bloodgulch.map> --oalmap pkg.oalmap --bots 8 --mode team --seconds 120 --shots 0 --seed N` for seeds 1-4, and `--mode ctf` / `ffa`. Watch kills (dust2: ~11-18 per 2 min in team slayer) and **ms per tick** (dust2 ~1.2 ms; Blood Gulch ~1.3). `HTA_DEBUG_UNITS=1` with `--shots` prints every unit's position and all item placements.
5. **Bundle.** Copy the staged package to `~/assetlab-private/bundle/<name>.oalmap` (`<name>` is what the MAP row shows, `[a-z0-9_-]`). On the `halo-sandbox` branch of Open Halo: `scripts/publish_apk.sh --with-assets --title ...`. It goes into the personal APK only; never to GitHub.

## What broke on de_dust2, and why (check these first on the next map)

| Symptom on the phone | Cause | Fix / where |
|---|---|---|
| Shredded brown ribbons in the sky, holes and dark slivers in the sand | Displacement grids built transposed: Valve's `CCoreDispInfo` advances the **row** index p0→p1 and the column p0→p3 | `source_bsp.py`; measured 1,195 vs 76 of 2,064 edge vertices shared with neighbours; regression test |
| Sky visible through window recesses; no crates, domes, palms | Static props (321 on dust2, lump **v6**) were skipped | `importers/source_mdl.py` (MDL v44-48, VVD v4, DX90 VTX v7, LOD 0) + `SourceBSP.static_prop_placements` (v4-v10) |
| Bots stand still all match | Nav's largest region was dust2's **rooftops** | Open Halo `hta_nav_main_from_spawns` |
| Bots stand under an item forever | Nav reaches ledges the body cannot (no clip brushes imported) | Open Halo `brain.c` item give-up |
| 3.5x slower ticks after props | Failed A* searches (one-way drops) retried every frame | Open Halo `plan_wait` per goal node |
| Palm fronds / window frames block | Source `SOLID_NONE` props | group flag bit 0 = no collision |
| Respawn on a roof outside the map (22 of 40 starts) | Player start snapped to ground from 8 wu above | Open Halo `spawn_lift()` = 1 wu on imported maps |
| App crashed on launch | Map list read in a field initializer before the Activity had a context | Open Halo `findMaps()` |
| VTF garbage / fails | Mip count read from byte 63 instead of 56 | `package.py _vtf_rgba` |

## Other stock CS:S maps (dry run 2026-09-23, not staged)

With `cstrike_pak_dir.vpk` only / with the HL2 VPKs added:

| map | BSP | triangles | props placed | placeholders | textures | verdict |
|---|---|---|---|---|---|---|
| de_dust2 | v20 | 94k / 110k | 315 / 321 | 0 / 6 | 113 MiB | done (bundled without HL2 VPKs) |
| de_dust | v20 | 90k / 104k | 298 / 304 | 1 / 7 | 126 MiB | **best next candidate**; texture budget right at the cap |
| de_train | v20 | — / 383k | 384 / 679 | 46 / 72 | 120 MiB | needs a triangle budget (HL2 props are dense) |
| de_nuke | v20 | — / 524k | 405 / 680 | 83 / 106 | 332 MiB | needs texture downsampling + triangle budget |
| de_inferno | v20 | — / 568k | 470 / 547 | 53 / 74 | 368 MiB | same |
| cs_militia | v20 | — / 547k | 362 / 393 | 29 / 38 | 576 MiB | same |
| cs_assault, cs_compound, cs_havana, cs_italy, cs_office, de_aztec, de_cbble, de_chateau, de_piranesi, de_port, de_prodigy, de_tides | **v19** | — | — | — | — | importer refuses v19 |

## Work the next maps need, in order of payoff

1. **BSP v19** (12 of the 18 stock maps). v19 and v20 share the lump layout the importer reads; the differences are mostly HDR lighting lumps (unused here) and the face lump version. Accept 19 behind the same bounds checks and prove it on de_aztec or cs_office with the host test.
2. **Texture budget.** Downsample textures (halve the largest until the package's RGBA total fits, e.g. ≤ 96 MiB for phone headroom). A 2048² VTF is 16 MiB as RGBA; most CS:S world textures are 512-1024.
3. **Triangle budget for props.** Use a lower VTX LOD for skybox/distant props, or skip props whose model is `*_skybox*` / fade-distance limited, until a map stays under ~150k triangles.
4. **HL2 textures.** Need a full CS:S or HL2 client install (owner's own account; never ask for a password or Guard code in chat). Until then, HL2-shared surfaces are muted placeholders.
5. **Alpha-tested / translucent materials** (grilles, foliage, fences) render opaque. Carry `$alphatest`/`$translucent` into the package and teach the runtime a cutout pass.
6. **Clip brushes and player clips** are not imported: players and the nav grid can reach ledges and roofs Source forbids. Importing `CONTENTS_PLAYERCLIP` brushes as invisible collision would fix both at once.
