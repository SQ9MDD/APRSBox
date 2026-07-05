# Direct Only

This filter passes only directly heard packets.

Actual behavior:

- it checks only whether path already contains any consumed hop marked with `*`,
- it does not care about still unconsumed hops such as `WIDE1-1`,
- `...,WIDE1-1:` passes,
- `...,SR5ABC*,WIDE1-1:` is rejected.

Use it when:

- the rule should react only to directly heard stations,
- already repeated traffic should be ignored,
- you want to inspect direct coverage separately.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
