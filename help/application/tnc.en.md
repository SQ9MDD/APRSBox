# Interfaces

The Interfaces tab configures APRSBox input and output connections. Radio interfaces can receive KISS/TNC2, transmit outbound frames, and optionally share a LAN KISS port. The APRS-IS connection supports both reception and transmission controlled by `Packet Routing`.

## Interface list

The table shows configured interfaces. Click a row to edit it.

- `Status` shows configuration and runtime state, such as connected, error, or disabled.
- `TX control` shows the TX block for a physical TNC. For APRS-IS, the routing icon shows whether an active flow ending in `TX APRS-IS` exists.
- `LAN` shows whether APRSBox exposes a KISS/TNC proxy for LAN clients.

Disabling an interface stops its receive processing. Disabling a radio interface also stops the outbound service from using it. For APRS-IS, the `Enable APRS-IS connection` switch controls the entire shared RX/TX connection. When it is disabled, active flows targeting `TX APRS-IS` remain configured but cannot transmit. Beacon, WX, object, bulletin, and message settings can still reference a disabled radio interface, but transmission will be skipped or fail depending on context.

## Interface types

- `TCP` connects to a TNC or software that exposes KISS over TCP. `Path / Address / Filter` usually has the `host:port` format, for example `127.0.0.1:8001`.
- `SERIALL` uses a local serial port, for example `/dev/ttyUSB0` or `/dev/ttyACM0`, and requires a valid `Baud Rate`.
- `OpenWebRX MQTT (RX only)` receives packets from OpenWebRX MQTT. This type is receive-only: TX is blocked and LAN proxy is disabled.
- `APRS-IS (RX/TX)` contains the complete APRS-IS connection configuration directly in the interface form. It receives TNC2 lines matching the server filter and sends frames accepted by a `Receiver RF -> TX APRS-IS` or `Local TX -> TX APRS-IS` flow over the same connection. It does not use KISS. Only one APRSIS interface may exist.

For OpenWebRX MQTT, the address field should be an `mqtt://` or `mqtts://` URL with the topic in the path, for example `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

For APRSIS, `APRS-IS receive filter` is the APRS-IS server filter. New interfaces default to `m/20`; another valid filter such as `r/52.23/21.01/50` can be entered. Server, port, login, and passcode are saved from the same form. The separate `iGATE settings` tab is no longer used.

## Configuration fields

- `Name` is displayed in logs, interface lists, and TX selectors.
- `Band` describes the interface band.
- `Enabled` activates a physical interface in the APRSBox runtime. For APRS-IS, the `Enable APRS-IS connection` label enables the shared connection used for reception and transmission; flows ending in `TX APRS-IS` still decide which frames may be sent.
- `Block TX on this interface` allows receiving traffic but blocks outbound transmission.
- `TX Min Gap (s)` sets the minimum pause between transmissions on this TNC. The allowed range is `0.2` to `1.2` seconds.
- `RX Silence Reconnect Timeout (s)` applies to serial interfaces. After RX silence longer than this value, the serial broker can force a reconnect. `0` disables this watchdog.

`Baud Rate` is used only for `SERIALL`. For APRSIS, fields specific to a physical TNC are hidden: serial settings, RF TX block/pacing, and LAN proxy. Transmission to APRS-IS requires both an enabled connection and a matching `Packet Routing` flow.

The APRS-IS source and target are available in the `Packet Routing` editor only when an APRSIS interface is defined. Without that interface, a flow referencing APRS-IS also cannot be saved or enabled again.

The APRSIS interface form also contains:

- `Server` and `Port` — the APRS-IS server address, defaulting to `rotate.aprs2.net:14580`.
- `Login callsign / callsign-SSID` — may be left blank to use the identity from `My Station`.
- `Passcode` — may be left blank so APRSBox derives the standard APRS-IS passcode from the login callsign.
- `APRS-IS receive filter` — controls traffic received from the server but does not restrict frames sent by `Packet Routing`.

Below the APRSIS form, the current connection state and expandable diagnostics show active flows, the last error, and TX counters. An APRS-IS passcode is not an account password; it is the standard code derived from a callsign.

## iGate routing and APRS-IS safety

- `Receiver RF -> TX APRS-IS` creates the classic iGate uplink from radio to APRS-IS.
- `Local TX -> TX APRS-IS` sends APRSBox-generated frames to APRS-IS, including beacon, status, weather, objects, items, bulletins, and messages.

Both modes require a verified APRS-IS login. `pass -1` identifies an unverified receive-only client and does not allow RF-received frames to be sent. For RF uplinks, APRSBox uses `qAO` when the receiving TNC has no usable TX return path, or `qAR` when the TNC permits TX and an active `APRS-IS -> RF` flow provides message return. Locally generated frames use `TCPIP*`.

The `TX APRS-IS` target has a system safety filter that rejects, among other cases, frames containing `TCPIP` / `TCPXX`, `NOGATE` / `RFONLY`, and malformed third-party encapsulation. See [Packet Routing](packet_routing.en.md) for detailed flow construction.

## Expose Port

`Expose Port` exposes the TNC connection through APRSBox as a TCP port for LAN clients. APRSBox relays frames between the physical TNC and clients.

- `Allow TX from remote clients` allows LAN clients to send frames to the TNC. When disabled, clients can only receive.
- `Bind Address` defines the listen address. `0.0.0.0` means all network interfaces.
- `Port` is the TCP port exposed by APRSBox. Up to 3 simultaneous clients are supported.
- `Whitelist` restricts access to IPv4 addresses or CIDR networks. Enter one item per line; commas are also accepted.

Do not enable remote TX on an untrusted network. If you expose the port beyond the local machine, configure a whitelist.

## When to use multiple interfaces

Multiple active interfaces can run in parallel. Received traffic is handled per interface, while radio transmission depends on the selector used in each tab, such as `My Station`, `WX`, objects, bulletins, messages, or `Packet Routing` rules. APRS-IS receive traffic is visible in traffic history, station details, and the map, but is excluded from all APRSBox statistics.

If you only need input from OpenWebRX, use `OpenWebRX MQTT (RX only)`. If you need full radio RX/TX, use `TCP` or `SERIALL`. For reception and/or transmission over the APRS-IS network, use `APRS-IS (RX/TX)` and the appropriate `Packet Routing` flows.
