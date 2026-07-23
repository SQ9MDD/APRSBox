# Source Callsign Filter

This filter checks only the packet source callsign. It does not inspect path, digi hops, or destination.

How it works:

- without `*`, the match is exact,
- `SQ9MDD` does not match `SQ9MDD-4`,
- `*` wildcard may be used anywhere,
- `allow` behaves like a whitelist,
- `deny` behaves like a blacklist.

Practical consequences:

- an empty `allow` list rejects everything,
- an empty `deny` list passes everything.

Examples:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Use it when:

- club, test, service, or operator traffic should be separated,
- a known source should be blocked or isolated.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
