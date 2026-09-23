# Session handoff — 2026-09-23 (generalization audit)

## Start of next session

1. Read [GENERALIZATION_AUDIT.md](GENERALIZATION_AUDIT.md) (the importer after the audit) and [MAP_IMPORT_PLAYBOOK.md](MAP_IMPORT_PLAYBOOK.md) (how to take a map to the phone).
2. Ask for phone results of the latest sandbox build: dust2 rebuilt with the audited importer, plus the roof-spawn fix, both still unconfirmed on the device.
3. The owner's long-term goal is **Garry's Mod Workshop content**. It is deliberately **not started**; do not begin it without being asked.
4. Owner's standing preferences: the **Halo sky stays** on imported maps (Source's 3D skybox is not to replace it). Imported-map work never goes to Open Halo's GitHub `main` (local branch `halo-sandbox`; a separate repository is planned, name not chosen).

## Generalization audit (2026-09-23) — summary

- **What was generalized:**
  - BSP version table (v19 + v20)
  - one coordinate module (`coords.py`)
  - a translation registry (`translate.py`) for starts and teams, brush entities, model entities, non-geometry entities, material policy and placeholder colours
  - an entity tokenizer and a KeyValues VMT parser
  - VTF format table with correct frame and face offsets
  - dependency search by `--game-dir`
  - texture budget, vertex sharing, rejected starts
  - a per-lump used/not-needed/unsupported report
  - a per-map `compatibility.json`/`.md`, also staged by the portal and printed by `assetlab report`
  - Open Halo side: teams read from the package, not class names; spawn lift for imported maps; item/flag placement on directed-reachable nodes; host test simulates a body at every start
- **Still Source-version-specific (explicit tables):** BSP v19/v20, face lump v1, static props v4–11 (leading fields), MDL v44–48, VVD v4, VTX v7, VTF 7.0–7.5 (13 formats).
- **Unsupported (reported per map):**
  - lightmaps and lights
  - clip brushes
  - overlays and decals
  - alpha, translucency and other shader layers
  - 3D skybox scaling (Halo sky kept on purpose)
  - moving brushes, ladders and lifts
  - game logic and Lua
  - MDL v49
  - prop scale
  - a triangle budget
- **Maps tested:** de_dust2, cs_office (v19), de_aztec (v19), de_inferno, koth_bagel_rc2a, gm_construct (without HL2, missing dependencies), gm_flatgrass, Black Mesa dm_crossfire. All eight convert through one command, load, render and collide in Open Halo, ground every shipped start and keep bodies in the map, and play 8-bot matches. Numbers are in the audit.
- **Map-specific hacks remaining:** none found. The remaining constants are named conventions or runtime caps, listed in the audit.

## Where things are

- **This repo** (public, `madpai/open-asset-lab`, branch `main`): importer, packager, no-login portal. Pushed. Tests: `.venv/bin/python -m unittest discover -s tests -v` (25 pass; synthetic fixtures only).
- **Open Halo sandbox** (`~/projects/halo-trial-android`, local branch **`halo-sandbox`**, never pushed): matches on imported maps. The owner's rule: imported-map work is a separate "Halo Garry's Mod" project and must **not** reach Open Halo's GitHub `main`. `fp-animated-guns`/`main` stay strictly Halo. See its `docs/HANDOFF.md` "IMPORTED MAPS".
- **Portal**: user systemd `open-asset-lab.service`, `http://100.89.1.14:8762/`, bound to Tailscale only, **no login** (removed at the owner's request; the tailnet is the boundary). Mutations still need the `X-OAL-Request` header and a same-origin `Origin`. Linked from Open Halo's sideload page. The service's VPK list is TF2 server + the CS:S server's `cstrike_pak_dir.vpk`. The owner has since installed the CS:S client, Garry's Mod and Black Mesa under `~/.local/share/Steam/steamapps/common/`; they may be used as **test inputs** (conversions to scratch, not bulk-staged). The CS:S client's `hl2/` has HL2's texture archives, unlike the server install.
- **Private data** (never commit): `~/assetlab-private/` — `css-server/` (SteamCMD CS:S dedicated server incl. `hl2/`), `maps/` (registered BSPs), `bundle/*.oalmap` (what the personal APK bundles), TF2 server install (textures missing), `koth_bagel_rc2a.bsp`.

## Current de_dust2

Stage `de_dust2-3e24a3cf2954-289842cc` (audited importer, CS:S content only): 94,605 triangles (48,665 solid), 315 of 321 props + 9 physics-prop entities, 0 placeholders, 20 red / 20 blue starts, 120 MiB. Bundled as `~/assetlab-private/bundle/de_dust2.oalmap`. Mounting the CS:S client's `hl2/` too gives 0 missing dependencies (all 321 props, 75 model entities) - an owner decision, not bundled. Earlier phone result (previous importer): 120 fps, bots fight, Team Slayer/CTF work.

## Package format changes this session

OALMAP stays v1. The group record's fourth word (was reserved 0) is now flags; bit 0 = drawn but not collided with (Source `SOLID_NONE` props). Older readers ignore it. See [RUNTIME_PACKAGE.md](RUNTIME_PACKAGE.md). The manifest now carries `static_props_placed` and `static_props_unresolved`.

## History

[PROGRESS.md](PROGRESS.md) has the dated log (TF2 texture attempt, first staged maps, the VTF mip fix, displacements, props). The TF2 client-texture work is paused: the dedicated server's `tf2_textures_dir.vpk` has no data archives and a client install needs the owner's own Steam login (never ask for a password or Guard code in chat).
