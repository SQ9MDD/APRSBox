# Station Readiness

This card is a simple first-start checklist. It shows what is still missing from the configuration, but it does not test antenna quality, RF coverage, or whether other stations can hear your frames.

## Before you start — three terms

- **RF** is radio traffic received or transmitted through a TNC.
- **APRS-IS** is the Internet APRS network.
- A **flow** is a “source → destination” routing rule, such as `Receiver RF → TX APRS-IS`.

Complete the steps in order. Interfaces create the sources and destinations that you will later use in `My Station` and `Packet Routing`.

## Recommended configuration order

### 1. Interfaces

Open `Interfaces` first and add:

- at least one active `TCP` or `SERIALL` radio interface; `OpenWebRX MQTT` is receive-only,
- an `APRS-IS (RX/TX)` interface when the station should receive from or send frames to APRS-IS.

Verify that the interfaces are enabled, physical TNC TX is not unintentionally blocked, and APRS-IS reaches the connected state.

**After this step:** `Radio interfaces` and `APRS-IS connection` should be green. If only some configured radio interfaces are enabled, the radio state is dark yellow. No active radio interface gives a red state.

[Interfaces help](tnc.en.md)

### 2. My Station

Then configure `My Station`:

- callsign and SSID,
- coordinates and APRS symbol,
- beacon comment, interval, and path,
- TX destination: one radio interface, all active interfaces, or `Internal TX`,
- automatic beacon transmission when periodic beacons are required.

`Internal TX` creates a frame inside APRSBox but does not send it to a physical TNC. Choose it when routing alone should decide where the frame goes. Selecting one radio interface or all active interfaces transmits the beacon over RF.

**After this step:** `Beacon defined` should be green. Defining a beacon alone does not send it to APRS-IS; the flow in step 3 controls that route.

[My Station help](station.en.md)

### 3. Packet Routing

Finally, open `Packet Routing` and add the active flows required by the station role.

For a fully green card, APRSBox checks:

- `Local TX → TX APRS-IS` — sends locally generated beacons, status, weather, objects, items, bulletins, and messages directly to APRS-IS,
- `Receiver RF → TX APRS-IS` for every active RF input — the classic iGate uplink,
- `APRS-IS → TX RF` for every active TX-capable interface — the guarded return path for qualifying APRS-IS messages,
- `Receiver RF → TX RF` between the required active interfaces — digi or cross-band operation according to the station design.

[Packet Routing help](packet_routing.en.md)

**After this step:** `Local TX → APRS-IS` and the required cells for every active interface should be green. Match any missing direction on the card with the list above.

## Own frames and APRS-IS

A frame transmitted by your radio interface is not automatically uploaded directly to APRS-IS. It may appear there when a local or external RF iGate hears it, but that depends on RF coverage, filters, and the availability of that gateway.

To upload your own frames independently of an RF iGate, create an active `Local TX → TX APRS-IS` flow. This applies both to a frame sent to `Internal TX` and to your own frame transmitted over a radio interface at the same time.

This is separate from `Receiver RF → TX APRS-IS`: `Local TX` handles frames created by APRSBox, while `Receiver RF` handles frames actually received from radio. Do not create a flow from the radio output; locally generated frames always use `Local TX` as their routing source.

## Reading the colors

- green — the required item is active or the flow exists,
- dark yellow — configuration is partial or a flow is missing,
- red — no active interface or a connection error,
- gray — the interface is disabled or the direction does not apply.

If you intentionally do not provide a role such as digipeating or `APRS-IS → RF`, its field may remain a warning. This does not mean the runtime is broken; it shows the difference from the complete readiness matrix.
