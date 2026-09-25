---
name: workshop-import
description: Find and convert Steam Workshop content (Garry's Mod by default) into Megamod packages -- one item or a whole collection -- and check the result in the engine. Use for any request to add Workshop characters, weapons or maps.
---

# Import from the Steam Workshop

Downloads go to `~/.local/share/open-asset-lab/workshop/downloads` and
packages to a private folder: **never** commit either (public repository).

1. Find it:
   ```sh
   python -m assetlab workshop search "<words>" --tag Model|Weapon|Map|NPC
   python -m assetlab workshop info <id or URL>        # kind, size, direct or SteamCMD
   python -m assetlab workshop collection <id>         # what a collection holds
   ```
2. Look before building (downloads it, builds nothing):
   ```sh
   python -m assetlab workshop analyze <id> --install-steamcmd
   ```
3. Build, mounting Garry's Mod's own content (playermodels take their
   animations from it):
   ```sh
   python -m assetlab workshop import <id> --install-steamcmd --output-dir ~/assetlab-private/workshop/<id> \
       --game-dir "<GarrysMod>/garrysmod" --game-dir "<GarrysMod>/sourceengine" [--only characters,weapons,maps]
   # a whole collection, one folder per item, never stopping on a failure:
   python -m assetlab workshop import-collection <id> --install-steamcmd --output-dir ~/assetlab-private/workshop \
       --game-dir ... [--limit 50] [--dry-run]
   ```
   `workshop_report.json` / `collection_report.json` say what was built,
   what failed and why. A weapon's numbers drafted from its SWEP Lua are
   estimates: say so when it ships.
4. Check in the engine before claiming it works: characters and weapons
   with Megamod's `open-halo-asset-test`, maps with `open-halo-map-test`
   (see Megamod's convert-map skill), then bundle into
   `~/assetlab-private/bundle` and publish from Megamod.

SteamCMD is 32-bit: Debian/Ubuntu need `lib32gcc-s1`. Gamemodes and
entity/tool/effects addons are skipped by collection imports (nothing to
build, sometimes gigabytes); import one by itself to try it anyway.

Report per item: what was built, what failed and why, and the engine check.
