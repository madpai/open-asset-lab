# First vertical slice — 2026-09-23

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
