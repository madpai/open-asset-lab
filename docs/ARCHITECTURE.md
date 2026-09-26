# Architecture

*This describes the service as it is built today. Where it is going
(providers vs importers, intermediate representations, generic output,
new importers, Studio) is [ASSET_LAB_VISION.md](ASSET_LAB_VISION.md).
Where the two differ, this file is the truth about the code; the vision is
the direction.*

The service has one Python process, one SQLite queue and one worker. A Source BSP importer reads bounded lumps into an in-memory world: triangle vertices, material keys, spawn points and diagnostics. The compiler resolves materials, serializes OALMAP v1, and records source hash and conversion provenance. A staging job calls Open Halo's host tool as a fixed executable with fixed arguments, verifies render and collision, and then atomically publishes a unique staged directory. Browser connections only create and inspect jobs; they do not own worker lifetime.

Asset Lab owns source selection, format identification, parsing, dependency resolution, conversion, validation, package compilation and staging. MegaMod (the engine in megamod-showdown, which grew out of Open Halo) owns native package loading, renderer upload, collision, navigation and Android gameplay. The rule between them: MegaMod understands MegaMod content; Asset Lab understands external content. The shared contract is [OALMAP v1](RUNTIME_PACKAGE.md), rather than a false Halo `.map` cache.

The importer lives under `assetlab/importers/`; a future importer can produce the same minimal world representation and compile through the package layer. A future acquisition provider would register a local source in the same queue. The service's providers are local directories and uploads (`providers.py`). The Workshop client (`workshop.py`, added 2026-09-24) still combines acquisition with GMod addon analysis and import dispatch; splitting it into a `Provider` plus an importer is the first step in the vision's priorities. It never executes remote scripts (SWEP Lua is parsed as data).

Security: default bind is localhost. `--tailscale` binds the current Tailscale IPv4 only. There is no login (removed 2026-09-23 at the owner's request): the network boundary is the only access control, so the service must never bind a public interface. Mutations require a custom request header and reject foreign Origin values. Source selection uses server-issued IDs derived from registered files; no remote path or shell command is accepted. Upload names are restricted, symlinks are excluded, input/queue/disk limits apply, and one conversion runs at a time. This is a private local service, with no public Internet listener.

Ownership: Python owns BSP bytes, mesh lists and converted texture bytes during compilation. The package owns their serialized copies. `hta_external_map_load` allocates Open Halo `hta_bsp_mesh` buffers and spawns; `hta_external_map_free` releases them. The Vulkan mesh upload owns GPU copies until `hta_gfx_mesh_free`. `hta_collision_build` borrows mesh vertex/index pointers; free its grid before freeing the mesh.
