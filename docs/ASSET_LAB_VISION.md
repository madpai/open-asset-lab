# Open Asset Lab vision

The [comparative research map](RESEARCH_CONNECTIONS.md) links engine/mod findings to this project's importers, normalized content, provenance, package design, skeletons/animation, materials, and dependency resolution. It marks proposals separately from the capabilities described below.

**Read this before any major architectural decision in this repository.**
It is Open Asset Lab's half of the north star set by the owner on
2026-09-26. The canonical, shared document is MegaMod's
[`docs/MEGAMOD_VISION.md`](https://github.com/madpai/megamod-showdown/blob/main/docs/MEGAMOD_VISION.md)
(the engine side: entities, scripting, world events, rules, networking,
physics, materials, packages). This file repeats the shared essentials so it
stands alone, then goes deep on what Asset Lab is becoming.

| Tag | Means |
|---|---|
| **[Now]** | Implemented and tested here today |
| **[Next]** | Planned direction; build toward it when concrete work calls for it |
| **[Someday]** | Aspirational; keep it possible, don't build it yet |

---

## 1. The shared picture

```
 EXTERNAL OR ORIGINAL CONTENT
            │
   ┌─ OPEN ASSET LAB ────────────────────────────────────────────────┐
   │  PROVIDERS   acquire content + provenance (local, upload, Workshop, …)
   │  IMPORTERS   identify · parse (Source BSP/MDL/VMT/VTF, GMA, glTF, …)
   │  NORMALIZE   into stable intermediate representations
   │  ANALYZE     skeletons, weapons, worlds, surfaces (+ reviewable AI hints)
   │  ENRICH      collision, nav prep, LODs, fallbacks, previews
   │  VALIDATE    before runtime; report what was lost
   │  COMPILE     MegaMod packages, with provenance
   └──────────────────────────────────────────────────────────────────┘
            │
      MEGAMOD PACKAGES  →  MEGAMOD ENGINE  →  experiences  →  native multiplayer
```

- **MegaMod** is becoming a native, content-driven game runtime.
- **Open Asset Lab** is becoming the universal content compiler,
  content-intelligence platform and, eventually, creator tooling that
  turns heterogeneous assets into clean runtime content.
- **Halo is one compatibility layer** (inside MegaMod). **Source/GMod is one
  importer family** (here). **Steam Workshop is one provider** (here).

**The rule:** *MegaMod should understand MegaMod content. Open Asset Lab
should understand the messiness of external content.* Every foreign
format, entity class, unit system and material convention stops here;
what leaves is generic.

It is **not** "a script that converts GMod content for MegaMod". Two tests:
- *If Steam Workshop disappeared tomorrow, would Open Asset Lab still make
  sense?* It must: yes.
- *If Source support disappeared tomorrow?* It should become: yes.

---

## 2. Where it stands [Now] (2026-09-26)

| Area | Today |
|---|---|
| Providers | `providers.py` defines a `Provider` protocol (`sources`, `resolve`); `LocalDirectories` and web uploads implement it. **The Steam Workshop client (`workshop.py`: public browse API, SteamCMD, fetch) is not yet a `Provider`**: it lives in one module with GMod addon analysis and import dispatch. |
| Importers | `importers/source_bsp.py` (BSP v19/v20, entities, displacements, static and model props, lightmaps), `source_mdl.py` / `source_studio.py` (MDL v44–v49, skeletons, skin weights, animations), `gma.py` (GMod addon archives); VMT KeyValues, VTF (13 formats) and VPK resolution. All Source-family. |
| Translation | `translate.py`: a registry mapping Source entity classes to generic meanings (spawn classes → `"team"`, brush/model classes → solid, non-solid, breakable); `$surfaceprop` → placeholder surface colours. See [GENERALIZATION_AUDIT.md](GENERALIZATION_AUDIT.md). |
| Intermediate forms | The BSP importer produces an in-memory world (triangles, material keys, starts, diagnostics) that the package layer compiles. **Characters and weapons build straight into OALASSET** (`character.py`); there is no shared Mesh/Skeleton/Material representation yet. |
| Analysis | Workshop addon analysis: playermodels (with registered names and hands), SWEPs drafted into weapon definitions (**labelled estimates**), NPCs, maps. Hero stats and abilities are hand-kept data (`data/hero_roster.json`). |
| Packages | OALMAP v1/v2 ([RUNTIME_PACKAGE.md](RUNTIME_PACKAGE.md)) and OALASSET v1 (characters, weapons, sound banks), deterministic, with manifests carrying source hash, provenance, dependencies, warnings and unsupported features; a `compatibility.md` per map. |
| Validation | Synthetic-fixture unit tests (no game content) in CI; staged maps render and collide in MegaMod's host tool `open-halo-map-test`; spawns are ground-checked. |
| Service | Local web UI and API: SQLite job queue, one worker, staged library, Workshop search/import panels; bound to localhost or the Tailscale address only, never public. |

---

## 3. Responsibilities, and the boundaries between them

| Stage | Owns | Must not |
|---|---|---|
| **Provider** | Obtaining local content plus **provenance** (where from, when, which item/version, licence notes as known) | Parse or convert. A provider hands over files and a provenance record, nothing more |
| **Importer** | Identifying and parsing one format family; translating its concepts into intermediate representations | Acquire content; write runtime packages directly (new work goes through the IR) |
| **Normalizer / analyzer** | Units, axes, skeleton semantics, material semantics, surface classes, weapon semantics | Silently invent values: inferences are labelled |
| **Enricher** | Generating what content lacks: collision, nav preparation, LODs, fallback materials, hitboxes, thumbnails | Hide that it generated something |
| **Validator** | Checking against the runtime's limits and contract before anything ships | Pass what the runtime would reject |
| **Compiler** | Deterministic MegaMod packages with provenance | Know which game the content came from, beyond metadata |

**Provider/importer separation [Next]:** make the Workshop client a
`Provider` (search/fetch → local files + provenance) and move GMod addon
interpretation (playermodel registration, SWEP Lua) into an importer.
Future providers slot in beside it: local filesystem **[Now]**, uploads
**[Now]**, Git repositories, HTTP downloads, creator workspaces, generated
content. Remote scripts are never executed; SWEP Lua is parsed as data.

---

## 4. Intermediate representations [Next]

Stable internal representations that importers produce and the compiler
consumes, so each importer doesn't grow its own pipeline:

`World` · `Mesh` · `Material` · `Texture` · `Skeleton` · `Animation` ·
`Character` · `Weapon` · `Vehicle` · `Prop` · `Collider` · `Navigation` ·
`GameplayEntity` · `Audio` · `Script` · `PackageMetadata`

Build them from what already exists. The BSP importer's in-memory world is
the first `World`/`Mesh`; the next importer (glTF) is what should force
`Mesh`, `Material` and `Skeleton` to become shared. Don't design all
sixteen up front. Each gets defined when a second consumer needs it.

## 5. Importers beyond Source [Next]

Source/GMod is the first family and a superb torture test (eight maps from
four games through one code path). It is not the identity. Candidates:
**glTF/GLB (first: it proves generalization and opens original content)**,
OBJ, Quake BSP, Blender-exported content, voxel formats, MegaMod-native
project formats, other open or documented formats. Legally obtained content
only; format documentation is a reference, never copied code.

## 6. World and gameplay-entity translation [Next]

Translate foreign entities into MegaMod's **generic** world concepts (the
runtime side is MegaMod vision §8). Never reproduce Source's entity system:

| Source | MegaMod |
|---|---|
| `func_breakable` | Renderable + Collider + Health + Breakable **[Now]**: breakable groups flow through OALMAP flags |
| `info_player_*` | Spawn with a generic `"team"` **[Now]** |
| `func_button` | Button + EventEmitter |
| `trigger_teleport` | Trigger + Teleporter |
| `func_door` | Door + Interactable |
| `trigger_hurt` | DamageVolume |

What can't be translated is **reported**, as unsupported lumps and
features are today.

## 7. Humanoid normalization [Next]

A canonical **MegaMod humanoid**: `pelvis`, `spine`, `chest`, `neck`,
`head`, `upper_arm_l/r`, `forearm_l/r`, `hand_l/r`, `thigh_l/r`,
`calf_l/r`, `foot_l/r`; optional fingers, eyes, jaw, weapon attachments,
custom bones. Asset Lab should detect likely humanoids, suggest semantic
bone mappings, validate compatibility, retarget animations, normalize
attachments and emit runtime-ready characters. **[Now]** Source playermodels
convert with their own skeleton and animations "baked by role", and
compatibility depends on Valve's shared bone names. That is the seed and
the regression set.

## 8. Weapon normalization [Next]

More than a mesh: world model, view model, animations, grip, muzzle,
magazine, fire modes, projectile behaviour, fire rate, damage, spread,
recoil, reload, audio, effects, ammo, AI usage hints. Sources: format
metadata, SWEP definitions, scripts, model attachments, user
configuration, heuristics, AI suggestions. **Every inferred value is
labelled as inferred** (today's SWEP drafts already are).

## 9. AI-assisted analysis [Someday → Next]

Where deterministic parsing can't answer a semantic question, AI may
suggest: "this looks humanoid", "this mesh is probably a rifle", "these
bones are the hands", "this attachment is the muzzle", "this region looks
like a spawn room", "these are chokepoints", "this texture is glass".
**AI output is reviewable and labelled, and never silently overrides
deterministic validation.** A suggestion is data with a confidence and a
source, which a person or a rule accepts.

## 10. Surface semantics and procedural enrichment [Next]

Preserve or infer surface classes (wood, metal, glass, concrete, dirt,
grass, water, plastic) so the runtime can react generically: splinters,
shards, sparks, dust, the right impact sound. **[Now]** `$surfaceprop`
already drives placeholder colours, and MegaMod's props have a material
enum. Carry surfaces through packages to world triangles next.

Enrichment makes incomplete content usable without rebuilding it by hand:
collision, LODs, navmeshes, spawn layouts, hitboxes, fallback materials,
physics properties, thumbnails, previews, animation mappings, gameplay
regions. **[Now]** texture budgeting, spawn grounding and rejection,
placeholder materials, and previews through the host tool.

## 11. Content as Lego [Someday]

Interoperability is the defining capability. A character might combine an
original mesh, the MegaHumanoid skeleton, a compatible imported animation
set, an arena movement profile, an energy rifle, a flight ability and a
custom voice. A weapon might take its mesh from one source, its behaviour
from another definition, and a custom projectile, reload and sound. Each
normalization step above exists to make that possible.

## 12. Packages [Now → Next]

OALMAP and OALASSET are working prototypes; keep them. When new
requirements (world entities, materials, scripts, nav) would fork them
again, move toward an extensible **chunk-based** container (`OALP`: META,
MESH, MATL, TEXR, COLL, NAVM, ENTS, ANIM, AUDO, PHYS, SCRP…), with unknown
optional chunks skippable. Later still, **experience packages** bundle a
manifest, maps, characters, weapons, vehicles, props, materials, audio,
scripts, rules and UI. Format changes are contract changes: coordinate and
test in both repositories. Details in MegaMod vision §10.

## 13. Original content first-class [Next]

```
Blender → glTF → Open Asset Lab → character / weapon / map metadata
        → validate → preview → compile → MegaMod
```
No Halo, no Source, no Garry's Mod. This workflow is how MegaMod proves it
is its own engine, and how anything shareable gets made.

**Procedural worlds [Someday]:** with enough semantic understanding, Asset
Lab could assemble a world from modular content ("abandoned mall, medium,
12 players, infection, high verticality") or remix existing ones. Keep it
possible; it is not scope.

## 14. MegaMod Studio [Someday]

The local web UI may grow into **MegaMod Studio**: Dashboard, Library,
Workshop, Imports, Characters, Weapons, Maps, Materials, Audio, Projects,
Packages, Validation, Preview; later World Editor, Entity Inspector, Rule
Editor, Script Editor, Package Builder, Multiplayer Test Launcher. Don't
rush into a giant editor. **Preserve local-first**: heavy work on the
desktop, the phone or tablet over the owner's Tailscale, no public listener,
network boundary as the only access control (see
[ARCHITECTURE.md](ARCHITECTURE.md)).

---

## 15. Priorities for Asset Lab (directional)

Imported content is now mainly a **stress test**, not the goal. Don't spend
the next phase importing hundreds more characters. Roughly by dependency:

1. **Provider/importer split**: the Workshop client becomes a `Provider`;
   GMod addon interpretation becomes an importer.
2. **Surface semantics** carried to packages (feeds MegaMod's material and
   interaction work).
3. **World-entity translation** into generic concepts, as MegaMod gains
   Door / Button / Trigger / Teleporter (MegaMod vision §8).
4. **A glTF importer**, which forces shared `Mesh` / `Material` / `Skeleton`
   IR and opens original content.
5. **Humanoid normalization** and animation retargeting.
6. **Weapon normalization** with labelled inference.
7. **Chunked packages** when a new data kind needs one.
8. **Library / project model**, then experience packages.
9. Studio, AI-assisted analysis and procedural enrichment as the IR matures.

## 16. Checklist before implementing a major system

- Does it work for **original** content, not just Source?
- Is it in the right stage (provider vs importer vs compiler)?
- Does it produce or consume a **reusable intermediate representation**
  rather than a one-importer pipeline?
- Does the output use **generic MegaMod concepts**, with foreign terms kept
  in the importer?
- Is every inferred or AI-suggested value **labelled**?
- Is **provenance** carried through to the package?
- Can the result be **validated before runtime**, and is what was lost
  **reported**?
- Would it still make sense if Workshop, or Source, disappeared?

## 17. Do not over-refactor

The pipeline works: six maps, 14 characters and 11 weapons in the owner's
bundle, eight structurally different maps through one path. For every
change: a real limitation first, the minimum change, synthetic-fixture
tests, the host-tool render/collision check on real content, and a note of
the coupling that remains. No abstractions that solve no concrete problem.

## 18. Content, legal and provenance rules: unchanged, and stronger

- Never commit BSPs, VMTs, VTFs, VPKs, MDLs, GMAs, Workshop downloads,
  staged or converted packages, previews of proprietary content, Halo
  data, credentials or personal paths.
- Public tests use synthetic fixtures only.
- Workshop availability grants no redistribution rights; a documented
  format grants no content rights.
- Every package records its provenance (source hash, origin, provider,
  conversion, inferred values). The vision raises the bar on provenance.
- Converted proprietary content stays private to the owner. Shareable
  output comes from original or suitably licensed content.
