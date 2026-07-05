# TX RF

This target sends the packet through the selected radio modem.

Use it for:

- local digi paths,
- cross-band forwarding,
- RF port-to-port forwarding.

Typical layout:

```text
Receiver RF -> Duplicate Filter (viscous-delay) -> Path rule and DIGI guard -> TX RF
```

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
