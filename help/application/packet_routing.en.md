# Packet routing rules

This screen shows the list of rules that control APRS packet flow inside APRSBox.

At this level you mainly manage:

- which rules exist,
- the order of the rules,
- which rules are enabled,
- which rule you want to open and edit.

## What this tab is for

The `Packet Routing` tab is used to manage traffic logic between APRSBox inputs and outputs.

Most common uses:

- forwarding packets from `Receiver RF` to `TX APRS-IS`,
- building digipeater rules such as `Receiver RF -> TX RF`,
- routing locally generated traffic with `Local TX -> TX APRS-IS`,
- creating diagnostic paths ending in `Black Hole`,
- separating multiple RF inputs into different routing scenarios.

## How to read the rule list

Each row shows:

- rule order,
- name and description,
- input source,
- final target,
- enabled or disabled state.

The order of rules matters operationally, so keeping the list readable is helpful.

## Typical scenarios

### `Receiver RF -> TX APRS-IS`

Used when locally received RF traffic should be forwarded to APRS-IS.

### `Receiver RF -> TX RF`

Used when APRSBox should behave as a digi and repeat traffic further on RF.

### `Local TX -> TX APRS-IS`

Used when objects, status, weather, bulletins, or other APRSBox-generated frames should be sent to APRS-IS.

### `Receiver RF -> Black Hole`

Used for testing and observing traffic without forwarding it further.

## Where the detailed description is

The full description of blocks, filters, configuration fields, and ready-made rule layouts is available in the `Packet Flow` help:

[Detailed Packet Flow reference](packet_routing_flow.en.md)
