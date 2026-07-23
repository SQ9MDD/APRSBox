# APRS-IS als Quelle und RF Guard

Ein Flow `APRS-IS -> RF` leitet ausgewaehlte APRS-IS-Pakete kontrolliert an ein physisches Funkinterface weiter. Ziel darf nur ein aktives, TX-faehiges physisches TNC sein. APRS-IS und RX-only-Interfaces sind als Ziel gesperrt.

## Erforderliche Reihenfolge

`APRS-IS source -> RF Guard -> Default-Deny-Filter fuer Rufzeichen + Radius -> TX RF`

`RF Guard` wird bei der Auswahl einer APRS-IS-Quelle automatisch eingefuegt. Der Block kann nicht entfernt, deaktiviert, umgangen oder doppelt hinzugefuegt werden. Backend und Runtime erzwingen den Schutz auch bei manuell veraenderten gespeicherten Daten.

## Default-Deny-Filter fuer Rufzeichen und Radius

Der Filter enthaelt nur eine Liste von Quellrufzeichen und einen Radius. Beide Bedingungen sind mit `AND` verknuepft: Die Paketquelle muss exakt einem eingetragenen Rufzeichen entsprechen und die dekodierte Paketposition muss innerhalb des Radius um die in `My Station` konfigurierten Koordinaten liegen.

Der Rufzeichenabgleich ist strikt und umfasst die SSID. `SQ9MDD` passt nur zu `SQ9MDD`, `SQ9MDD-1` nur zu `SQ9MDD-1`. Platzhalter werden nicht unterstuetzt. Pro Zeile wird ein Rufzeichen eingetragen.

Eine leere Konfiguration ist gueltiges `default deny`. Pakete ohne dekodierte Position sowie alle Pakete bei fehlenden gueltigen `My Station`-Koordinaten werden ebenfalls abgelehnt.

## RF-Schutz

Der Guard erzwingt APRS- und q-construct-Validierung, Loop Prevention, Sperren fuer `NOGATE`, `RFONLY` und `TCPXX`, Duplikatnormalisierung zwischen RF und APRS-IS, viscous delay, eine zweite Duplikatpruefung, Rate Limits, Third-Party-Kapselung und das AX.25-Laengenlimit. `TCPIP` allein wird nicht gesperrt; der Internetpfad wird vor TX entfernt.

Standardwerte: `5 s` viscous delay, pro Flow `6 Pakete/min` mit Burst `3`, pro Quellrufzeichen `2 Pakete/min` mit Burst `2` und `30 s` Duplikatfenster. Pending-Pakete liegen nur im Speicher, werden durch eine gleiche lokale RF-Kopie abgebrochen und nach einem Neustart nicht wiederhergestellt.

Der originale Payload bleibt erhalten. Verwendet wird der konfigurierte RF-Ausgangspfad; ein leerer Pfad bedeutet direct. Akzeptierte Pakete gehen in die vorhandene RF/KISS-Queue. Eigene APRS-IS-to-RF-Zaehler verhindern eine Anrechnung auf DIGI- und physische TNC-RX-Statistiken.

## Navigation

[Zurueck zu Packet Flow](packet_routing_flow.de.md)
