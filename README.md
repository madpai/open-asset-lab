# Open Asset Lab

Local Source BSP ingestion, conversion and staging for [Open Halo Project](https://github.com/madpai/open-halo-project). This first release converts Source 1 BSP v20 world geometry into a versioned `.oalmap` package. Open Halo's host Vulkan renderer loads it, builds collision and writes offscreen images. Android can also pick the staged package and explore its world geometry.

## What works today

- Inspect Source BSP v20, face lump v1, including compressed lumps, entities, static-prop inventory, embedded pakfile and missing material paths.
- Convert world faces, power 2–4 displacement surfaces and static prop models (MDL v44–48, LOD 0), positions, winding, UVs and supported player spawns. Resolve VMT/VTF from the BSP pakfile, explicitly configured material directories or read-only VPK archives. Unresolved materials display muted, material-specific placeholders and remain listed in diagnostics.
- Compile deterministic OALMAP v1 packages with bounds, indexed triangles, RGBA textures, spawn positions and a provenance manifest.
- Load packages in Open Halo's host `open-halo-map-test`, using its existing Vulkan renderer and triangle collision grid.
- Submit local or uploaded BSPs through a private web UI (no login; reachable only on localhost or your tailnet). A SQLite single worker continues after a browser disconnect; successful jobs enter a staged library with package, preview, reports and hashes.

## Limits

Android has a separate package picker and basic walking mode, pending device testing. It does not run Source or Halo game modes on imported maps. Source lightmaps, translucency/alpha-test, brush entities, Source game logic, Workshop browsing and most Source shader features are not implemented. Collision conservatively uses visible world triangles; clip brushes and invisible solids are absent. The demonstrated TF2 map still has 66 placeholder materials and 1,211 static props that are inventoried but not rendered. The Counter-Strike: Source dedicated-server package supplies de_dust2 and its textures through anonymous SteamCMD login; the TF2 files tested earlier omitted usable texture data archives. See [progress](docs/PROGRESS.md).

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
