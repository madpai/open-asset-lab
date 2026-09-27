# Stable content IDs: grammar and the read-only audit (N2)

**Status:** 2026-09-26. The grammar below is the one recommendation. IDs are
**proposed and audited only** -- except original worlds (X1): an OALMAP v3
from `assetlab.world` declares its world `id`/`namespace` and uses placed
`entity` IDs, (X2) `mover` definition IDs and (X3) `script` IDs, which MegaMod resolves at load. Otherwise no package carries them, MegaMod does not
load or send them, and no save or network message depends on them. What the
runtime actually matches on today is MegaMod's
[`docs/CONTENT_COMPATIBILITY.md`](https://github.com/madpai/megamod-showdown/blob/main/docs/CONTENT_COMPATIBILITY.md)
(file names, manifest names, display labels, roster positions and a
gameplay fingerprint).

## Grammar: `namespace:type/name`

| Part | Rule |
|---|---|
| namespace | `[a-z][a-z0-9_]*`, at most 40 bytes. The owning package lineage; one owner per namespace in a resolved package set. Stays the same across versions of the same package. |
| type | one of `world`, `character`, `weapon`, `sounds`, `entity`, `mover`, `script` (a registry category; new ones are added deliberately), at most 24 bytes. `entity` (added for X1, 2026-09-26) is a **placed** world entity, unique within its world and in the world's namespace -- a placement, not a reusable definition ([ORIGINAL_WORLDS.md](ORIGINAL_WORLDS.md)). `script` (added for X3, 2026-09-27) is a **host-side gameplay script** inside a world (`x3:script/button_logic`), in the world's namespace. `mover` (added for X2, 2026-09-26) is a **reusable mover definition** inside a world (`x2:mover/basic_slide_door`), in the world's namespace, unique among the world's mover definitions; placed movers name it and MegaMod resolves the reference once at load |
| name | `[a-z][a-z0-9_]*`, at most 48 bytes; unique within namespace and type |
| whole | at most 96 bytes; `:` and `/` appear exactly once each, as separators |

- **Characters:** lowercase ASCII letters, digits and underscore only. No
  hyphens, dots, spaces, Unicode, escapes or extra separators -- anything
  else is rejected, not escaped. (No current name needs a hyphen.)
- **Case:** the canonical form is lowercase; comparison is byte for byte,
  never case-folded. A legacy name with capitals gets a *proposed* lowercase
  form and must be mapped explicitly (an alias); two names that only differ
  after lowering are a reported collision, never merged.
- **Duplicates:** the same full ID from two packages is an error.
- **Not identity:** file names and paths, display labels, Halo tag paths,
  source-engine class names, array positions.
- **Version** is package metadata, not part of the ID.

Examples: `megamod:weapon/ion_rifle`, `lab_demo:world/relay_test`,
`owner:character/goku`. Built-in content the runtime provides without a
package (the Halo Trial's own weapons, which loadouts name today) would sit
under a reserved namespace, `halo_trial:weapon/assault_rifle`.

This is the grammar in the research note
[CONTENT_ID_GRAMMAR_RECOMMENDATION](https://github.com/madpai/megamod-showdown/blob/main/docs/research/CONTENT_ID_GRAMMAR_RECOMMENDATION.md),
tightened by the audit: hyphens dropped (nothing needs them), the type list
fixed to today's four kinds. The `kind:namespace.name` form in
ENTITY_COMPARISON.md is superseded.

## The audit

```sh
assetlab ids <packages or folders...> [--namespace OWNER] [--json]
```

Reads only the manifests of `.oalmap` / `.oalasset` files and reports, per
package: the proposed ID, the legacy name it came from, what the runtime
uses as its key today, and any problem -- duplicate IDs, normalisation
collisions, invalid or overlong names, unknown kinds, a map file whose name
differs from its `map_id`, a package file named unlike its `name`, and no
declared namespace ("ambiguous ownership"; `--namespace` supplies the
assumption). It also lists legacy references that would need aliases:
loadouts that name weapons by display label (resolved to a package weapon's
proposed ID, or to the built-in namespace), and weapon/ability bases that
name Halo weapons by tag path fragment. Output is sorted and independent of
argument order and folder location. It never writes.
`tests/test_ids.py` covers each finding on synthetic packages.

## Findings on the owner's current bundle (2026-09-26)

35 packages (7 worlds, 14 characters, 13 weapons, 1 sound pack):

- **No package declares a namespace** (all 35). Every ID today would rest
  on an assumed owner.
- **One duplicate identity:** the lit variant of cs_office was compiled from
  the same BSP, so its manifest says `map_id: cs_office`, the same as the
  unlit package. The runtime tells them apart only by file name
  (`cs_office_lit`). Any ID scheme needs the compiler to give variants their
  own `map_id` (or an explicit variant field).
- **Every other name is already canonical:** 33 packages would get their
  current name as their ID with no alias.
- **Legacy references:** 19 loadout slots name package weapons by display
  label, 9 name built-in Halo weapons by label (e.g. "pistol", "plasma
  pistol"), and 25 weapon/ability bases name Halo weapons by tag path
  fragment (matched by substring at runtime today). All 53 resolve to a
  proposed ID; none is dangling.

## What would come next (not done)

1. The compiler writes a `namespace` and gives map variants distinct
   `map_id`s -- an additive manifest field, no binary change.
2. Loadouts and bases gain ID references beside the legacy labels, with the
   audit checking both agree.
3. Only then could the network send a name-to-index table at join instead
   of requiring identical roster order (see MegaMod's content compatibility
   contract), and saves record IDs.
