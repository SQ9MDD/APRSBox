# Icon Filter

This filter compares the APRS symbol exactly in `table+code` form.

How it works:

- matching is exact and does not use wildcard,
- it compares the exact symbol value returned by APRSBox parser,
- in `allow` mode, no match means reject,
- in `deny` mode, no match means pass,
- if symbol cannot be decoded, `allow` rejects and `deny` passes.

Examples:

- `/>`,
- `\\l`.

Use it when:

- selected symbol classes should get their own path,
- symbol meaning matters more than packet type.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
