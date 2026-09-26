# Working in Open Asset Lab

**Before major architectural work, read `docs/ASSET_LAB_VISION.md`** (and,
for the engine side, MegaMod's `docs/MEGAMOD_VISION.md`). Open Asset Lab is
becoming a general content compiler for MegaMod, not a Source converter.
It should understand the messiness of external content, so that MegaMod
only ever sees clean, generic MegaMod content. In practice:

- **Providers acquire; importers interpret.** A provider returns local
  files plus provenance and never parses. Steam Workshop is one provider
  among many. Would this still make sense if Workshop, or Source,
  disappeared?
- **Normalize into reusable intermediate representations** (World, Mesh,
  Material, Skeleton, Character, Weapon, …) rather than a new one-importer
  pipeline; define each when a second consumer needs it.
- **Emit generic concepts.** Foreign terms (`func_door`, SWEP, `$surfaceprop`)
  stay in importers; packages say Door, WeaponDefinition, surface `wood`.
- **Provenance always.** Every package records where its content came from;
  inferred or AI-suggested values are labelled and never override
  deterministic validation.
- The vision separates **[Now]**, **[Next]** and **[Someday]**; never
  describe a [Next] capability as done. Don't over-refactor: a real
  limitation, the minimum change, tests, a real-content check.

- Keep this repository separate from Open Halo. Runtime contract changes must be coordinated and tested in both repositories.
- Never commit BSPs, VMTs, VTFs, VPKs, Workshop downloads, staged packages, previews from proprietary maps, Halo data, tokens or personal paths in generated artifacts.
- Use original in-memory synthetic fixtures for public tests. Keep real maps under a private directory outside either Git repository.
- Run `python -m unittest discover -s tests -v` after importer or package changes. For Open Halo changes run its `scripts/verify.sh` with the owner's existing Trial data.
- Verify a real Source map with Open Halo's `open-halo-map-test` before claiming end-to-end map rendering. A standalone converter output is insufficient.
- Preserve source material paths and warnings. Unsupported features should fail explicitly or appear in the report.
- Procedures as skills (`.claude/skills/`, readable by any agent): `workshop-import` for Workshop items and collections. Map conversion and publishing live in Megamod's `.claude/skills/` (`convert-map`, `publish`).
- CI runs the tests and a no-game-content guard on every push; a red run is a real failure to root-cause, not to re-run away.
