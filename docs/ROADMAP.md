# Roadmap

Open Asset Lab is the compiler/toolchain for **MegaMod Engine**, not a
Showdown-specific importer. MegaMod Showdown is the Engine's continuing
integration and stress test; future original games are independent
consumers. Original workflows should become as strong as foreign-content
imports. Keep the output generic even when Showdown supplies the first
concrete feature need.

The direction is [ASSET_LAB_VISION.md](ASSET_LAB_VISION.md) (§15 has the
priority order, §2 the current state). This file keeps the short list and
what is done.

## Done

- 2026-09-23: phone-tested de_dust2 matches; VPK material resolution;
  static-prop models; non-solid prop flag; generalization audit (eight maps
  from four Source games through one path).
- 2026-09-24/25: Source characters and weapons (`.oalasset`), sound banks,
  MDL up to v49; Workshop search/fetch/analyze/import and collections;
  breakable brushes; static Source lightmaps (OALMAP v2) and the
  displacement lightmap mapping fix. Details and exact dates in
  [HANDOFF.md](HANDOFF.md) and [PROGRESS.md](PROGRESS.md).
- 2026-09-26: read-only N2 audit of proposed `namespace:type/name` IDs,
  collisions and legacy references; see [CONTENT_IDS.md](CONTENT_IDS.md).

## Next, by dependency (directional, not a sprint list)

MegaMod's v10 LAN content check is implemented; it is an engine-side prerequisite to safe cross-peer testing, not an OAL format migration. OAL's N2 read-only ID audit is complete. For X1, pass a tiny programmatically built ORIGINAL normalized world through the ordinary OAL validator/compiler, then load the compiled package in MegaMod. Exercise stable placed IDs, target/reference validation, generic event links, a moving collider, trigger and teleport target. A glTF importer and editor can follow that proof. See [research connections](RESEARCH_CONNECTIONS.md).

1. Support the X1 original synthetic world through a shared normalized-world validator/compiler seam. The fixture constructs Button → Relay → Door and Trigger → Teleport destination; it must reach real OAL compilation and MegaMod package loading. MegaMod may separately use a small C world fixture for unit tests.
2. Split the Workshop client into a `Provider` (acquisition + provenance)
   and a GMod addon importer.
3. Carry surface semantics (wood, metal, glass, …) into packages.
4. Translate world entities (doors, buttons, triggers, teleports) into
   MegaMod's generic concepts once the runtime has them.
5. A glTF/GLB importer: forces shared Mesh / Material / Skeleton
   representations and opens original content.
6. Humanoid normalization and animation retargeting; weapon normalization
   with labelled inference.
7. Chunked packages when a new data kind needs one; then a library /
   project model and experience packages.

Imported content is now mainly a stress test: don't prioritize importing
more characters over the items above.

## Still true from the original plan

- Player-clip brushes as invisible collision.
- Common VMT shader properties beyond albedo, alpha and lightmaps.
- Workshop research: [Steamworks ISteamUGC](https://partner.steamgames.com/doc/api/isteamugc)
  is tied to the consumer application's ID and permissions;
  [Steamworks' implementation guide](https://partner.steamgames.com/doc/features/workshop/implementation)
  describes game/app enablement; `ISteamRemoteStorage` is
  [deprecated for new Workshop integration](https://partner.steamgames.com/doc/api/isteamremotestorage).
  Local import stays independent of any Workshop provider.
