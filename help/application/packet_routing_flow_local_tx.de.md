# Local TX

Dies ist die Quelle fur Frames, die APRSBox lokal selbst erzeugt.

Dazu gehoren:

- Beacons,
- Statuspakete,
- Wetter,
- Objekte,
- Items,
- Bulletins,
- Nachrichten.

Nicht dazu gehoren:

- per RF empfangener Verkehr,
- bereits digipeateter Verkehr,
- normaler Eingangsverkehr vom TNC.

In der Praxis:

- das ist der interne Sendestrom der Anwendung,
- `Local TX` darf nur zu `TX APRS-IS` oder `Black Hole` fuhren.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
