# Pakettypfilter

Dieser Filter arbeitet auf dem, was der APRSBox-Decoder als APRS-Gruppe oder APRS-Typ erkannt hat.

Uebliche Selektoren:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Praktische Bedeutung:

- `message` umfasst auch ACK/REJ, bulletin und announcement,
- `weather` bedeutet nur weather-only-Frames,
- eine Position mit Wetterdaten bleibt `position`,
- zur Rueckwaertskompatibilitaet funktionieren auch alte Selektoren wie `M`, `S`, `O` und `W` sowie rohe Typcodes des Parsers.

So arbeitet er:

- im Modus `allow` passiert der Frame nur, wenn erkannte Gruppe oder Typ zur Liste passt,
- im Modus `deny` faellt der Frame nur, wenn erkannte Gruppe oder Typ zur Liste passt,
- wenn der Decoder Gruppe/Typ nicht bestimmen kann, lehnt `allow` ab und `deny` laesst durch.

Verwende ihn, wenn:

- Positionen, Objekte, Nachrichten oder Wetter getrennt geroutet werden sollen,
- eine Regel auf eine Verkehrsklasse begrenzt bleiben soll.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
