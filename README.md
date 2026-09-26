# Open Asset Lab

A local content **ingestion, analysis, normalization, conversion,
validation and packaging** environment that turns heterogeneous game
assets into clean runtime content for
[MegaMod](https://github.com/madpai/megamod-showdown), the native
content-driven engine behind MEGAMOD SHOWDOWN. It is growing into a
general content compiler and, eventually, creator tooling.

**Today** its content family is **Source and Garry's Mod**: it converts
Source BSP v19/v20 maps into `.oalmap` packages and Source characters and
weapons into `.oalasset` packages. Steam Workshop is its first
**acquisition provider**. The host Vulkan tools render and validate
packages, and MEGAMOD SHOWDOWN plays matches on the owner's privately
converted content. Source is the first importer family, not the permanent
identity: next come original content (glTF from Blender) and other formats.
**The direction, with what exists now versus what is planned, is
[`docs/ASSET_LAB_VISION.md`](docs/ASSET_LAB_VISION.md)**, the companion to
MegaMod's canonical
[`MEGAMOD_VISION.md`](https://github.com/madpai/megamod-showdown/blob/main/docs/MEGAMOD_VISION.md).

## What works today

- Convert Source characters (skeleton, skin weights, animations baked by role) and weapons (world and view models, clips, sounds, stats) into `.oalasset` packages: `assetlab character` and `assetlab weapon`.
- Read exact Garry's Mod Workshop addon archives with `assetlab gma`, including `.gma` and supported `_legacy.bin` files. Workshop downloads and converted packages stay outside this public repository.
- **Search, fetch and import from the Steam Workshop** (Garry's Mod by default) with `assetlab workshop`, or from the web UI's Workshop panel: search needs no API key; items download directly or through anonymous SteamCMD; each addon is analyzed for playermodels (with the names and hands it registers), SWEPs (drafted into weapon definitions), NPCs and maps; import builds the packages and reports what failed and why.
- Modern playermodels: MDL v44-v49.
- Inspect Source BSP v19 and v20, face lump v1, including compressed lumps, entities, static-prop inventory, embedded pakfile and missing material paths.
- Convert world faces, power 2–4 displacement surfaces and static prop models (MDL v44–48, LOD 0), positions, winding, UVs and supported player spawns. Resolve VMT/VTF from the BSP pakfile, explicitly configured material directories or read-only VPK archives. Unresolved materials display muted, material-specific placeholders and remain listed in diagnostics.
- Compile deterministic OALMAP v1 packages with bounds, indexed triangles, RGBA textures, spawn positions and a provenance manifest.
- Load packages in Open Halo's host `open-halo-map-test`, using its existing Vulkan renderer and triangle collision grid.
- Submit local or uploaded BSPs through a private web UI (no login; reachable only on localhost or your tailnet). A SQLite single worker continues after a browser disconnect; successful jobs enter a staged library with package, preview, reports and hashes.

## Limits

MEGAMOD SHOWDOWN is in a separate public repository; Open Halo's public
`main` stays Halo-only. Only Source-family formats are imported so far,
and Workshop acquisition is not yet separated from GMod addon
interpretation (see the vision's current-state table). Megamod's published 2026-09-24 personal build has
five imported maps, 12 characters and 11 imported weapons. Its latest hero
roster and two-device rules still need phone feedback. BSP v21+ is refused
with a reason. Static LDR Source lightmaps are available through `convert --lightmaps` (OALMAP v2). Overlays, clip brushes, live moving brushes,
game logic and most shader features are not implemented;
alpha-test/translucent surfaces are supported in the current map packages.
Each map's `compatibility.md` lists what it lost. Collision uses visible
world triangles, solid brush entities and solid props. Textures are
downsampled to fit the runtime budget. See the
[current handoff](docs/HANDOFF.md), [progress](docs/PROGRESS.md) and
[generalization audit](docs/GENERALIZATION_AUDIT.md).

## Install

Requires Python 3.11+, Pillow, srctools and a built Open Halo host tool for staged render validation. On this machine the compiler, CMake, Ninja, Vulkan and Android toolchain were already installed. No system package installation was needed.

```sh
cd /home/commander/projects/open-asset-lab
python -m venv .venv
.venv/bin/pip install -e .
cd ../halo-trial-android
cmake -S . -B build-host -G Ninja
cmake --build build-host --target open-halo-map-test
```

Alternatively, from this checkout run `python -m assetlab` with the system Python if Pillow is installed.

## Inspect and convert

```sh
python -m assetlab inspect /path/to/map.bsp
python -m assetlab inspect /path/to/map.bsp --json
python -m assetlab convert /path/to/map.bsp --output /private/path/map.oalmap
# Mount a game's content the way Source does (the folder and every *_dir.vpk in it), and write a compatibility report:
python -m assetlab convert /path/to/map.bsp --output /private/path/map.oalmap --game-dir "/path/to/Counter-Strike Source/cstrike" --game-dir "/path/to/Counter-Strike Source/hl2" --report-dir /private/path/report
python -m assetlab report /private/path/*.oalmap
# Optional unpacked materials directory; must contain materials/... paths:
python -m assetlab convert /path/to/map.bsp --output /private/path/map.oalmap --material-root /path/to/game
# Optional VPK directory files; include both material and texture archives as needed:
python -m assetlab convert /path/to/map.bsp --output /private/path/map.oalmap --vpk /path/to/tf2_misc_dir.vpk --vpk /path/to/tf2_textures_dir.vpk
```

`convert` writes the package only. The web job runs Open Halo validation and stages it. Direct host proof:

```sh
cd /home/commander/projects/halo-trial-android
VK_ICD_FILENAMES=$PWD/scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json \
  ./build-host/open-halo-map-test /private/path/map.oalmap /private/path/preview
# writes preview_overview.ppm and preview_spawn.ppm
```

The saved lavapipe ICD is needed on this desktop because the native NVIDIA Vulkan instance creation currently fails. On a working GPU, omit `VK_ICD_FILENAMES`.

## Steam Workshop

```sh
python -m assetlab workshop search "harry potter" --tag Model            # Model, Weapon, Map, NPC, Vehicle
python -m assetlab workshop search ak47 --tag Weapon --sort popular      # relevance, popular, recent, subscribed, rated
python -m assetlab workshop info https://steamcommunity.com/sharedfiles/filedetails/?id=3563673673
python -m assetlab workshop collection <collection id>                    # what it holds (nested collections too)
python -m assetlab workshop import-collection <collection id> --install-steamcmd --output-dir /private/out \
    --game-dir "<GarrysMod>/garrysmod" --game-dir "<GarrysMod>/sourceengine" [--limit 50] [--dry-run]
python -m assetlab workshop analyze <id | .gma | _legacy.bin | folder> --install-steamcmd
python -m assetlab workshop import <id> --install-steamcmd --output-dir /private/out \
    --game-dir "<GarrysMod>/garrysmod" --game-dir "<GarrysMod>/sourceengine" [--only characters,weapons,maps] [--pick NAME] [--dry-run]
```

Search reads the Workshop's public browse page (no key); set `STEAM_WEB_API_KEY` to use `IPublishedFileService/QueryFiles` instead. Items that still carry a direct file URL (older ones) download over HTTPS; the rest need SteamCMD, which `--install-steamcmd` fetches from Valve (it is 32-bit: Debian/Ubuntu need `lib32gcc-s1`). Garry's Mod playermodels take their animations from the game, so mount its `garrysmod` and `sourceengine` folders. Weapon definitions drafted from a SWEP's Lua are written beside each package for review; their numbers are estimates. `workshop_report.json` lists what was built, what failed and why.

A collection imports item by item, each into its own folder under `--output-dir`, with `collection_report.json` summing up; one broken item never stops the rest. Gamemodes and entity/tool/effects addons are skipped (they hold nothing to build, and some are gigabytes); import one by itself to try it anyway. In the web service, **Import collection** queues the same way (up to 50 items, at most 64 unfinished jobs), skipping private, banned, oversized (4 GiB) and already-imported items and saying why.

## Private web service

```sh
cd /home/commander/projects/open-asset-lab
python -m assetlab serve --source-dir /private/path/to/maps --vpk /private/path/to/tf2_misc_dir.vpk --vpk /private/path/to/tf2_textures_dir.vpk
# localhost only: http://127.0.0.1:8762
python -m assetlab serve --tailscale --source-dir /private/path/to/maps
# binds only the Tailscale IPv4 address, port 8762
```

On this desktop the Tailscale address is currently `http://100.89.1.14:8762`. From your phone on the same tailnet, open that address; there is no login. Open Halo's sideload page (`http://100.89.1.14:8731/`) links to it as **Open Asset Lab**. Port 8762 avoids Open Halo's sideload port 8731. The service accepts only registered local directory entries or BSP uploads; web clients cannot submit filesystem paths. Upload limit is 128 MiB, with a 2 GiB upload library cap. Anyone who can reach the port can use the service, so bind to Tailscale only when remote access is wanted and never to a public interface. For a persistent desktop service, adapt [the user-systemd template](scripts/open-asset-lab.service.example), then run `systemctl --user daemon-reload && systemctl --user enable --now open-asset-lab.service`. This desktop has that user service enabled.

```sh
python -m assetlab staged
python -m unittest discover -s tests -v
```

The default library is `~/.local/share/open-asset-lab/`, with `jobs.sqlite3`, `uploads/`, `work/`, and `staged/index.json`. Jobs have bounded logs and a single worker. If the service restarts during a job, unfinished jobs requeue. The staged list shows resolved texture and missing dependency counts. Earlier staged packages retain their original checkerboard previews; select the newest stage for the updated placeholder preview.

## Reproduce the demonstrated host milestone

The real `koth_bagel_rc2a.bsp` test map is **not** in this public repository. It was downloaded for local validation from [icewind1991/vbsp](https://github.com/icewind1991/vbsp/blob/master/koth_bagel_rc2a.bsp) and kept under `/home/commander/assetlab-private/maps/`. That repository's MIT license does not by itself prove redistribution rights for the map, so this project does not publish it or its converted output. With a lawfully obtained copy:

```sh
python -m assetlab inspect /private/maps/koth_bagel_rc2a.bsp
python -m assetlab convert /private/maps/koth_bagel_rc2a.bsp --output /private/koth_bagel_rc2a.oalmap
cd ../halo-trial-android
VK_ICD_FILENAMES=$PWD/scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json \
  ./build-host/open-halo-map-test /private/koth_bagel_rc2a.oalmap /private/render
```

The inspected local file had SHA-256 `a8e448254566...`; see [PROGRESS.md](docs/PROGRESS.md) for exact measurements and limitations. The public tests synthesize their own BSP bytes and include no game content.

## Legal

Code is GPL-3.0-or-later, compatible with Open Halo's GPLv3 code. Valve's BSP definitions were used as a format reference, not copied into this repository. You are responsible for rights to source content and converted output. Workshop availability does not grant redistribution rights. No Halo assets, Source game assets, Workshop downloads, credentials or converted proprietary maps belong in this repository.
