# Obligatorische Sicherheitsregeln APRS-IS → RF

Ein Flow `APRS-IS -> RF` leitet ausgewaehlte APRS-IS-Pakete kontrolliert an ein physisches Funkinterface weiter. Ziel darf nur ein aktives, TX-faehiges physisches TNC sein. APRS-IS und RX-only-Interfaces sind als Ziel gesperrt.

## Erforderliche Reihenfolge

`APRS-IS-Quelle -> APRS-IS-Eingangssicherheitsregel -> APRS-IS-Rufzeichen- und Radiusregel -> APRS-IS-zu-RF-TX-Sicherheitsregel -> TX RF`

Alle drei Regeln werden für `APRS-IS → RF` automatisch eingefügt. Sie können nicht entfernt, deaktiviert, umgangen, verschoben oder doppelt hinzugefügt werden. Diesem eingeschränkten Flow können keine optionalen Filter hinzugefügt werden. Backend und Runtime erzwingen denselben Schutz auch bei manuell veränderten gespeicherten Daten.

## APRS-IS-Rufzeichen- und Radiusregel

Der Filter enthaelt nur eine Liste von Quellrufzeichen und einen Radius. Beide Bedingungen sind mit `AND` verknuepft: Die Paketquelle muss exakt einem eingetragenen Rufzeichen entsprechen und die dekodierte Paketposition muss innerhalb des Radius um die in `My Station` konfigurierten Koordinaten liegen.

Der Rufzeichenabgleich ist strikt und umfasst die SSID. `SQ9MDD` passt nur zu `SQ9MDD`, `SQ9MDD-1` nur zu `SQ9MDD-1`. Platzhalter werden nicht unterstuetzt. Pro Zeile wird ein Rufzeichen eingetragen.

Eine leere Konfiguration ist gueltiges `default deny`. Pakete ohne dekodierte Position sowie alle Pakete bei fehlenden gueltigen `My Station`-Koordinaten werden ebenfalls abgelehnt.

## APRS-IS-Eingangssicherheitsregel

Der erste Guard erzwingt APRS- und q-construct-Validierung, Loop Prevention, Sperren fuer `NOGATE`, `RFONLY` und `TCPXX` sowie eine erste normalisierte Duplikatpruefung zwischen RF und APRS-IS. `TCPIP` allein wird nicht gesperrt.

## APRS-IS-zu-RF-TX-Sicherheitsregel

Der letzte Guard ist direkt vor `TX RF` fixiert. Er steuert viscous delay, die erneute Duplikatpruefung danach, Token-Bucket-Limits pro Flow und Quelle, Zielbereitschaft, Third-Party-Kapselung und das AX.25-Laengenlimit. Der Internetpfad wird vor TX entfernt.

Standardwerte: `5 s` viscous delay, pro Flow `6 Pakete/min` mit Burst `3`, pro Quellrufzeichen `2 Pakete/min` mit Burst `2` und `30 s` Duplikatfenster. Pending-Pakete liegen nur im Speicher, werden durch eine gleiche lokale RF-Kopie abgebrochen und nach einem Neustart nicht wiederhergestellt.

APRS-IS-Text wird als Unicode dekodiert, AX.25 APRS auf RF verwendet jedoch 7-Bit-ASCII. Vor der Kapselung werden typische Zeichen transliteriert (`°` zu `deg`, `µ`/`μ` zu `u`, typografische Striche und Anführungszeichen zu ASCII); nicht unterstützte Zeichen werden zu `?`. Größenprüfung und KISS-Kodierung verwenden exakt diesen bereinigten Payload.

Verwendet wird der konfigurierte RF-Ausgangspfad; ein leerer Pfad bedeutet direct. Akzeptierte Pakete gehen in die vorhandene RF/KISS-Queue. Eigene APRS-IS-to-RF-Zähler verhindern eine Anrechnung auf DIGI- und physische TNC-RX-Statistiken.

## Navigation

[Zurueck zu Packet Flow](packet_routing_flow.de.md)
