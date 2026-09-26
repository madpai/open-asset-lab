# Roadmap

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

## Next, by dependency (directional, not a sprint list)

1. Split the Workshop client into a `Provider` (acquisition + provenance)
   and a GMod addon importer.
2. Carry surface semantics (wood, metal, glass, …) into packages.
3. Translate world entities (doors, buttons, triggers, teleports) into
   MegaMod's generic concepts once the runtime has them.
4. A glTF/GLB importer: forces shared Mesh / Material / Skeleton
   representations and opens original content.
5. Humanoid normalization and animation retargeting; weapon normalization
   with labelled inference.
6. Chunked packages when a new data kind needs one; then a library /
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
