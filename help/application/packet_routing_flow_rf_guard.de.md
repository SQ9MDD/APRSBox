# APRS-IS als Quelle und RF Guard

Ein Flow `APRS-IS -> RF` leitet ausgewaehlte APRS-IS-Pakete kontrolliert an ein physisches Funkinterface weiter. Ziel darf nur ein aktives, TX-faehiges physisches TNC sein. APRS-IS und RX-only-Interfaces sind als Ziel gesperrt.

## Erforderliche Reihenfolge

`APRS-IS source -> RF Guard -> explizite Allow-Regeln -> TX RF`

`RF Guard` wird bei der Auswahl einer APRS-IS-Quelle automatisch eingefuegt. Der Block kann nicht entfernt, deaktiviert, umgangen oder doppelt hinzugefuegt werden. Backend und Runtime erzwingen den Schutz auch bei manuell veraenderten gespeicherten Daten.

## Explizite Allow-Regeln

Alle Regeln sind inklusiv. Bedingungen innerhalb einer Regel sind mit `AND`, getrennte Regeln mit `OR` verknuepft. Die Bedingungen verwenden Daten des vorhandenen Parsers und der Filter: Pakettyp, Quellrufzeichen, Destination, Nachrichtenadressat, Objektname, Symbol und Entfernungsbereich.

Eine leere Regelliste ist eine gueltige `default deny`-Konfiguration: Der Flow kann gespeichert und aktiviert werden, leitet aber keine Pakete weiter.

## RF-Schutz

Der Guard erzwingt APRS- und q-construct-Validierung, Loop Prevention, Sperren fuer `NOGATE`, `RFONLY` und `TCPXX`, Duplikatnormalisierung zwischen RF und APRS-IS, viscous delay, eine zweite Duplikatpruefung, Rate Limits, Third-Party-Kapselung und das AX.25-Laengenlimit. `TCPIP` allein wird nicht gesperrt; der Internetpfad wird vor TX entfernt.

Standardwerte: `5 s` viscous delay, pro Flow `6 Pakete/min` mit Burst `3`, pro Quellrufzeichen `2 Pakete/min` mit Burst `2` und `30 s` Duplikatfenster. Pending-Pakete liegen nur im Speicher, werden durch eine gleiche lokale RF-Kopie abgebrochen und nach einem Neustart nicht wiederhergestellt.

Der originale Payload bleibt erhalten. Verwendet wird der konfigurierte RF-Ausgangspfad; ein leerer Pfad bedeutet direct. Akzeptierte Pakete gehen in die vorhandene RF/KISS-Queue. Eigene APRS-IS-to-RF-Zaehler verhindern eine Anrechnung auf DIGI- und physische TNC-RX-Statistiken.

## Navigation

[Zurueck zu Packet Flow](packet_routing_flow.de.md)
