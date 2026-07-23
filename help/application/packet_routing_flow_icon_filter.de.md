# APRS-Symbolfilter

Dieser Filter vergleicht das APRS-Symbol exakt im Format `table+code`.

So arbeitet er:

- der Vergleich ist exakt und verwendet keinen Wildcard,
- er vergleicht genau den Symbolwert, den der APRSBox-Parser geliefert hat,
- im Modus `allow` bedeutet kein Treffer Ablehnung,
- im Modus `deny` bedeutet kein Treffer Durchlass,
- wenn das Symbol nicht decodiert werden kann, lehnt `allow` ab und `deny` laesst durch.

Beispiele:

- `/>`,
- `\\l`.

Verwende ihn, wenn:

- bestimmte Symbolklassen einen eigenen Pfad bekommen sollen,
- die Symbolbedeutung wichtiger ist als der Pakettyp.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
