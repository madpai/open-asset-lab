# OALMAP v1

A single little-endian binary file, portable between x86-64 Linux and ARM64 Android. It is not a Halo cache. Version 1 starts with a 64-byte header: `OALM` magic; eight uint32 values (version, manifest byte count, vertex count, index count, group count, texture count, spawn count, flags); six float32 values (min XYZ, max XYZ); one reserved uint32. After the header, sections are contiguous:

| Section | Record |
| --- | --- |
| UTF-8 manifest | canonical sorted-key JSON, byte count from header |
| Vertices | 10 float32 each: position XYZ, normal XYZ, UV, lightmap UV |
| Indices | uint32 triangle list |
| Groups | four uint32: first index, index count, albedo texture index, reserved |
| Textures | uint32 width, height, byte count, then tightly packed RGBA8 |
| Spawns | four float32: feet XYZ and yaw radians |

The manifest stores package version, ID, display name, Source format/version, SHA-256 of the source, source basename/provenance, coordinate scale, geometry and texture counts, bounds, material paths, dependencies, spawn source origins/ground projections, entity inventory and raw key-value metadata, unsupported features, warnings and required runtime marker `external-map-v1`. It intentionally has no absolute desktop path. The file layout is deterministic for identical source bytes, source basename and material roots. Staging gives each job a unique directory, so repeat imports do not overwrite.

The C loader bounds the total file at 256 MiB, checks version, counts, every section length, indices, groups, texture sizes, finite vertices/spawns and trailing bytes. The renderer and collision code receive ordinary `hta_bsp_mesh` buffers. Runtime loading currently skips manifest JSON after validating its length; the host tool reads binary geometry/spawns. Source provenance is retained for Asset Lab, not used as executable instructions.
