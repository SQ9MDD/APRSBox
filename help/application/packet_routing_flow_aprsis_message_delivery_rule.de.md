# APRS-IS-Nachrichten-Zustellregel

Diese obligatorische Systemregel stellt den Nachrichtenpfad eines bidirektionalen IGates im eingeschränkten Flow `APRS-IS → RF` bereit. Sie wird nach der Eingangssicherheitsprüfung und vor der Rufzeichen- und Radiusregel ausgeführt.

## Weitergeleiteter Verkehr

Die Regel kann Nachrichten, `ack`, `rej` und adressierte Anfragen für ein exakt angegebenes lokales Rufzeichen mit SSID sowie das nächste Positionspaket eines erfolgreich zu RF weitergeleiteten Absenders zulassen.

Bulletins, Gruppennachrichten, Telemetriedefinitionen und allgemeine Anfragen gehören nicht zum obligatorischen Nachrichtenverkehr.

## Lokaler Empfänger

Der Empfänger muss kürzlich über eine konfigurierte lokale RF-Quelle gehört worden sein. Die SSID ist Bestandteil des Vergleichs. Die Nachricht wird abgelehnt, wenn der Empfänger zu alt ist, zu viele benutzte DIGI-Hops benötigt, kürzlich als Internet-Station gesehen wurde oder der Absender im gleichen lokalen RF-Bereich gehört wurde.

## Konfiguration

- **Lokale RF-Empfangsquellen**: ein Schnittstellenname pro Zeile; leer verwendet die RF-Zielschnittstelle.
- **Gültigkeit des lokalen Empfangs**: 5 bis 60 Minuten, Standard 60.
- **Maximale benutzte DIGI-Hops**: 0 bis 2, Standard 0 für direkten Empfang.

Eine zugelassene Nachricht umgeht die Rufzeichen- und Radiusregel, nicht jedoch TX-Sicherheit, Duplikatprüfung, Ratenbegrenzung, Third-Party-Kapselung oder AX.25-Längenprüfung.

[APRS-IS-Rufzeichen- und Radiusregel](packet_routing_flow_aprsis_callsign_radius_rule.de.md)

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
