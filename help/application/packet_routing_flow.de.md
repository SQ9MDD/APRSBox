# Packet-Flow-Regelreferenz

Diese Hilfeseite ist eine kurze Orientierung dazu, wofür der `Packet Flow`-Editor dient und wann die typischen Pfade verwendet werden. Die detaillierte Beschreibung jedes Blocks ist weiter unten verlinkt.

## Was dieser Bildschirm macht

Eine Routing-Regel beschreibt, was APRSBox mit einem Paket tun soll, nachdem es empfangen oder lokal erzeugt wurde.

Jede Regel hat eine Quelle, null oder mehr Zwischenblöcke und ein Endziel.

Pakete laufen immer von oben nach unten. Wenn ein Block ein Paket verwirft, wird der Rest der Regel nicht mehr ausgeführt.

## Wann Packet Flow verwendet wird

- `Empfänger RF -> TX APRS-IS` - klassischer iGate-Uplink von RF nach APRS-IS.
- `Empfänger RF -> TX RF` - klassischer Digipeater-Pfad auf Funk.
- `Local TX -> TX APRS-IS` - lokal erzeugte Frames wie Beacons, Wetter, Objekte, Items, Bulletins und Nachrichten.
- `APRS-IS -> Input Guard -> Default Deny -> RF TX Guard -> TX RF` - leitet explizit erlaubte Netzwerkpakete sicher an ein physisches TNC weiter.
- `... -> Black Hole` - Diagnose, Trockenlauf und Regeltests ohne Weiterleitung.

## Wie man eine Regel aufbaut

1. Quelle auswählen.
2. Ziel auswählen.
3. Nur die Blöcke hinzufügen, die für diesen Pfad gebraucht werden.
4. Regel speichern und das Ausführungsprotokoll prüfen.

## Quellblöcke

- [Empfänger RF](packet_routing_flow_receiver_rf.de.md)
- [Local TX](packet_routing_flow_local_tx.de.md)
- [APRS-IS als Quelle und RF Guard](packet_routing_flow_rf_guard.de.md)

## Filter- und Regelblöcke

- [Strenger Filter](packet_routing_flow_strict_filter.de.md)
- [Pfadregel und DIGI-Schutz](packet_routing_flow_path_rule_and_digi_guard.de.md)
- [Duplikatfilter (viscous-delay)](packet_routing_flow_duplicate_filter.de.md)
- [Nur direkt](packet_routing_flow_direct_only.de.md)
- [DIGI-Filter](packet_routing_flow_digi_filter.de.md)
- [Rufzeichenfilter](packet_routing_flow_callsign_filter.de.md)
- [Pakettypfilter](packet_routing_flow_packet_type_filter.de.md)
- [Symbolfilter](packet_routing_flow_icon_filter.de.md)
- [Distanzfilter](packet_routing_flow_distance_filter.de.md)
- [Ratenbegrenzungsfilter](packet_routing_flow_rate_limit_filter.de.md)

## Zielblöcke

- [TX RF](packet_routing_flow_tx_rf.de.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.de.md)
- [Black Hole](packet_routing_flow_black_hole.de.md)

## Kurze Hinweise

- `TX APRS-IS` erfordert den Block `Strenger Filter`.
- `TX RF` erfordert den Block `Pfadregel und DIGI-Schutz`.
- `Local TX` kann nur in `TX APRS-IS` oder `Black Hole` enden.
- Ein `APRS-IS -> RF`-Flow erhält automatisch obligatorische Input- und RF-TX-Guards um den strikten Default-Deny-Filter für Rufzeichen und Radius. Rufzeichen und Radius sind mit `AND` verknüpft; eine leere Konfiguration leitet keine Pakete weiter.
