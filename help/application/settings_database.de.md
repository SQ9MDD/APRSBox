# Datenbankwartung

Dieses Panel zeigt den Zustand des SQLite-Speichers und bietet manuelle Bereinigungsaktionen. Ereignisprotokolle werden nach Mitternacht automatisch gekürzt; `VACUUM` und das Zurücksetzen der Laufzeitdaten bleiben manuell.

## Diagnose

- Datei-, WAL- und SHM-Größe zeigen den aktuell von SQLite belegten physischen Speicher.
- `Zugewiesene Datenbankgröße`, `Freigebbarer Speicher` und `Seitengeometrie` werden aus SQLite-Seiten berechnet.
- `Integritätsprüfung` ist das Ergebnis von `PRAGMA quick_check`. Untersuchen Sie jedes Ergebnis außer `ok` vor Wartungsarbeiten.
- `VACUUM-Empfehlung` vergleicht den freigebbaren Speicher mit dem im Panel angezeigten Schwellenwert.
- Liste und Summe der Laufzeittabellen zeigen den exakten aktuellen Umfang des Resets.

## VACUUM ausführen

`VACUUM` baut die SQLite-Datei neu auf, damit unbenutzte Seiten an das Dateisystem zurückgegeben werden können. Der Vorgang kann dauern und die Datenbank vorübergehend sperren. Zuvor müssen alle TNC-Schnittstellen deaktiviert werden.

## Laufzeitprotokolle/-daten zurücksetzen

Der Reset löscht Betriebsverläufe wie Ereignisprotokolle, empfangenen Verkehr, Routing-Laufzeitstatus, APRS-IS-Laufzeitstatistik, WX-Laufzeitcache, Radarstatus und Bandbedingungsaggregate.

TNC- und Routing-Konfiguration, Stations- und WX-Einstellungen, APRS-Inhalte, Kartenquellen, Benutzer und APRS-Nachrichtenverlauf bleiben erhalten. Vor dem Reset müssen alle TNC-Schnittstellen deaktiviert werden.
