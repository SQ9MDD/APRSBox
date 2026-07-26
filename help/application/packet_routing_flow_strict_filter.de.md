# APRS-IS-Uplink-Sicherheitsregel

Dies ist der Systemsicherheitsblock fur Regeln, die in `TX APRS-IS` enden.

Fur Frames aus `Empfänger RF`:

- er pruft den kompletten ausseren Pfad,
- er lehnt den Frame ab, wenn der Pfad `TCPIP`, `TCPXX`, `NOGATE` oder `RFONLY` enthalt,
- er validiert Third-Party-Kapselung,
- bei gueltigen Third-Party-Frames pruft er auch den inneren Pfad auf dieselben gesperrten Tokens.

Fur `Local TX` ist er strenger:

- der Frame muss in Metadaten als lokal von APRSBox erzeugt markiert sein,
- Third-Party-Kapselung wird abgelehnt,
- jede `q..`-Konstruktion im Pfad wird abgelehnt,
- `TCPIP`, `TCPXX`, `NOGATE` und `RFONLY` bleiben gesperrt.

Wichtige Hinweise:

- bei `TX APRS-IS` ist diese Regel verpflichtend,
- er ersetzt keine RF-Digi-Pfadlogik,
- wenn TNC2-Parsing fehlschlaegt, wird der Frame abgelehnt.

Typische Anwendungsfalle:

- `Empfänger RF -> APRS-IS-Uplink-Sicherheitsregel -> TX APRS-IS`,
- `Local TX -> APRS-IS-Uplink-Sicherheitsregel -> TX APRS-IS`.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
