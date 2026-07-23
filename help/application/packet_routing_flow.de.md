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
- `APRS-IS-Quelle -> APRS-IS-Eingangssicherheitsregel -> APRS-IS-Rufzeichen- und Radiusregel -> APRS-IS-zu-RF-TX-Sicherheitsregel -> TX RF` - leitet explizit erlaubte Netzwerkpakete sicher an ein physisches TNC weiter.
- `... -> Black Hole` - Diagnose, Trockenlauf und Regeltests ohne Weiterleitung.

## Wie man eine Regel aufbaut

1. Quelle auswählen.
2. Ziel auswählen.
3. Nur die Blöcke hinzufügen, die für diesen Pfad gebraucht werden.
4. Regel speichern und das Ausführungsprotokoll prüfen.

## Quellblöcke

- [Empfänger RF](packet_routing_flow_receiver_rf.de.md)
- [Local TX](packet_routing_flow_local_tx.de.md)
- [Obligatorische Sicherheitsregeln APRS-IS → RF](packet_routing_flow_rf_guard.de.md)

## Filter- und Regelblöcke

- [APRS-IS-Uplink-Sicherheitsregel](packet_routing_flow_strict_filter.de.md)
- [APRS-IS-Nachrichten-Zustellregel](packet_routing_flow_aprsis_message_delivery_rule.de.md)
- [APRS-IS-Rufzeichen- und Radiusregel](packet_routing_flow_aprsis_callsign_radius_rule.de.md)
- [RF-Digipeating-Pfadregel](packet_routing_flow_path_rule_and_digi_guard.de.md)
- [RF-Duplikatverzögerungsfilter](packet_routing_flow_duplicate_filter.de.md)
- [Filter für direkten RF-Empfang](packet_routing_flow_direct_only.de.md)
- [DIGI-Filter](packet_routing_flow_digi_filter.de.md)
- [Quellrufzeichenfilter](packet_routing_flow_callsign_filter.de.md)
- [APRS-Pakettypfilter](packet_routing_flow_packet_type_filter.de.md)
- [APRS-Symbolfilter](packet_routing_flow_icon_filter.de.md)
- [Positionszonenfilter](packet_routing_flow_distance_filter.de.md)
- [Übertragungsratenfilter](packet_routing_flow_rate_limit_filter.de.md)

## Zielblöcke

- [TX RF](packet_routing_flow_tx_rf.de.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.de.md)
- [Black Hole](packet_routing_flow_black_hole.de.md)

## Kurze Hinweise

- `TX APRS-IS` erfordert die `APRS-IS-Uplink-Sicherheitsregel`.
- RF-zu-RF-Übertragung erfordert die `RF-Digipeating-Pfadregel`.
- `Local TX` kann nur in `TX APRS-IS` oder `Black Hole` enden.
- Ein `APRS-IS → RF`-Flow enthält genau vier obligatorische Systemregeln. Optionale Filter können nicht hinzugefügt werden. Adressierter Verkehr zu einer kürzlich lokal über RF gehörten Station kann durch die Nachrichtenzustellregel zugelassen werden; anderer Verkehr benötigt Rufzeichen **und** Radius, und eine leere Konfiguration leitet keine weiteren Pakete weiter.
