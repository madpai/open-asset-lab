"""Compatibility reports: one per imported map, and a table across maps."""
from __future__ import annotations
import json
from pathlib import Path


def game_dir_search(game_dirs):
    """A game directory mounted the way Source mounts one: the directory as
    an unpacked root, and every `*_dir.vpk` in it. Order is preserved."""
    roots, vpks = [], []
    for d in game_dirs:
        d = Path(d).expanduser()
        if not d.is_dir():
            raise FileNotFoundError(f'game directory not found: {d}')
        roots.append(d)
        vpks.extend(sorted(p for p in d.glob('*_dir.vpk') if p.is_file()))
    return roots, vpks


def markdown(compat):
    """One map's compatibility report as Markdown."""
    g, m, sp, st, en = compat['geometry'], compat['materials'], compat['spawns'], compat['static_props'], compat['entities']
    lines = [f"## {compat['map']}", '',
             f"- **BSP:** v{compat['bsp_version']} ({compat['bsp_version_label']})",
             f"- **Geometry:** {g['triangles']:,} triangles ({g['world_triangles']:,} world/brush), "
             f"{g['collision_triangles']:,} collide; {g['brush_entities_converted']} brush entities "
             f"({g['brush_entities_hidden_at_spawn']} hidden at spawn, not drawn); "
             f"{g['water_faces']} water faces; excluded by flag: {g['faces_excluded_by_flag'] or 'none'}",
             f"- **Displacements:** {compat['displacements']['converted']} of {compat['displacements']['in_bsp']}",
             f"- **Materials:** {m['used']} used, {m['resolved']} resolved, {m['placeholder']} placeholder, "
             f"{m['non_solid']} non-solid; {m['textures_downsampled']} downsampled; "
             f"{m['texture_bytes']/2**20:.1f} MiB RGBA",
             f"- **Static props:** lump v{st['lump_version']}, {st['placed']} of {st['in_bsp']} placed, "
             f"{st['model_entities_placed']} model entities; unresolved models: {len(st['models_unresolved'])}",
             f"- **Entities:** {en['total']} total; spawn {en['spawn']}, brush {en['brush']}, model {en['model']}, "
             f"not geometry {en['not_geometry']}, unsupported {en['unsupported']}",
             f"- **Spawns:** {sp['total']} ({sp['red']} red, {sp['blue']} blue, {sp['either']} either), "
             f"{sp['grounded']} on ground, {sp['rejected_no_ground']} rejected (no ground)",
             f"- **Dependencies:** {compat['dependencies']['missing']} missing; found in {compat['dependencies']['found_in'] or 'nothing'}",
             f"- **Lumps not used (unsupported):** {', '.join(sorted(compat['lumps']['unsupported'])) or 'none'}"]
    if compat['unsupported_features']:
        lines += ['- **Unsupported features:**'] + [f'  - {x}' for x in compat['unsupported_features']]
    if en['unsupported_classes']:
        lines.append('- **Unsupported entity classes:** ' + ', '.join(f'{k} x{v}' for k, v in en['unsupported_classes'].items()))
    if m['features_not_reproduced']:
        lines.append('- **Material features not reproduced:** ' + ', '.join(f'{k} ({v})' for k, v in m['features_not_reproduced'].items()))
    if compat['warnings']:
        shown = compat['warnings'][:8]
        lines += [f'- **Warnings ({len(compat["warnings"])}):**'] + [f'  - {w}' for w in shown]
        if len(compat['warnings']) > len(shown):
            lines.append(f'  - ... {len(compat["warnings"]) - len(shown)} more in compatibility.json')
    return '\n'.join(lines) + '\n'


def table(compats):
    """Several maps side by side."""
    head = '| map | BSP | triangles | collide | disp | materials (ok/placeholder) | props placed | spawns (R/B/any) | unsupported entities | warnings |'
    rows = [head, '|' + '---|' * 10]
    for c in compats:
        g, m, sp = c['geometry'], c['materials'], c['spawns']
        rows.append(f"| {c['map']} | v{c['bsp_version']} | {g['triangles']:,} | {g['collision_triangles']:,} | "
                    f"{c['displacements']['converted']}/{c['displacements']['in_bsp']} | {m['resolved']}/{m['placeholder']} | "
                    f"{c['static_props']['placed']}/{c['static_props']['in_bsp']} + {c['static_props']['model_entities_placed']} ent | "
                    f"{sp['red']}/{sp['blue']}/{sp['either']} | {c['entities']['unsupported']} | {len(c['warnings'])} |")
    return '\n'.join(rows) + '\n'


def write(compat, directory):
    directory = Path(directory)
    (directory/'compatibility.json').write_text(json.dumps(compat, indent=2, sort_keys=True) + '\n')
    (directory/'compatibility.md').write_text(markdown(compat))
