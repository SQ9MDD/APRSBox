# APRS-IS-Rufzeichen- und Radiusregel

Diese obligatorische Systemregel ist die explizite Zulassungsliste im eingeschränkten Flow `APRS-IS → RF`. Sie arbeitet nach Default Deny: Ein Paket läuft nur weiter, wenn sowohl das exakte Quellrufzeichen als auch die dekodierte Position zur Konfiguration passen.

## Bedingungen

Die Bedingungen sind mit `AND` verknüpft:

1. Die Paketquelle entspricht exakt einem Rufzeichen aus der Liste.
2. Die Paketposition liegt innerhalb des konfigurierten Radius um die Koordinaten in `My Station`.

Ein passendes Rufzeichen ohne passende Position wird abgelehnt. Ebenso wird eine Position innerhalb des Radius abgelehnt, wenn das Quellrufzeichen nicht in der Liste steht.

## Quellrufzeichen

- Geben Sie ein Rufzeichen pro Zeile ein.
- Groß-/Kleinschreibung spielt keine Rolle; ansonsten ist der Vergleich strikt und umfasst die SSID.
- `SQ9MDD` passt nur zu `SQ9MDD`.
- `SQ9MDD-1` passt nur zu `SQ9MDD-1`.
- Platzhalter werden nicht unterstützt.
- Das Rufzeichen muss eine gültige AX.25-Adresse sein: 1–6 Buchstaben oder Ziffern mit optionaler SSID von `0` bis `15`.
- Es können höchstens 50 Rufzeichen konfiguriert werden.

## Radius

Die GUI akzeptiert einen Radius von `0,1` bis `1000 km` in Schritten von `0,1 km`. Die Entfernung wird von den in `My Station` konfigurierten Stationskoordinaten berechnet, nicht vom Empfangsmodem oder einem anderen Paket.

Das Paket wird abgelehnt, wenn:

- seine APRS-Position nicht dekodiert werden kann,
- `My Station` keine gültigen Koordinaten besitzt,
- seine Position außerhalb des Radius liegt.

## Leere und unvollständige Konfiguration

Rufzeichenliste und Radius müssen beide ausgefüllt oder beide leer sein. Eine teilweise ausgefüllte Konfiguration kann nicht gespeichert werden.

Sind beide Felder leer, ist die Konfiguration gültig und verwirft absichtlich jedes Paket. Dadurch bleibt eine nicht konfigurierte Regel standardmäßig sicher.

## Platzierung

Die Regel wird automatisch zwischen `APRS-IS-Eingangssicherheitsregel` und `APRS-IS-zu-RF-TX-Sicherheitsregel` eingefügt und verwaltet. Sie kann nicht entfernt, deaktiviert, dupliziert oder verschoben werden. Diesem Flow können außerdem keine optionalen Filter hinzugefügt werden.

## Navigation

[Obligatorische Sicherheitsregeln APRS-IS → RF](packet_routing_flow_rf_guard.de.md)

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
