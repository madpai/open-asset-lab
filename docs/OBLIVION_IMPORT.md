# Experimental classic Oblivion import

Use the assetlab-content skill: preserve provenance, measure scale and inspect
native appearance before expanding a conversion. This reader targets local
classic BSA v103 and NIF 20.0.0.4 diffuse triangles. It is not a TES4 plugin,
quest, Havok or KF importer. Strict mode rejects skin/controllers; `--freeze`
imports a reported stored pose and omits unsupported features. Optional PyFFI
is an offline BSD decoder, pinned in `requirements-oblivion.txt`; the Engine
loads the existing normalized packages and has no foreign decoder dependency.

Install optional requirements in the Asset Lab virtual environment. Then:

```sh
python -m assetlab oblivion-model meshes/clutter/cheese01.nif \
  --meshes /private/mesh-archive.bsa --textures /private/texture-archive.bsa \
  --output-dir /private/cheese --namespace localtoy --name cheese --scale .0078125
```

Use `--kind character` or `--kind weapon` for the explicit one-root-bone rigid
fallback. Fit scale, pivot, facing, grip and first-person placement to the
native runtime before treating that package as playable art. Weapon metadata
uses an authored melee fallback; stats are not recovered from plugin records.
`--exclude-node NAME` explicitly omits a scene subtree and records the choice;
missing names are refused. For an unsheathed iron longsword, exclude `Scb`;
the source mesh includes both blade and scabbard.
Armor geometry can be imported as a prop; wearable armor attachments are not
implemented. Package provenance records source paths/hashes and unsupported
features, and does not establish redistribution rights. Keep all extracts,
packages and previews outside public repositories.

The original `projects/gatebound` config demonstrates the reusable survival
contract: eight skills, host-owned progression and a maximum 32-item shop.
The private arena composes Oblivion visuals with Source/Workshop packages.
`character --animation-map mapping.json` and a weapon definition's
`animation_map` select exact source sequences for native roles. Missing labels
fail instead of silently substituting unrelated animation. Animation-only
Source `UseHands` weapons can set `hands_model` to an actual donor hand MDL.
Asset Lab maps bone names, preserves bind transforms and appends missing
ordered helper bones; it refuses an empty visible viewmodel. This is required
for the local Workshop Zombie SWEP.

For a trusted Python project, `World.model_geometry` accepts normalized
`ModelPlacement` objects and bakes their triangles, normals and UVs into the
existing map format. `World.material_textures` replaces authored texture
pixels with normalized diffuse textures. Model placement changes world
identity; texture-only changes are covered by package SHA256 and the complete
content fingerprint. Native screenshots must verify both. Explicit rigid
actor view geometry and root clips allow camera placement and simple actions;
these clips do not claim original donor skeletal animation. Private UI bitmap
artwork stays in the personal bundle and is excluded from guest APKs.

**Fact:** classic local archives use v103 with flags 0x703. The prefix flag is
interpreted for later versions in [NifSkope's archive reader](https://github.com/niftools/nifskope/blob/develop/lib/fsengine/bsa.cpp)
(reviewed 2026-09-30). This original v103 reader bounds tables, offsets and zlib
output, rejects overlaps/traversal and never extracts archive member paths.
**Inference:** frozen creature artwork is useful for a prototype enemy when
paired with authored native AI. **Unknown:** original skeletal animation,
plugin semantics and broader NIF variants; none are claimed supported.
