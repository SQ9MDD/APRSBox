# Interfaces

The Interfaces tab configures APRSBox input and output connections. Radio interfaces can receive KISS/TNC2, transmit outbound frames, and optionally share a LAN KISS port. The APRS-IS connection supports both reception and transmission controlled by `Packet Routing`.

## Interface list

The table shows configured interfaces. Click a row to edit it.

- `Status` shows configuration and runtime state, such as connected, error, or disabled.
- `TX control` shows the TX block for a physical TNC. For APRS-IS, the routing icon shows whether an active flow ending in `TX APRS-IS` exists.
- `LAN` shows whether APRSBox exposes a KISS/TNC proxy for LAN clients.

Disabling an interface stops its receive processing. Disabling a radio interface also stops the outbound service from using it. For APRS-IS, the `Enable APRS-IS reception` switch controls reception only; an active flow targeting `TX APRS-IS` may still keep the same connection open and send data through it. Beacon, WX, object, bulletin, and message settings can still reference a disabled radio interface, but transmission will be skipped or fail depending on context.

## Interface types

- `TCP` connects to a TNC or software that exposes KISS over TCP. `Path / Address / Filter` usually has the `host:port` format, for example `127.0.0.1:8001`.
- `SERIALL` uses a local serial port, for example `/dev/ttyUSB0` or `/dev/ttyACM0`, and requires a valid `Baud Rate`.
- `OpenWebRX MQTT (RX only)` receives packets from OpenWebRX MQTT. This type is receive-only: TX is blocked and LAN proxy is disabled.
- `APRS-IS (RX/TX)` uses the connection configured in iGate settings. It receives TNC2 lines matching the server filter and sends frames accepted by a `Receiver RF -> TX APRS-IS` or `Local TX -> TX APRS-IS` flow over the same connection. It does not use KISS. Only one APRSIS interface may exist.

For OpenWebRX MQTT, the address field should be an `mqtt://` or `mqtts://` URL with the topic in the path, for example `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

For APRSIS, `Path / Address / Filter` is the APRS-IS server filter. New interfaces default to `m/20`; another valid filter such as `r/52.23/21.01/50` can be entered. Server, port, callsign, and passcode continue to come from iGate settings.

## Configuration fields

- `Name` is displayed in logs, interface lists, and TX selectors.
- `Band` describes the interface band.
- `Enabled` activates a physical interface in the APRSBox runtime. For APRS-IS, the `Enable APRS-IS reception` label enables reception only; TX is controlled independently by flows ending in `TX APRS-IS`.
- `Block TX on this interface` allows receiving traffic but blocks outbound transmission.
- `TX Min Gap (s)` sets the minimum pause between transmissions on this TNC. The allowed range is `0.2` to `1.2` seconds.
- `RX Silence Reconnect Timeout (s)` applies to serial interfaces. After RX silence longer than this value, the serial broker can force a reconnect. `0` disables this watchdog.

`Baud Rate` is used only for `SERIALL`. For APRSIS, fields specific to a physical TNC are hidden: serial settings, RF TX block/pacing, and LAN proxy. This does not block transmission to APRS-IS, which is controlled by `Packet Routing`.

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
