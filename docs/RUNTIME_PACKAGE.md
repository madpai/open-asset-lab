# OALMAP v1 and v2

A single little-endian binary file, portable between x86-64 Linux and ARM64 Android. It is not a Halo cache. Version 1 starts with a 64-byte header: `OALM` magic; eight uint32 values (version, manifest byte count, vertex count, index count, group count, texture count, spawn count, flags); six float32 values (min XYZ, max XYZ); one reserved uint32. After the header, sections are contiguous:

| Section | Record |
| --- | --- |
| UTF-8 manifest | canonical sorted-key JSON, byte count from header |
| Vertices | 10 float32 each: position XYZ, normal XYZ, UV, lightmap UV |
| Indices | uint32 triangle list |
| Groups | v1: four uint32; v2: five uint32. First index, index count, albedo texture index, flags, then (v2 only) lightmap texture index or `UINT32_MAX` for unlit. Flags bit 0: no collision; bit 1: alpha; bit 2: breakable. Breakable ID plus one occupies bits 8–23. |
| Textures | uint32 width, height, byte count, then tightly packed RGBA8 |
| Spawns | four float32: feet XYZ and yaw radians |

The manifest stores package version, ID, display name, Source format/version, SHA-256 of the source, source basename/provenance, coordinate scale, geometry and texture counts, bounds, material paths, dependencies, spawn source origins/ground projections, entity inventory and raw key-value metadata, unsupported features, warnings and a matching required runtime marker (`external-map-v1` or `external-map-v2`). It intentionally has no absolute desktop path. The file layout is deterministic for identical source bytes, source basename and material roots. Staging gives each job a unique directory, so repeat imports do not overwrite.

`convert --lightmaps` opts into v2 when the BSP has static LDR lightmaps. Source face luxels are packed into up to eight 1024-pixel RGBA atlases, included in the texture budget, and selected per material group. Vertex lightmap UVs use the existing two float32 slots. V1 remains the default and keeps the same binary layout.

The C loader bounds the total file at 256 MiB, checks version, counts, every section length, indices, groups, texture sizes, finite vertices/spawns and trailing bytes. The renderer and collision code receive ordinary `hta_bsp_mesh` buffers. Runtime loading currently skips manifest JSON after validating its length; the host tool reads binary geometry/spawns. Source provenance is retained for Asset Lab, not used as executable instructions.
