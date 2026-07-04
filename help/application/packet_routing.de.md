# Packet-Routing-Regeln

Diese Seite zeigt die Regeln, mit denen APRSBox APRS-Pakete zwischen Eingangen und Ausgangen weiterleitet. Eine Regel hat eine Quelle, optionale Filter in der Mitte und ein Ziel.

Die Regeln werden von oben nach unten ausgewertet. Die Reihenfolge in der Liste ist wichtig, besonders wenn mehrere Regeln ahnlichen Verkehr beschreiben.

## Wofur Packet Routing verwendet wird

Packet Routing definiert, was APRSBox mit einem Paket tun soll, nachdem es per RF empfangen oder lokal von der Anwendung erzeugt wurde.

Typische Verwendung:

- per RF empfangene Frames zu APRS-IS weiterleiten,
- RF-Verkehr zu einem RF-Ausgang digipeaten,
- lokal von APRSBox erzeugte Frames zu APRS-IS senden,
- ausgewahlten Verkehr nur protokollieren,
- Verkehr verwerfen, der nicht weiterlaufen soll.

## Haufige Szenarien

### `RF -> APRS-IS`

Das ist der typische iGate-Fall. APRSBox empfängt einen Frame vom Funk und leitet ihn nach dem erforderlichen Systemfilter zu APRS-IS weiter.

Verwendung:

- wenn lokal gehorter RF-Verkehr auf APRS-IS erscheinen soll,
- wenn verschiedene RF-Ports APRS-IS mit getrennten Regeln versorgen sollen,
- wenn du RF-Empfang und Internet-Uplink klar trennen willst.

### `RF -> RF`

Das ist der klassische Digipeater-Fall. Ein Frame kommt per RF herein und wird nach den konfigurierten Filtern wieder per RF gesendet.

Verwendung:

- wenn du ein lokales Digi aufbaust,
- wenn du Cross-Band oder Port-zu-Port-RF umsetzen willst,
- wenn nur ausgewahlte Verkehrsarten, Gebiete, Pfade oder Rufzeichen wiederholt werden sollen.

### `Local TX -> APRS-IS`

Dieser Pfad ist fur Frames gedacht, die APRSBox selbst erzeugt, zum Beispiel Beacon, Status, Wetter, Objekte, Items, Bulletins und Nachrichten.

Verwendung:

- wenn lokal erzeugter Anwendungsverkehr zu APRS-IS hochgeladen werden soll,
- wenn Objekte, Bulletins oder Nachrichten APRSBox ohne RF-Pfad verlassen sollen,
- wenn lokale Sendelogik von eingehender RF-Logik getrennt bleiben soll.

### `RF -> Black Hole` oder `Local TX -> Black Hole`

Das ist ein Diagnosepfad. Das Paket lauft durch die Regel, wird aber nicht weiter ausgesendet.

Verwendung:

- wenn du eine Regel sicher testen willst,
- wenn du sehen willst, wie Pakete durch Filter laufen,
- wenn du Verkehr protokollieren, aber nicht senden willst.

## Quellen und Ziele

`Receiver RF` bedeutet Pakete, die von einem konfigurierten Funkmodem empfangen wurden.

`Local TX` bedeutet Frames, die APRSBox selbst erzeugt, zum Beispiel Beacon, Status, Wetter, Objekte, Items, Bulletins und Nachrichten.

Ziele sind `TX RF`, `TX APRS-IS` und `Black Hole` fur reine Protokollierung.

`Local TX` kann nur zu APRS-IS oder zur reinen Protokollierung geroutet werden.

## Detaillierte Blockbeschreibung

Eine ausfuhrliche Beschreibung von Filtern, Regeln und Zielen steht hier:

[Detaillierte Beschreibung der Routing-Blocke](packet_routing_flow.de.md)

## Systemschutz

`TX APRS-IS`-Regeln sind auf einen verpflichtenden `Strict Filter` beschrankt.

`TX RF`-Regeln erfordern einen aktiven Schritt `Path rule and DIGI guard`.

Nur eine aktive Regel kann zur gleichen Zeit dasselbe Quelle-Ziel-Paar bedienen.
