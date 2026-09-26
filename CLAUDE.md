# Open Asset Lab: agent briefing

Read, in order:

1. **`AGENTS.md`**: the hard rules (no game content, synthetic test
   fixtures, verify on real content with MegaMod's host tool) and the
   architectural rules (providers vs importers, intermediate
   representations, generic output, provenance).
2. **`docs/ASSET_LAB_VISION.md`**: what this project is becoming. Read it
   before major architectural work. Open Asset Lab is the content
   compiler for **MegaMod**, a native content-driven engine; Source/GMod
   is the first importer family and Steam Workshop the first provider,
   not the identity. The shared north star is MegaMod's
   `docs/MEGAMOD_VISION.md`
   (https://github.com/madpai/megamod-showdown/blob/main/docs/MEGAMOD_VISION.md).
3. **`docs/HANDOFF.md`**: the current state and how to run things.

Hard rules that override everything:

- This repository is **public**. Never commit BSPs, VMTs, VTFs, VPKs, MDLs,
  GMAs, Workshop downloads, converted or staged packages, previews of
  proprietary content, Halo data, credentials or personal paths.
- Real content lives in the owner's private directories
  (`~/assetlab-private/`), outside every Git repository.
- Package format changes are contract changes with MegaMod: change,
  test and document both sides together.
- Git author: `Phase2 <schultz0@proton.me>`. Code is GPL-3.0-or-later.
- Run `python -m unittest discover -s tests -v` after importer or package
  changes; CI runs it plus a no-game-content guard on every push.
