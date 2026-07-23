# APRS-IS-Nachrichten-Zustellregel

Diese obligatorische Systemregel stellt den Nachrichtenpfad eines bidirektionalen IGates im eingeschränkten Flow `APRS-IS → RF` bereit. Sie wird nach der Eingangssicherheitsprüfung und vor der Rufzeichen- und Radiusregel ausgeführt.

## Weitergeleiteter Verkehr

Die Regel kann Nachrichten, `ack`, `rej` und adressierte Anfragen für ein exakt angegebenes lokales Rufzeichen mit SSID sowie das nächste Positionspaket eines erfolgreich zu RF weitergeleiteten Absenders zulassen.

Bulletins, Gruppennachrichten, Telemetriedefinitionen und allgemeine Anfragen gehören nicht zum obligatorischen Nachrichtenverkehr.

## Lokaler Empfänger

Der Empfänger muss innerhalb der letzten 60 Minuten direkt über eine beliebige aktive TNC-Schnittstelle gehört worden sein, auf der RF-Senden erlaubt ist. Die SSID ist Bestandteil des Vergleichs. Die Nachricht wird abgelehnt, wenn der Empfänger in diesem Zeitraum nicht direkt gehört wurde, die Schnittstelle deaktiviert ist oder RF-Senden gesperrt hat, der Empfänger kürzlich als Internet-Station gesehen wurde oder der Absender im gleichen lokalen RF-Bereich gehört wurde.

## Konfiguration

Diese Systemregel hat keine Einstellungen. APRSBox verwendet automatisch alle aktiven sendefähigen TNC-Schnittstellen, auf denen RF-Senden nicht gesperrt ist. Deaktivierte, reine Empfangs- und TX-gesperrte Schnittstellen werden nicht berücksichtigt.

Eine zugelassene Nachricht umgeht die Rufzeichen- und Radiusregel, nicht jedoch TX-Sicherheit, Duplikatprüfung, Ratenbegrenzung, Third-Party-Kapselung oder AX.25-Längenprüfung.

[APRS-IS-Rufzeichen- und Radiusregel](packet_routing_flow_aprsis_callsign_radius_rule.de.md)

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
