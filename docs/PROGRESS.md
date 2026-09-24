# Progress milestones — 2026-09-23 onward

## McRonalds and citizen fists — 2026-09-24

Workshop item `3159770816` (`gm_mcronalds`) converts with GMod and
`sourceengine` mounted, prop LOD 1, into private `mcdonalds.oalmap`
(120 MB, 113,462 triangles, 0 missing dependencies, 4 grounded starts).
Host render shows the restaurant and the dining room. A 4-bot 45 s Slayer
got 3 kills at 0.787 ms/tick. Eight conveyor brushes are not imported.
The menu name is the bundle filename, not the BSP's `mcronald` id.

Fist SWEPs already in the Workshop download folder are scripts or empty
meshes. The punch viewmodel is Garry's Mod `c_arms_citizen.mdl`.
`VIEWMODEL_ROLES` now finds `ACT_VM_FISTS_IDLE` and `seq:` labels.
Included-model absolute poses are retargeted onto the destination bind so
a citizen neck does not swallow a taller head. Character tests: 5 pass.
Details in [HANDOFF.md](HANDOFF.md).

## Workshop hero roster and material import — 2026-09-24

Megamod Showdown's published private build (`f9ee859`) uses Asset Lab
packages for 12 characters and 11 weapons. This public importer is at
`c984d5f` before the documentation closeout. The new Workshop bodies are
Master Chief, Dragonborn, Iron Man and Dumbledore; Daedric Sword and Elder
Wand extend the weapon roster. All source downloads and converted packages
stay outside Git in `~/assetlab-private/`. The personal APK is available to
the owner at `http://100.89.1.14:8733/`; device visual feedback is pending.

- Master Chief's `$blendtintbybasealpha`/`$color2` material needed tint
  baked into RGBA. Without it, armor rendered white because Megamod does
  not run GMod material proxies.
- Dragonborn's 4096-pixel body VTF exceeded the former input cap and became
  a placeholder. The decoder now accepts 4096 pixels and downsamples to
  fit the package texture budget. Treat input size and output budget as
  separate limits.
- Several older Workshop listings said removed, while anonymous SteamCMD
  still delivered `_legacy.bin` archives. Exact item IDs and inspection of
  downloaded files matter; a collection ID is not an addon archive.
- Daedric Sword has separate Source world and view models, a TF2 swing
  sound and a view attack clip. Elder Wand reuses the Workshop wand model
  and sound with its own recharge balance. Package and offscreen renders
  were checked; first-person phone FOV remains unconfirmed.
- The 36 synthetic tests pass. The game side passed a 12-character,
  11-weapon bot match and `scripts/verify.sh` 80/80. These results do not
  establish phone appearance, performance or LAN behavior; the next
  checklist is in [HANDOFF.md](HANDOFF.md) and the game repo's handoff.

## ctf_2fort and TF2/HL2 weapons — 2026-09-24

TF2's ctf_2fort converts with no missing dependencies and plays in Open Halo's sandbox: doors imported open, the 3D skybox and additive light shafts left out, props at LOD 1, CTF flags in the intelligence rooms. Bots fight on it after Open Halo's bot grid was made finer for imported maps. Three more class weapons: TF2's Rocket Launcher and Scattergun, HL2's .357 Magnum (given a grip it never had). Bundled in sandbox build `5b64d7d`; phone test pending. 34 synthetic tests.

## Characters, weapons and custom classes — 2026-09-23 (late night)

Source characters (CS:S terrorist and counter-terrorist, GMod's Kleiner and Alyx) and the CS:S AK-47 convert into OALASSET packages through the same registry-and-search-path rules as maps, and play in Open Halo's sandbox. Bodies animate by role and hold both imported and Halo weapons. The AK has its own first-person model, clips, sound and stats. A custom-classes option spawns players with two chosen weapons. Verified on the desktop by renders and bot matches; phone test pending. Details in HANDOFF.

## Four imported maps on the phone — 2026-09-23 (late night)

de_aztec, cs_office and gm_construct were converted with the audited importer (same command as dust2) and bundled with de_dust2 in the owner's personal APK (sandbox build `8c25abc`, 707 MB). Owner's phone: cs_office and gm_construct run at **120 fps** and are "almost complete with some problems" (not being pursued now); screenshots show office interiors, props and GMod's buildings rendering. Next objective set by the owner: importing a player model and a weapon (see HANDOFF).

## Generalization audit — 2026-09-23 (night)

Audited the whole path for de_dust2-specific behaviour and refactored it into format tables, a translation registry and per-map compatibility reports: [GENERALIZATION_AUDIT.md](GENERALIZATION_AUDIT.md). Eight maps from CS:S (incl. two v19), TF2, Garry's Mod and Black Mesa now go through one command; all load, collide, keep every shipped start in the map and play bot matches in Open Halo. Two runtime assumptions tuned to dust2 were found by the new maps: the start re-grounding lift (cs_office ceilings) and region-based item placement (one-way ledges). 25 synthetic tests.

## Playable and scouted — 2026-09-23 (late)

- Owner's phone: de_dust2 runs at ~120 fps with bots in Team Slayer and CTF. Remaining reports were see-through windows (fixed by props) and respawns on roofs (an Open Halo snap-to-ground bug, fixed on its sandbox branch).
- Dry-ran every stock CS:S map: 12 of 18 are BSP v19 (refused), and de_nuke/de_inferno/cs_militia exceed the 128 MiB texture cap. Adding `hl2/hl2_misc_dir.vpk` places every HL2 prop, but HL2 textures stay placeholders (no data archives in the server install). Table and next steps in [MAP_IMPORT_PLAYBOOK.md](MAP_IMPORT_PLAYBOOK.md).

## Static props — 2026-09-23 (night)

- The owner saw sky through de_dust2's windows. Those windows, and its crates, domes, palms, rocks and wall trims, are static props: 321 placements of 53 models in a version-6 static prop lump the importer skipped. New `importers/source_mdl.py` reads MDL v44-48, VVD v4 and DX90 VTX v7 (LOD 0, bind pose, skin families, first existing `$cdmaterials` folder), placed with Valve's AngleMatrix and wound to agree with the model normals. `SourceBSP.static_prop_placements` reads lump versions 4-10 by record size.
- de_dust2: 315 placed, all materials resolved; six HL2 cars are absent from the CS:S server install and are listed as missing. 94,143 triangles (was 22,419), 130,645,616 bytes, texture data 118 MB (Open Halo's cap is 128 MiB). Renders at the owner's reported window position show the arched grille and shutters where the hole was.
- Group records' reserved word is now flags; bit 0 marks Source `SOLID_NONE` props as drawn but not collided with (46k of 72k prop triangles). Old readers ignore it. Three synthetic model tests added; 11 pass. Portal stage `de_dust2-3e24a3cf2954-7ec0e144` is byte-identical to the desktop conversion.

## Displacement fix and no-login portal — 2026-09-23 (evening)

- Owner's phone screenshots of de_dust2 showed shredded brown rock ribbons in the sky, holes and dark slivers in the sand. Cause: displacement grids were built transposed. Valve's `CCoreDispInfo` advances the outer (row) index along p0→p1 and the inner index along p0→p3; the importer had them swapped, so every vertex offset was applied at its mirror position. Measured on de_dust2: 1,195 of 2,064 displacement edge vertices coincide with a neighbour's after the fix, 76 before. Each displacement now has one winding chosen from its flat base quad, alternating diagonals, and per-triangle normals. A synthetic regression test fails on the old code (`0.0 != 0.25`) and passes now; 8 tests pass.
- Open Halo's host test gained `OALMAP_CAMERA="x y z yaw pitch"` to render the exact positions from a device report. Side-by-side renders at the three reported positions show the holes, slivers and rock ribbons gone. The restaged `de_dust2-3e24a3cf2954-5fa236d6` is byte-identical to the desktop conversion (SHA-256 `9543d04c…`), 40/40 spawns usable.
- Basic Auth was removed at the owner's request; the `access` command is gone. Mutations still need the `X-OAL-Request` header and a same-origin `Origin`. The service stays bound to the Tailscale address. Open Halo's sideload page links to it.

## Counter-Strike: Source de_dust2 — 2026-09-23

SteamCMD anonymous login installed the Counter-Strike: Source dedicated-server package (app 232330) in private storage. Its `de_dust2.bsp` is Source BSP v20. The VTF decoder used byte 63 (depth) as the mip count; correcting it to byte 56 resolved all 100 used material textures from the CS:S VPK. The resulting private OALMAP has 67,257 vertices, 22,419 triangles, 40 spawns, no placeholder materials or missing dependencies, and is 91,421,427 bytes. Open Halo's host Vulkan test rendered the map with llvmpipe and found usable ground under 40/40 spawns. The Android exploration picker and walking path were added for device testing; no on-device result is claimed yet. Brush entities, Source lightmaps, static props and gameplay entities remain unsupported. The private Asset Lab service has staged this package for the owner's download.

## Material preview follow-up — 2026-09-23

- Added explicit read-only VPK lookup to the CLI and worker. A synthetic VPK test verifies an actual VMT and VTF are loaded. The local service now uses the project's virtual environment and the privately installed TF2 dedicated-server VPK indexes.
- The anonymous TF2 dedicated-server install completed successfully, but `tf2_textures_dir.vpk` has no numbered texture archives. A separate anonymous request for client depot 441 returned `missing license for depot (No subscription)`. Asset Lab reports these missing VTF paths instead of claiming to have recovered them.
- Replaced the harsh checkerboard with deterministic, muted, material-specific placeholders. The manifest now lists every placeholder material, and the web staged list displays resolved texture and missing dependency counts. This improves the geometry preview without disguising missing assets.
- A fresh authenticated web conversion of the real map staged `koth_bagel_rc2a-a8e448254566-a6eefc80`. It has 71 world materials, five resolved albedos, 66 placeholders and 51 missing dependency paths. The OALMAP is 21,945,010 bytes; conversion took 2.301 s. Open Halo loaded it in 20.16 ms, built collision from 61,016 triangles in 5.22 ms, rendered the new spawn image through llvmpipe and found 32/32 usable ground projected spawns. The preview was visually inspected and has readable wood, masonry, grass and floor colors, though no real TF2 surface detail. Seven Python tests pass.
- Actual TF2 texture replacement remains dependent on a complete local client install or appropriately supplied content. The phone browser itself was not tested in this follow-up.

## Paused Steam install — 2026-09-23

At the user's request, the desktop Steam client was launched with `steam://install/440`. The client appeared to wait for account sign-in and no TF2 content download began. The transient Steam unit was stopped when the user requested a pause. The Asset Lab service remains active. The partial anonymous 435 MiB `app_update 440` directory has an app manifest but no numbered texture archives; it must not be mistaken for a complete TF2 install. No Steam password or Guard code was requested or stored. Further installation and texture conversion are paused until the user resumes.

## Demonstrated

- Audited Open Halo `fp-animated-guns` and kept its Trial branch/worktree clean before changes. Found no installed Source BSP in local Steam games; the installed `Zombie Panic Mod` maps are GoldSrc v30. Kept real Source test maps private outside both repositories.
- Inspected the real `koth_bagel_rc2a.bsp` (SHA-256 `a8e4482545669a88b372f8ccb5a0b1503b8601e7603987b2100c6133ea193f69`): Source v20, face lump v1, 22,641,755 source bytes, 12,207 world faces, 41,910 source vertices, 757 displacements, 736 entities and 1,211 static props.
- Converted it into 183,048 runtime vertices, 61,016 triangles, all 757 displacement records and 32 spawn points. 71 world materials were used; five albedo textures resolved, 54 dependency paths were missing and 13 material warnings were reported. 6,546 zero-area fan triangles were discarded. Missing surfaces still show the magenta fallback.
- Staged package `koth_bagel_rc2a-a8e448254566-bb3c8e27` at `~/.local/share/open-asset-lab/staged/`. OALMAP v1 is 21,933,010 bytes, SHA-256 `80c681e6e43ebbd2ab84ea5029dacb3ef644c0ad0512dfe2ab0dc947e9aaa478`, with 13,631,504 bytes of RGBA texture data.
- Open Halo's host renderer loaded that package in 20.35 ms, built collision from 61,016 triangles in 5.23 ms, uploaded to Vulkan in 45.08 ms, and wrote offscreen overview and spawn images. The software Vulkan device was llvmpipe; its reported GPU allocation was 31.0 MiB. Image coverage was 4.60% overview and 100.00% spawn view. All 32 source spawn XY points found walkable ground in the host collision grid. The first real map preview is `staged/koth_bagel_rc2a-a8e448254566-bb3c8e27/preview.png`.
- A separate handmade Source v20 `test2.bsp` from bsp_tool was uploaded through the web API, submitted as a job, and found `STAGED` through a later independent HTTP request. Its host spawn view covered 64.13% before the face-normal correction; current post-correction packages also pass the host test. The larger real map was then submitted, staged and its five artifacts retrieved via the same authenticated Tailscale-bound API.
- The `open-asset-lab.service` systemd user service is enabled and running on `100.89.1.14:8762`. Its Basic Auth rejects unauthenticated requests (401); unsafe source IDs, missing mutation header and path-like upload names were rejected (400/403/400). Open Halo's sideload service continues separately on port 8731.
- Public Python synthetic tests: 5/5. Open Halo's full `scripts/verify.sh` gate with the owner's private Trial map and lavapipe: 76 passed, 0 failed, including the new external package loader/collision test. A fresh isolated Python conversion took 1.928 s and reached 200.4 MiB peak resident memory. The worker's conversion stage measured 1.916 s.

## What the proof means

A: **Yes**, Asset Lab converted a real Source BSP with all its displacement records into a staged package. The map is visually incomplete because TF2 material dependencies and static-prop models are absent.

B: **Yes**, the current Open Halo **host** Vulkan renderer displayed actual converted Source world geometry and built collision. The Android app has no external-map selection or exploration mode yet, so this is not an Android walking proof.

C: **Not yet demonstrated from the phone.** The authenticated service is live on the Tailscale IP, and upload, job persistence, reconnect and artifact retrieval were demonstrated from the desktop via that IP. The owner's S24+ was offline in Tailscale during this milestone. A phone browser test remains.

## Limits and next test

Static props, clip brushes, brush entities, Source lightmaps and most shader behaviors are missing. Visible world triangles are used conservatively as collision, so some decorative surfaces can collide and invisible solid/clip surfaces are absent. Spawn ground projection and static host collision are proven; walking, jumping and wall behavior on this imported map need a native Android exploration mode. VPK lookup now works for explicitly configured archives; this TF2 map still needs the client texture data archives. After that material follow-up, the next engine milestone is an isolated external-map Android picker/exploration flow with measured on-device movement and memory, followed by collision brush and prop work.
