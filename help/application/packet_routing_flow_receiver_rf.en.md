# Receiver RF

Source for packets received by a selected radio modem.

Use it when:

- the rule should react to traffic from the air,
- several RF receivers need separate routing logic.

In practice:

- every `Receiver RF -> ...` rule begins here,
- the selected modem decides which input can enter the rule.

## Navigation

[Back to Packet Flow rule reference](packet_routing_flow.en.md)
