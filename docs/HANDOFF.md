# Session handoff — 2026-09-23 (end of day)

## Start of next session

1. Read [MAP_IMPORT_PLAYBOOK.md](MAP_IMPORT_PLAYBOOK.md): the whole de_dust2 pipeline, every bug it hit, and a dry run of the other stock CS:S maps.
2. The owner plans to try **another map**. Best candidate: **de_dust** (v20, 298 props, 1 placeholder, textures 126 MiB, just under Open Halo's 128 MiB cap). Most other stock maps need BSP v19 support or texture/triangle budgets first (playbook, "Work the next maps need").
3. Ask for the owner's phone screenshots of the latest sandbox build (`bd20c08`, spawn fix) if they have not arrived; they land in Open Halo's `scratch/uploads/`.

## Where things are

- **This repo** (public, `madpai/open-asset-lab`, branch `main`): importer, packager, no-login portal. Pushed. Tests: `.venv/bin/python -m unittest discover -s tests -v` (11 pass; synthetic fixtures only).
- **Open Halo sandbox** (`~/projects/halo-trial-android`, local branch **`halo-sandbox`**, never pushed): matches on imported maps. The owner's rule: imported-map work is a separate "Halo Garry's Mod" project and must **not** reach Open Halo's GitHub `main`. `fp-animated-guns`/`main` stay strictly Halo. See its `docs/HANDOFF.md` "IMPORTED MAPS".
- **Portal**: user systemd `open-asset-lab.service`, `http://100.89.1.14:8762/`, bound to Tailscale only, **no login** (removed at the owner's request; the tailnet is the boundary). Mutations still need the `X-OAL-Request` header and a same-origin `Origin`. Linked from Open Halo's sideload page. The service's VPK list is TF2 server + `cstrike_pak_dir.vpk`; it does **not** include the HL2 VPKs (they add HL2 props but only placeholder textures; decide per map).
- **Private data** (never commit): `~/assetlab-private/` — `css-server/` (SteamCMD CS:S dedicated server incl. `hl2/`), `maps/` (registered BSPs), `bundle/*.oalmap` (what the personal APK bundles), TF2 server install (textures missing), `koth_bagel_rc2a.bsp`.

## Current de_dust2

Stage `de_dust2-3e24a3cf2954-7ec0e144`: 94,143 triangles (48,203 solid), 315 of 321 props (six HL2 cars absent), 0 placeholders, textures 118 MB, package 130,645,616 bytes, 40/40 spawns on ground, byte-identical to the desktop conversion. Bundled as `~/assetlab-private/bundle/de_dust2.oalmap`. On the phone: 120 fps, bots fight, Team Slayer/CTF work; the owner reported the windows and roof spawns, both fixed.

## Package format changes this session

OALMAP stays v1. The group record's fourth word (was reserved 0) is now flags; bit 0 = drawn but not collided with (Source `SOLID_NONE` props). Older readers ignore it. See [RUNTIME_PACKAGE.md](RUNTIME_PACKAGE.md). The manifest now carries `static_props_placed` and `static_props_unresolved`.

## History

[PROGRESS.md](PROGRESS.md) has the dated log (TF2 texture attempt, first staged maps, the VTF mip fix, displacements, props). The TF2 client-texture work is paused: the dedicated server's `tf2_textures_dir.vpk` has no data archives and a client install needs the owner's own Steam login (never ask for a password or Guard code in chat).
