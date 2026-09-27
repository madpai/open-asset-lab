# Local game architecture observations

Read-only inspection on 2026-09-27. Steam's `libraryfolders.vdf` pointed to the local library; app manifests were used to select relevant installed titles. This is a *curated architectural sample*, not a committed inventory. No game was run, modified, unpacked for publication or bypassed. No proprietary assets or recovered source are in this repository. File paths below are relative to each game's install. **VERIFIED** applies to the files and declarations inspected, not to unobserved runtime behavior.

## Natural Selection 2 (Spark)

**Files/technique:** read installed Lua under `ns2/lua/bots/`: `BrainSenses.lua`, `PlayerBrain.lua`, `TeamBrain.lua`, `BotMotion.lua`, `Bot_Server.lua`, `BotDebuggingManager.lua`; targeted `rg`, short source reads. **VERIFIED:** senses have named lazy evaluators cached per frame with cycle checks; immediate action weights and slower objective weights are separately evaluated; active objectives have validation; team brain has known entities, alerts, threats and assignments; motion caches path points and tracks path regeneration/stuck cases; bot debug records chosen action/goal weights. `Bot_Server.lua` creates server virtual clients for bots. **STRONGLY INDICATED:** bot decision logic is server-owned and layered into sensors, tactical/strategic choice, team coordination and motion. **Unknown:** exact wire payload, total AI CPU cost, nav data file format and whether every path uses the same backend. **MegaMod lesson:** keep these layers and debug score provenance, but do not copy class-specific Lua behavior or its timing constants. Proprietary game Lua is used only as architectural evidence; no code or substantial excerpts were copied.

## Garry's Mod / Source content

**Files/technique:** `garrysmod/maps/gm_construct.nav` and `gm_flatgrass.nav` file presence and first header bytes; `bin/halflife2.fgd`, `bin/base.fgd`, `garrysmod/gamemodes/terrortown/ttt.fgd`; Lua modules `ai_schedule.lua` and `ai_task.lua`. **VERIFIED:** `gm_construct.nav` is a separate binary adjacent to its map, begins with bytes `ce fa ed fe`; `file` misidentifies that magic as Mach-O, so extension/header context matters. FGD declarations expose typed inputs/outputs, target names, NPC relationships, hint/assault points and scripted activities. Garry's Mod Lua exposes schedule/task construction over engine tasks. **STRONGLY INDICATED:** Source's spatial AI data and map interaction authoring are distinct from BSP render/collision bytes. **Unknown:** actual `.nav` topology, path quality, which map types use it for which NPCs, and exact runtime schedule behavior in the installed build. **MegaMod lesson:** package navigation alongside a world, preserve generic link/action semantics and authorable semantic points; avoid assuming a magic header means a particular platform file. Game assets and FGD declarations are proprietary; no file copy is included. Valve's public [SDK license](https://github.com/ValveSoftware/source-sdk-2013/blob/master/LICENSE) limits code reuse.

## Black Mesa

**Files/technique:** inspected installed `bin/bms.fgd`, `bin/halflife2.fgd` and looked for loose `.nav` files. **VERIFIED:** FGDs expose Source-style entity authoring; no loose `.nav` was found in the inspected install. **Unknown:** navigation may be embedded in other packaged assets or built differently. **MegaMod lesson:** absence of a loose file is weak evidence; document only the authoring vocabulary observed. Proprietary content remains local.

## Factorio

**Files/technique:** read `data/base/prototypes/entity/enemies.lua` and `enemy-constants.lua`. **VERIFIED:** enemy and spawner prototype data exposes movement speed, attack parameters, pollution absorption and evolution-dependent spawn weights. **STRONGLY INDICATED:** a data-defined archetype can configure substantial enemy behavior without making the prototype file itself a planner. **Unknown:** internal pathfinding, group control and multiplayer simulation ownership; those are not established by prototype declarations. **MegaMod lesson:** separate authorable agent parameters from decision runtime. Proprietary prototype data stays in the game install.

## Project Zomboid

**Files/technique:** targeted reads/searches in `projectzomboid/media/lua/server/ClientCommands.lua` and shared `Vehicles/TimedActions/`. **VERIFIED:** server Lua includes object change/transmission paths, while shared timed-action modules name interaction steps such as opening, locking and refueling. **STRONGLY INDICATED:** world actions have durable state changes distinct from their animation/interaction timing. **Unknown:** zombie AI internals and authoritative ownership of every action. **MegaMod lesson:** a general action API needs start/progress/result, plus authoritative durable world state; this is not evidence for a particular NPC planner. Proprietary code was not copied.

## Arma 3 and Space Engineers: scoped inventory only

**Files/technique:** filename inventory found Arma 3 `Addons/*.pbo` and Space Engineers managed `*.dll`/definition content. **VERIFIED:** the installs have packaged or managed components potentially worth later study. No content-level AI conclusion was drawn. **Unknown:** decision architecture, nav representation and authority from these filenames alone. This is deliberately not counted as deep research; revisit only with a specific question and a read-only public-format tool. No archive/binary extraction was performed.

## Confidence summary

NS2's layer split and Garry's Mod's authored I/O are the strongest local evidence because readable installed definitions directly express them. Header-only or filename-only findings are narrow. None of these games justifies copying proprietary code, data or an entire architecture into MegaMod.
