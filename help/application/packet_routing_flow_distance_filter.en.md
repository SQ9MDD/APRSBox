# Position Zone Filter

This filter passes a frame only when decoded position falls inside at least one configured zone.

How it works:

- 1 to 3 zones may be configured,
- each zone has a center and a radius,
- zones are evaluated with OR logic,
- the GUI requires 1 to 3 complete center+radius zones; only malformed legacy data with no valid zone is skipped,
- if the frame has no decodable position, the filter is skipped,
- only a frame with position outside all zones is rejected.

Use it when:

- traffic should be limited to a geographic area,
- local-only routing should depend on coverage area or event area.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
