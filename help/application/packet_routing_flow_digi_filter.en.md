# DIGI Filter

This filter does not look at the whole path and does not inspect still unconsumed hops. It checks only hops already marked with `*`, after removing that star.

Actual behavior:

- from `SR5BCD-2*,WIDE1-1` it sees only `SR5BCD-2`,
- from `WIDE1-1` it sees nothing, because no hop has been consumed yet,
- patterns are matched against consumed hops; `*` wildcard may be used anywhere,
- `allow` passes only when at least one consumed hop matches,
- `deny` rejects only when at least one consumed hop matches.

Practical consequences:

- an empty `allow` list rejects everything,
- an empty `deny` list passes everything,
- `*` in `deny` blocks every already-digipeated frame,
- `*` in `deny` does not block truly direct frames, because there is no consumed hop to match.

Examples:

- path `SR5BCD-2*,WIDE1-1` plus pattern `SR5BCD*` -> match,
- path `SR5ABC*,WIDE1-1` plus `deny: *` -> drop,
- path `WIDE1-1` plus `deny: *` -> pass.

Use it when:

- only traffic coming through selected digis should pass,
- traffic already repeated by specific intermediate stations should be excluded.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
