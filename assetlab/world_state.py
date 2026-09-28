"""X8 world replication budget, derived from MegaMod's exported contract.

The compiled entity order is runtime order: authored placements followed by
prefab children in canonical instance order. Only movers and relays need
network state. This module does not change package bytes or world keys.
"""
from __future__ import annotations

from .resources import CONTRACT

CONTRACT_STATE = CONTRACT['world_state']
LIMITS = CONTRACT_STATE['limits']
ENCODING = CONTRACT_STATE['encoding']
KINDS = CONTRACT_STATE['kinds']


def snapshot_bytes(movers: int, relays: int, moving: int = 0) -> int:
    """Bytes of one complete WORLD_STATE payload for these counts."""
    if not (0 <= moving <= movers <= LIMITS['spatial'] and 0 <= relays <= LIMITS['logical_flags']):
        raise ValueError('world state counts exceed the engine contract')
    runs = (movers + ENCODING['spatial_run_max'] - 1) // ENCODING['spatial_run_max']
    flag_bytes = (relays + ENCODING['flags_per_byte'] - 1) // ENCODING['flags_per_byte']
    return (ENCODING['header'] + runs * ENCODING['spatial_run'] +
            (movers - moving) * ENCODING['mover_at_rest'] + moving * ENCODING['mover_moving'] +
            (ENCODING['flag_run'] + flag_bytes if relays else 0))


def count(kinds):
    """Classify all placed and expanded kinds, preserving engine order."""
    channels = {'spatial': [], 'logical': [], 'host-only': []}
    objects = []
    for runtime, kind in enumerate(kinds):
        channel = KINDS[kind]['channel']
        index = len(channels[channel]) if channel != 'host-only' else None
        channels[channel].append(runtime)
        objects.append({'runtime': runtime, 'kind': kind, 'channel': channel, 'index': index})
    movers, relays = len(channels['spatial']), len(channels['logical'])
    rest, busy = snapshot_bytes(movers, relays), snapshot_bytes(movers, relays, movers)
    return {'protocol': CONTRACT_STATE['protocol'], 'runtime_objects': len(objects),
            'spatial': movers, 'logical': relays, 'host_only': len(channels['host-only']),
            'snapshot_bytes': {'at_rest': rest, 'all_moving': busy,
                               'packet_at_rest': rest + ENCODING['packet_header']},
            'objects': objects}


def errors(kinds):
    """Refuse a world the engine cannot represent in one snapshot."""
    movers = sum(KINDS[k]['channel'] == 'spatial' for k in kinds)
    relays = sum(KINDS[k]['channel'] == 'logical' for k in kinds)
    out = []
    if len(kinds) > LIMITS['runtime_objects']:
        out.append(f"world has more than {LIMITS['runtime_objects']} runtime objects (world entities), exceeding limit {LIMITS['runtime_objects']}")
    if movers > LIMITS['spatial']:
        out.append(f"world has {movers} movers, exceeds the spatial replication limit {LIMITS['spatial']}")
    if relays > LIMITS['logical_flags']:
        out.append(f"world has {relays} relays, exceeds the logical state limit {LIMITS['logical_flags']}")
    return out
