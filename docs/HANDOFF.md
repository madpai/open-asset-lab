# Handoff

Project: `/home/commander/projects/open-asset-lab`, branch `main`. Open Halo: `/home/commander/projects/halo-trial-android`, branch `fp-animated-guns`. Never commit real map/package/image artifacts. Local real test data: `/home/commander/assetlab-private/maps/`. Staging: `~/.local/share/open-asset-lab/staged/`.

Run `python -m unittest discover -s tests -v`. Build Open Halo with `cmake -S . -B build-host -G Ninja && cmake --build build-host`; run `scripts/verify.sh` with `HTA_MAP=/home/commander/halo-trial-data/extract/maps/bloodgulch.map` and `VK_ICD_FILENAMES=$PWD/scratch/lvp/usr/share/vulkan/icd.d/lvp_icd.json`. Host proof: `build-host/open-halo-map-test /path/to/package.oalmap /private/output-prefix`.

Service: `python -m assetlab serve --tailscale --source-dir /home/commander/assetlab-private/maps`. Access credentials: `python -m assetlab access`. Port 8762 is separate from Open Halo sideload port 8731. The phone was offline at initial verification; remote browser behavior still needs an actual device test. Current source map has many absent TF2 materials/props. Android has no external-map picker or runtime mode yet. See [PROGRESS.md](PROGRESS.md) for verified results and [OPEN_HALO_INTEGRATION.md](OPEN_HALO_INTEGRATION.md) before editing engine code.
