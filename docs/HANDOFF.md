# Session handoff — 2026-09-24 (ctf_2fort, TF2 and HL2 weapons)

## Start of next session

0. **All five bundled maps re-imported (2026-09-24, sandbox build after `99ee632`)** with alpha surfaces, the skybox cut, open doors, additive cut and flag points. Same commands as before; dust2 now from the CS:S client with its hl2 dir (0 missing).
0. **ctf_2fort and three weapons (2026-09-24)** -- sandbox build `5b64d7d`, phone test pending. See "ctf_2fort" below. Ask for fps / load time / holes before touching 2fort again.
1. **Characters and weapons are implemented (2026-09-23, late)** -- see "Characters and weapons" below. First phone test pending: player model in Settings, custom classes with the AK-47 in SINGLEPLAYER / CREATE GAME. Ask for the result before extending.
2. Imported maps on the phone (sandbox build `8c25abc`): **cs_office and gm_construct run at 120 fps and are "almost complete with some problems"**. The owner does not want to work on those problems now. de_aztec has no report yet; dust2 has an earlier phone pass.
3. The **Garry's Mod Workshop** is the long-term goal but is **not started**. Keep the **Halo sky**. Imported work never goes to Open Halo's GitHub `main` (local branch `halo-sandbox`; a separate repository is planned, name not chosen).

## ctf_2fort (2026-09-24)

- **Command:** `convert <TF2>/tf/maps/ctf_2fort.bsp --prop-lod 1 --game-dir <TF2>/tf --game-dir <TF2>/hl2`. 0 missing dependencies; 1,243,866 triangles (1.69M at LOD 0), 210 MB, texture budget full (385 of 479 downsampled).
- **New importer behaviour (applies to every map on its next conversion):**
  - `--prop-lod N`: props and model entities drawn at VTX LOD N, or the coarsest a model ships (every LOD indexes the same LOD 0 vertex list). Only a third fewer triangles on 2fort: many TF2 props have one LOD.
  - **3D skybox left out**: the sky_camera's BSP area (nodes + leaves are now read), when no player start shares it. Faces by centroid, props and brush entities by origin. Owner's call to keep the Halo sky makes the skybox a floating miniature otherwise.
  - **func_door imported open** at Source's m_vecPosition2 (movedir, brush size, lip); models parented to a door move with it. Nothing opens doors in Open Halo; closed they sealed 2fort's spawn rooms.
  - **Additive materials not drawn** (`$additive 1`: light shafts, glows); drawn opaque they were black slabs.
  - **Alpha surfaces** (`$alphatest`, `$translucent`): group flag bit 1, drawn in Open Halo's alpha pass -- fences, hay, cobwebs, glass were black cut-outs.
  - **flag_points** in the manifest from `item_teamflag` (TeamNum 2 red, 3 blue); Open Halo stands the CTF flags there.
- **Open Halo engine fixes it needed (sandbox):** a 0.175 wu bot grid on imported maps (TF2 doorways are body-wide), floors under more than six stacked surfaces, links need room for a body's sides (slatted railings), no push through a one-sided wall into the void. Bots now fight on 2fort (~35 kills / 5 min) but have not captured a flag in tests.

## TF2 and HL2 weapons (2026-09-24)

- `assetlab/data/weapons/tf2_rocketlauncher.json`, `tf2_scattergun.json` (TF2's legacy `v_models/` view models, arms included; right-handed), `hl2_357.json` (GMod's `sourceengine` HL2 content, HEV hands).
- **`world_grip`** in a definition: an attachment for a world model with no weapon bone (HL2's `w_357` is a pickup lying on its side). The .357's value was worked out from mesh extents against the AK and checked by render; Open Halo now bone-merges through weapon attachments as well as bones.
- TF2's modern `c_models` (arms + separate weapon, animations on the arms) are not supported; the legacy `v_models` still ship and are used instead.

## Characters and weapons (done 2026-09-23, late)

- **Commands** (same search-path rules as maps; `--game-dir` per content folder):
  ```sh
  .venv/bin/python -m assetlab character models/player/t_leet.mdl --hold ak --output X.oalasset --game-dir ".../Counter-Strike Source/cstrike" --game-dir ".../Counter-Strike Source/hl2"
  .venv/bin/python -m assetlab character models/player/kleiner.mdl --hold ar2 --output X.oalasset --game-dir ".../GarrysMod/garrysmod" --game-dir ".../GarrysMod/sourceengine"
  .venv/bin/python -m assetlab weapon assetlab/data/weapons/cs_ak47.json --output X.oalasset --game-dir ...
  ```
- **Code:**
  - `importers/source_studio.py` reads MDL v44-48 skeletons, attachments, pose parameters, include models and `.ani` animation blocks. It decodes RLE/RAWROT/RAWROT2/RAWPOS/ANIMROT/ANIMPOS tracks and handles delta layers and weight lists.
  - `character.py` bakes clips by role from `translate.CHARACTER_ROLES`:
    - GMod/HL2MP family: `ACT_HL2MP_*_{HOLD}` full-body sequences.
    - CS:S family: lower-body activity plus a `{Idle|Run|...}_Upper_{hold}` layer.
    - Move directions in 3x3 blend grids are picked by each cell's root motion, falling back to the move_x/move_y pose parameters.
  - Viewmodel clips map by `ACT_VM_*`. Weapon sounds are PCM WAVs decoded into the package.
- **Format:** OALASSET v1, documented in `character.py`'s docstring.
  - Characters: one skinned model. Weapons: a world model and a view model, plus the definition's stats relative to a base Halo weapon.
  - Weapon definitions are data in `assetlab/data/weapons/`. The AK-47's stats are its published CS:S values, stated as provenance.
- **Grip for bodies without a weapon bone:** `translate.SYNTH_GRIPS` adds `ValveBiped.weapon_bone` as an attachment on the right hand. The value was measured from CS:S's rifle idle.
- **What's missing, and is reported:**
  - Death animations: CS:S and GMod ragdoll instead, so Open Halo topples the body.
  - Gesture layers (fire/reload on the body).
  - Aim matrices.
  - Facial flexes.
  - Viewmodel FOV (CS:S draws at 54 degrees).
  - LAN sync of characters and classes.
- **Built packages (private, `~/assetlab-private/bundle/{characters,weapons}`):** `t_leet`, `ct_urban`, `kleiner`, `alyx`, `ak47`. Also available locally but not built: GMod's Breen, G-Man and a citizen; CS:S `t_phoenix` and other skins. There is no Gordon player model anywhere; GMod has only the HEV arms (`c_arms_hev`).

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
