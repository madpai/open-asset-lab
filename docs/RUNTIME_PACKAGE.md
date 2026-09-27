# OALMAP v1, v2 and v3

A single little-endian binary file, portable between x86-64 Linux and ARM64 Android. It is not a Halo cache. Version 1 starts with a 64-byte header: `OALM` magic; eight uint32 values (version, manifest byte count, vertex count, index count, group count, texture count, spawn count, flags); six float32 values (min XYZ, max XYZ); one reserved uint32. After the header, sections are contiguous:

| Section | Record |
| --- | --- |
| UTF-8 manifest | canonical sorted-key JSON, byte count from header |
| Vertices | 10 float32 each: position XYZ, normal XYZ, UV, lightmap UV |
| Indices | uint32 triangle list |
| Groups | v1: four uint32; v2: five uint32. First index, index count, albedo texture index, flags, then (v2 only) lightmap texture index or `UINT32_MAX` for unlit. Flags bit 0: no collision; bit 1: alpha; bit 2: breakable; bit 3 (v3): world entity. Breakable (or entity) index plus one occupies bits 8–23. |
| Textures | uint32 width, height, byte count, then tightly packed RGBA8 |
| Spawns | four float32: feet XYZ and yaw radians |

The manifest stores package version, ID, display name, Source format/version, SHA-256 of the source, source basename/provenance, coordinate scale, geometry and texture counts, bounds, material paths, dependencies, spawn source origins/ground projections, entity inventory and raw key-value metadata, unsupported features, warnings and a matching required runtime marker (`external-map-v1` or `external-map-v2`). It intentionally has no absolute desktop path. The file layout is deterministic for identical source bytes, source basename and material roots. Staging gives each job a unique directory, so repeat imports do not overwrite.

`convert --lightmaps` opts into v2 when the BSP has static LDR lightmaps. Source face luxels are packed into up to eight 1024-pixel RGBA atlases, included in the texture budget, and selected per material group. Vertex lightmap UVs use the existing two float32 slots. V1 remains the default and keeps the same binary layout.

The C loader bounds the total file at 256 MiB, checks version, counts, every section length, indices, groups, texture sizes, finite vertices/spawns and trailing bytes. The renderer and collision code receive ordinary `hta_bsp_mesh` buffers. Runtime loading also scans selected canonical manifest JSON fields: spawn teams, flag points, breakables and weather. It hashes the complete manifest for the current imported-world network key. The remaining source metadata and provenance are retained for Asset Lab, not used as executable instructions. See MegaMod's [N1 boundary review](https://github.com/madpai/megamod-showdown/blob/main/docs/research/CURRENT_RUNTIME_CONTENT_BOUNDARY_REVIEW.md).

## v3: world entities

Version 3 is v2's binary layout (five-word groups; lightmap index
`UINT32_MAX` when unlit) plus a manifest section the runtime must
implement:

```json
"world_entities": {"schema": 1, "entities": [
  {"id": "x1:entity/button_main", "kind": "interactable", "position": [x,y,z], "reach": 1.0,
   "links": [{"event": "used", "input": "activate", "target": "x1:entity/relay_main"}]},
  {"id": "x1:entity/door_main", "kind": "mover", "bounds": {"min": [...], "max": [...]},
   "move": [0,1.25,0], "speed": 1.0, "links": []}, ...]}
```

A mover's triangles are in groups flagged bit 3 with its entity index + 1
in bits 8–23, and bit 0 (the mover owns its collision, its `bounds` box).
Top-level `id` (`namespace:world/name`) and `namespace` name the world.
Written only by original worlds (`assetlab.world`, [ORIGINAL_WORLDS.md](ORIGINAL_WORLDS.md))
and only when there are entities; Source imports stay v1/v2. A runtime that
does not implement world entities refuses v3 rather than load the world
without its behaviour -- MegaMod relies on that to keep its v10 protocol
(`docs/WORLD_ENTITIES.md` there). MegaMod parses the section with a
bounded parser and refuses the whole package on any error.

### `world_entities` schema 2: mover definitions (X2)

Still OALMAP v3 (the binary layout is unchanged); the section's own
`schema` number says what it holds. Schema 2 adds reusable mover
definitions, and movers name one instead of carrying parameters:

```json
"world_entities": {"schema": 2,
  "mover_definitions": [{"id": "x2:mover/basic_slide_door", "size": [0.1,1.2,1.1],
                         "move": [0,1.25,0], "speed": 1.0}],
  "entities": [
    {"id": "x2:entity/door_a", "kind": "mover", "definition": "x2:mover/basic_slide_door",
     "position": [0,-3,0.55], "links": []}, ...]}
```

`position` is the closed box's centre; the box is `size` around it. In
schema 2 every mover names a definition and has no inline
`bounds`/`move`/`speed`; `mover_definitions` in schema 1 is refused. An
X1-era runtime refuses schema 2 ("unsupported schema"), so a world is never
loaded without its definitions. Each placed door still has its own
triangles (flagged bit 3 with its own entity index). Written only when a
world has definitions: worlds without them are schema 1, byte-for-byte as
before.

### `world_entities` schema 3: host-side scripts (X3)

Still OALMAP v3. Schema 3 adds `scripts` (each `{"id":
"namespace:script/name", "api": "megamod.v1", "callbacks": [...],
"source": "<Lua text>"}`), an interactable's optional `"script"`, and the
world's optional `"ability_script"`. Source text only -- never bytecode --
ASCII, 32 KB per script, 64 KB and 16 scripts per world. MegaMod runs
scripts on the host only (its `docs/SCRIPTING.md`); X1/X2-era runtimes
refuse schema 3. Written only when a world has scripts.

## The `package` declaration and library packages (X4)

Still OALMAP v3, and still `world_entities` schema 3: X4 adds one optional
top-level manifest member, written only for a world built with
`OriginalWorld.package` (X1-X3 fixtures are byte-for-byte unchanged).

```json
"package": {"id": "x4.resource_lab", "schema": 1,
            "provides": ["x4:mover/basic_slide_door", "x4:script/open_door", "x4:world/resource_lab"],
            "requires": [{"package": "x4.shared", "resources": ["x4shared:script/pulse_ability"]}]}
```

`id` is a **package ID** (`segment(.segment)*`, no `:` or `/`), never a
resource ID. `provides` is derived by the compiler -- the world, its mover
definitions, its own scripts -- in canonical byte order; MegaMod checks it
equals the content. `requires` names library packages (canonical order) and
the resources imported from each; a world may reference an imported
resource only if it is listed there. Every field is required, nothing else
is allowed. MegaMod's `docs/RESOURCES.md` is the contract.

A **library package** is an OALASSET v1 whose manifest has `"kind":
"library"`, the same `package` member (its provides: exactly its scripts)
and a `scripts` list in the schema-3 script form; no models, no sounds,
nothing after the manifest. It is written by `dependencies.compile_library`
to `packages/<package id>.oalasset`; MegaMod looks for it there by the ID a
world requires, and the package found must declare that ID.

## Asset resources in a library (X5)

A library may also provide **asset resources** -- MegaMod's `texture`,
`material`, `model` and `sound` types -- through an `assets` member and the
bytes of its members after the manifest:

```json
"assets": {"schema": 1,
  "members":   [{"path": "models/test_crate.mesh", "size": 1132}, ...],
  "textures":  [{"format": "rgba8", "height": 16, "id": "x5shared:texture/test_crate", "member": "textures/test_crate.rgba", "width": 16}],
  "materials": [{"draw": "opaque", "id": "x5shared:material/test_crate", "texture": "x5shared:texture/test_crate"}],
  "models":    [{"format": "mesh1", "id": "x5shared:model/test_crate", "materials": ["x5shared:material/test_crate"], "member": "models/test_crate.mesh"}],
  "sounds":    [{"channels": 1, "format": "pcm_s16le", "frames": 5512, "id": "x5shared:sound/test_impact", "member": "sounds/test_impact.pcm", "rate": 22050}]}
```

- The **resource ID is identity**; a **member path** is where the bytes sit
  in this package: lowercase `[a-z0-9_]` segments, one extension, at most
  96 bytes and 6 segments, never `..`, `/...`, `\`. MegaMod finds a member
  by offset, never joins it to a host path.
- Payloads: `rgba8` (w x h x 4 bytes), `pcm_s16le` (frames x channels x 2),
  `mesh1` (`MSH1`, u32 vertex/index/group counts, the OALMAP's 40-byte
  vertices, u32 indices, groups of u32 first/count/slot). The payload is the
  members' bytes in `members` order.
- `provides` lists every script and asset; every descriptor field is
  required; lists canonical; one member per resource.
- `provenance`: per resource ID, where it came from (provider, Workshop
  item, source path, licence...). Never played, never hashed.

A world imports them like scripts and places models as `prop` entities
(`{"id", "kind": "prop", "links": [], "model", "position"}`) and names a
sound in a mover definition (`"sound"`): world_entities schema 4. MegaMod's
`megamod-resources --json` ("assets", "world_entities") is the exact schema.

## The world key (MegaMod's map check)

MegaMod admits a joiner only if both peers compute the same **world key**
for the package: FNV-1a 64 over the played bytes -- counts, header bounds,
vertex/index/group/spawn records as stored, and the manifest members
`spawn_points`, `flag_points`, `breakables`, `weather`, `world_entities`
and (X4) `package` (exact value bytes, in manifest order; so scripts'
source bytes, comments included) -- never provenance, reports, names
or texture pixels. A world that requires libraries then adds, per package
of its closure sorted by package ID, `OALD`, the ID and that library's
digest (FNV-1a 64 of `OALL`, schema, its `assets` (X5), `package` and
`scripts` bytes, then -- when it declares assets -- `OALP`, the payload
length and every payload byte), so a library's Lua, texels, vertices and
samples are part of every requiring world's key; its provenance is not. The member lists come from MegaMod's contract
(`assetlab/data/megamod_resources.json`), not from this repository. `assetlab/worldkey.py` is the reference implementation
(its docstring has the exact stream); `assetlab world-key PKG` prints it
and `compile_world` reports it (`--packages-dir` finds required libraries).
MegaMod's `src/asset/external_map.c` computes the same value.
