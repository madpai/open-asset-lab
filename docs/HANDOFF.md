# Session handoff — 2026-09-25 (Workshop search/import, MDL v49, breakables)

## This session (cloud container, branch `claude/vibrant-euler-xwhpy5`)

Merge into `main` after reading this. Verified in the container against the
live Steam Workshop; the owner's private bundle and GMod install were not
there, so re-run the owner's usual conversions on the desktop.

- **Workshop search, fetch, analyze, import** (`assetlab/workshop.py`):
  ```sh
  python -m assetlab workshop search superman --tag Model           # no key needed
  python -m assetlab workshop search ak47 --tag Weapon --sort popular
  python -m assetlab workshop info 3563673673
  python -m assetlab workshop analyze 3563673673 --install-steamcmd  # what is inside
  python -m assetlab workshop import 3563673673 --install-steamcmd \
      --output-dir ~/assetlab-private/bundle/new \
      --game-dir ~/.local/share/Steam/steamapps/common/GarrysMod/garrysmod \
      --game-dir ~/.local/share/Steam/steamapps/common/GarrysMod/sourceengine
  python -m assetlab workshop import 853797162 --only weapons --dry-run
  ```
  Downloads go to `~/.local/share/open-asset-lab/workshop/downloads` (a
  cache, trimmed past 8 GiB by the service); SteamCMD to
  `~/.local/share/open-asset-lab/steamcmd` (`ASSETLAB_STEAMCMD` or
  `--steamcmd` for the existing `~/assetlab-private/steamcmd`). SteamCMD is
  32-bit: a fresh machine needs `lib32gcc-s1`.
- **What analysis finds:** playermodels with their registered names and
  hands; NPC registrations (recognised as variants of a registered body,
  not extra characters); SWEPs drafted into `data/weapons`-format JSON
  (stock, M9K, TFA, CW, ArcCW names; RPM or Delay; sound scripts; bases and
  grenades skipped) -- **drafts: review the numbers before shipping**, the
  JSON sits beside each package; maps.
- **Web UI** (`serve`): a Steam Workshop panel -- search with thumbnails,
  type and sort, Import by ID/URL, queued jobs that fetch, analyze, build,
  validate with `open-halo-asset-test`/`open-halo-map-test` and stage.
  `--no-workshop` turns it off.
- **MDL v49** is read (modern Workshop playermodels). Its VTX strip-group
  headers are 33 bytes; the stride is chosen per file by what fits.
- **Cel-shading outline shells** (`outline` material with a black base
  texture) are dropped and listed in the package as
  `outline_materials_dropped` -- Open Halo draws both faces, so the shell
  hid the body. When the engine gets per-submesh culling, keep them.
- **Breakables and weather for Megamod:** `prop_physics*` are kept apart,
  flagged (group bit 2, index + 1 in bits 8..23), out of static collision,
  and listed in the manifest's `breakables`; `func_precipitation` becomes
  `weather`. **Re-convert maps** to get them (older packages have none and
  still load). `func_breakable` (by its `material`; health 0, spawnflag 1
  "break on trigger" and unbreakable glass stay plain solid walls) and
  `func_breakable_surf` (always glass) break too, from 2026-09-25; tested
  on a synthetic BSP only -- no real map with them has been converted yet.
- **Collections:** `workshop import-collection ID` (CLI) and **Import
  collection** (web) queue a whole collection, nested ones included,
  skipping gamemodes, entity/tool/effects addons, private/banned, >4 GiB
  and already-imported items with a reason each.
- **Proof run:** 'Superman: The Animated Series' (3563673673): SteamCMD
  fetch, v49 model, GMod animations, built with 0 missing dependencies,
  rendered textured and animated in `open-halo-asset-test`.
- Tests 56/56 (`test_workshop.py`, `test_breakables.py` new).

## Previous: 2026-09-24 (McRonalds, citizen fists, Workshop scan)

## Start of next session

1. **Revisions:** game `91a1679` on `halo-sandbox` (private `megamod/main`);
   importer `d075f13` on public `main`. **Current private bundle:** 12
   characters, 13 weapons, six maps
   (`de_dust2`, `cs_office`, `de_aztec`, `ctf_2fort`, `gm_construct`,
   `mcdonalds`). Packages stay in `~/assetlab-private/bundle`. The game
   handoff's testing objective is the phone pass. Protocol on the game
   side is v8.
2. **Next importer work, if the phone pass is clean:** the Workshop maps
   already downloaded and not converted — Backrooms `2732733089`,
   gm_abandoned_mall `2878375438`, gm_liminal_hotel `2556466049`,
   gm_construct_remaster `3334581973`. Same command shape as McRonalds.
3. **Do not treat a Workshop listing as a mesh.** Several fist addons are
   Lua or empty VVDs. Check vertex count and `ACT_VM_*` / sequence labels
   before rebuilding a weapon.
4. **Earlier map state:** all five bundled maps were re-imported with alpha,
   skybox, door and flag fixes. The owner reported about 120 fps on
   cs_office and gm_construct in an older build and parked their remaining
   issues. ctf_2fort has host bot play, but no current phone report.

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

## McRonalds (2026-09-24)

- Workshop `3159770816`, addon name `gm_mcronalds`. Three files:
  `maps/mcronald.bsp` (11.8 MB), `maps/mcronald.nav`, a thumbnail. No
  packed models. Anonymous SteamCMD delivered it.
- Convert:
  ```sh
  .venv/bin/python -m assetlab convert ~/assetlab-private/workshop/3159770816/maps/mcronald.bsp \
    --output ~/assetlab-private/bundle/mcdonalds.oalmap --prop-lod 1 \
    --report-dir ~/assetlab-private/workshop/3159770816/report \
    --game-dir ~/.local/share/Steam/steamapps/common/GarrysMod/garrysmod \
    --game-dir ~/.local/share/Steam/steamapps/common/GarrysMod/sourceengine
  ```
- BSP v20. 113,462 triangles (all solid), 42 static props, 186 model
  entities, 4 `info_player_start` (no teams), 0 missing dependencies,
  1 placeholder (`glass/reflectiveglass001`, lightmapped reflective, no
  `$basetexture`). Eight `func_conveyor` brushes unsupported. Texture
  bytes 118,763,584 (under the 128 MiB cap). Package 120 MB. Manifest
  `map_id` is `mcronald`; the bundle filename `mcdonalds.oalmap` is what
  the game menu lists (label MCRONALDS).
- Host: `open-halo-map-test` 4/4 spawns usable, 0 bodies out of the map.
  Offscreen overview shows the restaurant and lot; the spawn shot is the
  dining room. `htamatch` 4 bots, 45 s Slayer: 3 kills, 0.787 ms/tick.
  The menu label and phone frame rate are not yet confirmed.

## Fist viewmodels and included skeletons (2026-09-24)

- `translate.VIEWMODEL_ROLES` now accepts `ACT_VM_FISTS_IDLE` and
  `seq:<label>`. `fists.json`, `ki_bolts.json`, and `repulsors.json` use
  `models/weapons/c_arms_citizen.mdl`. Built clips: idle `fists_idle_01`,
  fire `fists_left`, draw `fists_draw`. 2979 package verts, no missing
  materials. Offscreen idle shows two fists; the fire frame is a left hook.
- Workshop items that do **not** replace that mesh: Hands SWEP
  `852703807` (Lua and icons), Fighting Fists `954655623` (24-vert
  `c_fists.vvd`, material `no_material`), Zombie SWEP `2371481770` and
  parkour hands `2923379220` (animation MDLs, 64-byte empty VVDs).
- `character.py` retargets absolute poses from an included MDL onto this
  model's bind (citizen neck vs a custom player neck). The game also
  refuses a Head/Neck key whose position is much shorter than the bind,
  so already-built Superman and Goku packages keep their heads without a
  rebuild. A future character rebuild picks up the baker fix.

## Garry's Mod Workshop (2026-09-24)

- Fetch: `~/assetlab-private/steamcmd/steamcmd.sh +login anonymous +workshop_download_item 4000 <id> +quit` (lands in `~/.local/share/Steam/steamapps/workshop/content/4000/<id>/`). Use an exact item ID: collection downloads may contain only a thumbnail. A removed Workshop page does not always mean the archived item is unavailable; inspect SteamCMD's result and any `_legacy.bin` before deciding.
- `assetlab gma <file.gma or *_legacy.bin> [--extract DIR]` lists or unpacks an addon (`importers/gma.py`; legacy bins are LZMA "alone"). Pass DIR as the first `--game-dir`, then GMod's `garrysmod` and `sourceengine` for the shared player animations.
- Some addons need another item for their textures (Goku 764848190 needs 703107302): extract it into the same DIR.
- Imported: Harry Potter (2855665131, `models/konnie/harrypotter/harrypotter_school.mdl`), Goku (764848190, `.../goku/pm/gokupm.mdl`), Superman 64 (3300749206, `models/player/ms/superman64/superman64.mdl`). Extracted under `~/assetlab-private/workshop/<id>/` (private).
- New personal roster: Master Chief (`348923474`, `models/halo1/spartan_mc.mdl`), Dragonborn (`156922874`, `models/player/dovahkiin.mdl`), Iron Man (`158326196`, `models/avengers/iron man/mark7_player.mdl`), and Dumbledore (`156923049`, `models/player/voikanaa/albus_dumbledore.mdl`). The last three came as legacy bins; the original Workshop pages for some old items say removed, but SteamCMD delivered their archived content. Keep the converted packages personal and private.
- `Skyrim Sweps` (`192130265`) supplies Dragonborn's Daedric Sword world and first-person models. `assetlab/data/weapons/skyrim_daedric_sword.json` is the build recipe; its swing sound comes from TF2. `elder_wand.json` reuses Harry's Workshop wand model and sound with separate balance. Both built private packages have no missing materials or dependencies.
- The importer now decodes 4096-pixel VTFs then reduces them to its package texture budget (Dragonborn's body texture); `$blendtintbybasealpha` and `$color2` are baked into RGBA (Master Chief's green armor). Both were checked with `open-halo-asset-test` renders.
- Asset Lab's 36 synthetic unit tests pass, including the new tint-mask material test.
- Characters now flag alpha materials (group flag bit 1) and take `--display` and `--loadout`.
- Import lessons: Superman 64's air clip loses his head in game; the game
  uses a complete idle pose with a forward lean for powered flight.
  Dragonborn's 4096-pixel VTF needs the raised input cap and budgeted
  downsampling; otherwise it becomes a placeholder. Master Chief's armor
  needs the baked tint mask because the game does not execute GMod's
  material proxies. Check each imported body and weapon in a render and
  on device before treating a package as complete.

## Sound packs (2026-09-24)

- `assetlab sounds <definition.json> --output ui.oalasset --game-dir ...`: an OALASSET of kind `sounds` (no models), sounds by role. `assetlab/data/sounds/tf2_hitsounds.json` packs TF2's hit and kill dings and its freeze-cam sounds; MEGAMOD SHOWDOWN loads `assets/sounds/ui.oalasset` for its hit feedback and killcam.

## Character stats and CS:S M4A1 (2026-09-24)

- `assetlab character --stats KEY=VALUE` writes health, shield, damage,
  movement speed, flight and ability settings into the character manifest.
  `group` writes a picker category, `unique=1` reserves one per match unless
  the host enables duplicate heroes, and `ability_beam=1` marks a piercing
  line ability. The current private bundle has 12 characters and 11 weapons.
  The game reads these when each character spawns. Current private packages
  include Goku, Superman, Harry, two CS:S players and three Source players.
- `assetlab/data/weapons/fists.json` uses an empty world model and Garry's
  Mod citizen arms (`c_arms_citizen.mdl`, sequences `fists_draw` /
  `fists_left`). `hp_wand.json` has 12 charges and 3 charges per second
  recharge; `hp_broom.json` flies at 3.5 wu/s. `ki_bolts.json` and
  `repulsors.json` are the recharging energy primaries for Goku and Iron Man.
- `assetlab/data/weapons/cs_m4a1.json` is the CS:S M4A1 for Urban's preset.
  Its private package has four view clips, two sounds and no missing
  dependencies. Rate and magazine follow CS:S; damage, spread and reload
  are stated as game balance in the definition. Silencer switching is not
  implemented.

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
  - LAN sync of characters and classes was added later in Megamod protocol
    v6/v7; both devices need the same package roster, and v7 unique-slot
    behavior still needs a phone LAN check.
- **Built packages (private, `~/assetlab-private/bundle/{characters,weapons}`):** the current 12-character/11-weapon set includes `t_leet`, `ct_urban`, `kleiner`, `alyx`, `scout`, Harry, Goku, Superman 64, Master Chief, Dragonborn, Iron Man, Dumbledore, the AK-47, M4A1, wands, Fists, Daedric Sword and TF2 weapons. Also available locally but not built: GMod's Breen, G-Man and a citizen; CS:S `t_phoenix` and other skins. There is no Gordon player model anywhere; GMod has only the HEV arms (`c_arms_hev`).

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
  - shader layers beyond the imported alpha-test/translucent subset
  - 3D skybox scaling (Halo sky kept on purpose)
  - moving brushes, ladders and lifts
  - game logic and Lua
  - MDL v49
  - prop scale
  - a triangle budget
- **Maps tested:** de_dust2, cs_office (v19), de_aztec (v19), de_inferno, koth_bagel_rc2a, gm_construct (without HL2, missing dependencies), gm_flatgrass, Black Mesa dm_crossfire. All eight convert through one command, load, render and collide in Open Halo, ground every shipped start and keep bodies in the map, and play 8-bot matches. Numbers are in the audit.
- **Map-specific hacks remaining:** none found. The remaining constants are named conventions or runtime caps, listed in the audit.

## Where things are

- **This repo** (public, `madpai/open-asset-lab`, branch `main`): importer, packager, no-login portal. Tests: `.venv/bin/python -m unittest discover -s tests -v` (36 pass; synthetic fixtures only).
- **Megamod Showdown game** (`~/projects/halo-trial-android`, branch **`halo-sandbox`**, private `madpai/megamod-showdown` / remote `megamod`): imported-map matches and the hero roster. Never push this branch or its private packages to Open Halo's public `origin`. The public `fp-animated-guns`/Open Halo `main` remains strictly Halo. See the game repo's `docs/HANDOFF.md` and `CLAUDE.md` before editing.
- **Portal**: user systemd `open-asset-lab.service`, `http://100.89.1.14:8762/`, bound to Tailscale only, **no login** (removed at the owner's request; the tailnet is the boundary). Mutations still need the `X-OAL-Request` header and a same-origin `Origin`. Linked from Open Halo's sideload page. The service's VPK list is TF2 server + the CS:S server's `cstrike_pak_dir.vpk`. The owner has since installed the CS:S client, Garry's Mod and Black Mesa under `~/.local/share/Steam/steamapps/common/`; they may be used as **test inputs** (conversions to scratch, not bulk-staged). The CS:S client's `hl2/` has HL2's texture archives, unlike the server install.
- **Private data** (never commit): `~/assetlab-private/` — `css-server/`, `maps/`, `workshop/`, SteamCMD installs and `bundle/` (`.oalmap` and `.oalasset` packages for the personal APK). The owner-supplied CS:S, TF2, GMod and HL2 content remains outside both Git repositories.

## Current de_dust2

Stage `de_dust2-3e24a3cf2954-289842cc` (audited importer, CS:S content only): 94,605 triangles (48,665 solid), 315 of 321 props + 9 physics-prop entities, 0 placeholders, 20 red / 20 blue starts, 120 MiB. Bundled as `~/assetlab-private/bundle/de_dust2.oalmap`. Mounting the CS:S client's `hl2/` too gives 0 missing dependencies (all 321 props, 75 model entities) - an owner decision, not bundled. Earlier phone result (previous importer): 120 fps, bots fight, Team Slayer/CTF work.

## Package format changes this session

OALMAP stays v1. The group record's fourth word (was reserved 0) is now flags; bit 0 = drawn but not collided with (Source `SOLID_NONE` props). Older readers ignore it. See [RUNTIME_PACKAGE.md](RUNTIME_PACKAGE.md). The manifest now carries `static_props_placed` and `static_props_unresolved`.

## History

[PROGRESS.md](PROGRESS.md) has the dated log (TF2 texture attempt, first staged maps, the VTF mip fix, displacements, props). The TF2 client-texture work is paused: the dedicated server's `tf2_textures_dir.vpk` has no data archives and a client install needs the owner's own Steam login (never ask for a password or Guard code in chat).
