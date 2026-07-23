# APRS-IS als Quelle und zwei Guards

Ein Flow `APRS-IS -> RF` leitet ausgewaehlte APRS-IS-Pakete kontrolliert an ein physisches Funkinterface weiter. Ziel darf nur ein aktives, TX-faehiges physisches TNC sein. APRS-IS und RX-only-Interfaces sind als Ziel gesperrt.

## Erforderliche Reihenfolge

`APRS-IS source -> APRS-IS Input Guard -> Default-Deny-Filter fuer Rufzeichen + Radius -> RF TX Guard -> TX RF`

Beide Guards werden fuer `APRS-IS -> RF` automatisch eingefuegt. Sie koennen nicht entfernt, deaktiviert, umgangen, verschoben oder doppelt hinzugefuegt werden. Backend und Runtime erzwingen denselben Schutz auch bei manuell veraenderten gespeicherten Daten.

## Default-Deny-Filter fuer Rufzeichen und Radius

Der Filter enthaelt nur eine Liste von Quellrufzeichen und einen Radius. Beide Bedingungen sind mit `AND` verknuepft: Die Paketquelle muss exakt einem eingetragenen Rufzeichen entsprechen und die dekodierte Paketposition muss innerhalb des Radius um die in `My Station` konfigurierten Koordinaten liegen.

Der Rufzeichenabgleich ist strikt und umfasst die SSID. `SQ9MDD` passt nur zu `SQ9MDD`, `SQ9MDD-1` nur zu `SQ9MDD-1`. Platzhalter werden nicht unterstuetzt. Pro Zeile wird ein Rufzeichen eingetragen.

Eine leere Konfiguration ist gueltiges `default deny`. Pakete ohne dekodierte Position sowie alle Pakete bei fehlenden gueltigen `My Station`-Koordinaten werden ebenfalls abgelehnt.

## APRS-IS Input Guard

Der erste Guard erzwingt APRS- und q-construct-Validierung, Loop Prevention, Sperren fuer `NOGATE`, `RFONLY` und `TCPXX` sowie eine erste normalisierte Duplikatpruefung zwischen RF und APRS-IS. `TCPIP` allein wird nicht gesperrt.

## RF TX Guard

Der letzte Guard ist direkt vor `TX RF` fixiert. Er steuert viscous delay, die erneute Duplikatpruefung danach, Token-Bucket-Limits pro Flow und Quelle, Zielbereitschaft, Third-Party-Kapselung und das AX.25-Laengenlimit. Der Internetpfad wird vor TX entfernt.

Standardwerte: `5 s` viscous delay, pro Flow `6 Pakete/min` mit Burst `3`, pro Quellrufzeichen `2 Pakete/min` mit Burst `2` und `30 s` Duplikatfenster. Pending-Pakete liegen nur im Speicher, werden durch eine gleiche lokale RF-Kopie abgebrochen und nach einem Neustart nicht wiederhergestellt.

Der originale Payload bleibt erhalten. Verwendet wird der konfigurierte RF-Ausgangspfad; ein leerer Pfad bedeutet direct. Akzeptierte Pakete gehen in die vorhandene RF/KISS-Queue. Eigene APRS-IS-to-RF-Zaehler verhindern eine Anrechnung auf DIGI- und physische TNC-RX-Statistiken.

## Navigation

[Zurueck zu Packet Flow](packet_routing_flow.de.md)
