# Packet-Routing-Regeln

Dieser Bildschirm zeigt die Liste der Regeln, die den APRS-Paketfluss innerhalb von APRSBox steuern.

Auf dieser Ebene verwaltest du vor allem:

- welche Regeln existieren,
- in welcher Reihenfolge sie stehen,
- welche Regeln aktiv sind,
- welche Regel du zur Bearbeitung offnen willst.

## Wofur diese Registerkarte dient

Die Registerkarte `Packet Routing` dient zur Verwaltung der Verkehrslogik zwischen Eingangen und Ausgangen von APRSBox.

Haufige Verwendungen:

- Weiterleitung von Paketen von `Empfänger RF` zu `TX APRS-IS`,
- Aufbau von Digipeater-Regeln wie `Empfänger RF -> TX RF`,
- Routing von lokal erzeugtem Verkehr mit `Local TX -> TX APRS-IS`,
- Diagnosepfade mit Ziel `Black Hole`,
- Trennung mehrerer RF-Eingange in unterschiedliche Routing-Szenarien.

## Wie man die Regelliste liest

Jede Zeile zeigt:

- die Reihenfolge der Regel,
- Name und Beschreibung,
- die Eingangsquelle,
- das Endziel,
- den Aktivstatus.

Die Reihenfolge der Regeln ist auch operativ wichtig, deshalb sollte die Liste ubersichtlich bleiben.

## Typische Szenarien

### `Empfänger RF -> TX APRS-IS`

Wird verwendet, wenn lokal empfangener RF-Verkehr an APRS-IS weitergeleitet werden soll.

### `Empfänger RF -> TX RF`

Wird verwendet, wenn APRSBox als Digi arbeiten und Verkehr per RF weitergeben soll.

### `Local TX -> TX APRS-IS`

Wird verwendet, wenn Objekte, Status, Wetter, Bulletins oder andere lokal von APRSBox erzeugte Frames an APRS-IS gesendet werden sollen.

### `Empfänger RF -> Black Hole`

Wird fur Tests und Beobachtung verwendet, ohne Verkehr weiterzuleiten.

## Wo die Detailbeschreibung ist

Die vollstandige Beschreibung von Blocken, Filtern, Konfigurationsfeldern und fertigen Regelmustern steht in der Hilfe zu `Packet Flow`:

[Detaillierte Packet-Flow-Referenz](packet_routing_flow.de.md)
