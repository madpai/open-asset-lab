# First vertical slice — 2026-09-23

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

Static props, clip brushes, brush entities, Source lightmaps and most shader behaviors are missing. Visible world triangles are used conservatively as collision, so some decorative surfaces can collide and invisible solid/clip surfaces are absent. Spawn ground projection and static host collision are proven; walking, jumping and wall behavior on this imported map need a native Android exploration mode. Material paths from TF2 require legitimately installed content or explicitly supplied roots; VPKs are not yet resolved. The next milestone is an isolated external-map Android picker/exploration flow with measured on-device movement and memory, followed by collision brush and prop work.
