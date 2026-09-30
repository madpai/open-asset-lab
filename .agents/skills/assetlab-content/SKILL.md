---
name: assetlab-content
description: Prepare, normalize and verify original or imported content for Megamod Engine through Open Asset Lab, preserving provenance and checking native-loader agreement. Use for content projects, importer changes, generated assets and package compatibility work.
---

# Prepare content for Megamod

Read this checkout's `AGENTS.md`, `docs/ASSET_LAB_VISION.md`, current
`docs/HANDOFF.md`, and the relevant package/authoring documentation.
Inspect code when dated documentation and current capabilities disagree.
For Workshop acquisition use `.claude/skills/workshop-import/SKILL.md`;
for runtime contract changes read the Engine's instructions and vision too.

## Find and preserve the source of truth

Identify the input format/version, dependencies, intended behavior and
the Engine's actual supported representation. Providers supply local
files and provenance; importers interpret foreign formats; compiled
packages carry generic concepts. Keep private source assets, extracts,
packages, previews and reports outside public history.

Measure axes, handedness, units, facing, pivot, texture alpha, skeleton
and attachment conventions before transforming art. Preserve original
material paths and diagnostics. Unsupported features must remain visible
in the compatibility report. Label estimated stats or inferred semantics.

For original/generated assets, record creator/tool/model where known,
input/output hashes, generation settings or prompt, conversion recipe and
rights status. Generation does not establish redistribution rights or
engine compatibility. Use the available imagegen skill/tool for raster
generation; an optional external generator requires its credentials and
cost authorization. Universal Modder's fal server is not a dependency of
this skill. glTF, generalized retargeting and broader material features
must be verified in code before being described as supported.

## Verify one asset or world before expanding

Use existing compilers, with original fixtures for public tests. For a
new reader/writer, compare meaningful decoded data through a round trip;
bound any lossy error explicitly. Check rendered facing, scale, lighting,
alpha and attachments in the Engine before batch conversion.

For trusted local content projects, from the Asset Lab checkout:

```sh
.venv/bin/python -m assetlab project verify projects/megamod_racing \
  --engine ../megamod-showdown/build-host/megamod-resources \
  --output /private/new-verification-run
```

Supply the actual checkout/executable and a fresh evidence directory.
Like `project build`, this executes the project's local Python. It builds
twice, compares all package hashes, checks dependencies/references and
loads every world through the supplied native executable. It compares
world key/digest, dependency closure, bindings and replication budget;
`verification.json`, `build.json` and native stdout/stderr preserve the
result. A nonzero exit is a failed verification. This proves package
agreement; the Showdown playtest proves behavior, rendering and multiplayer.

For imported maps use `resources check` and the existing conversion skill's
`open-halo-map-test` render/collision/spawn check on private real content.
`project verify` is for authored projects, not a replacement importer.
After importer/package changes run the full synthetic unittest suite and
the relevant native integration gate. Preserve provenance-only identity
semantics; coordinate any contract change in both repositories.

Methodology and proposed follow-ups:
[Universal Modder study](https://github.com/madpai/megamod-showdown/blob/main/docs/research/UNIVERSAL_MODDER.md).


## Classic Oblivion prototype

For owner-supplied classic archives use `docs/OBLIVION_IMPORT.md` and the
optional `oblivion-model` CLI. Strict static imports first; frozen actors only
with explicit stored-pose diagnostics. Measure pivot/scale/grip and render in
the native engine. Neither imported artwork nor successful loading proves
skeletal animation, plugin mechanics or wearable armor. Use an original BSA/NIF
fixture for reader changes and `projects/gatebound` for survival contract work.

For animation-only Source `UseHands` viewmodels, explicitly supply the donor
`hands_model`; map bone names and inspect visible geometry in the native
renderer. Refuse zero-vertex viewmodels. For Oblivion first-person assets,
check blade direction, hand placement and casting in Android, and label
authored root clips separately from unsupported original KF animation.
Use real normalized diffuse pixels and floor/gate meshes where available.
Inspect the in-game HUD and inventory on an Android screen: Android widget
text units differ from Canvas pixels, and package presence alone proves
neither correct presentation nor that the runtime actually loaded the roster.
For wielded NIF weapons, inspect optional scabbard/attachment subtrees and
exclude them explicitly by name when appropriate; preserve this selection
in provenance. A covered blade is not an orientation or texture problem.
