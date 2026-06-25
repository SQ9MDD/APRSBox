# Changelog

## 1.8.47.dev - 2026-06-25
- `GUI / sidebar / scrolling`: als Reaktion auf GitHub `issue #54` (`Menu panel independent scrolling`) scrollt die Sidebar auf dem Desktop jetzt unabhaengig vom Hauptinhalt, waehrend der Scrollbalken ausgeblendet bleibt.

## 1.8.46.dev - 2026-06-23
- `Settings / Global settings / Traffic frames`: eine globale Aufbewahrung fuer den Verkehrsverlauf wurde hinzugefuegt (`1h` bis `6h` in Schritten von `30 min`, plus `12h` und `24h`, Standard `1h`); sie steuert das Cleanup von `traffic_frames`, und die Sichtbarkeit von Stationen, Objekten und Tracks auf der Karte folgt jetzt direkt diesem Datenfenster.
- `Messages / TX / multi-TNC`: die Fehlerbehandlung fuer `Transmit on all active interfaces` wurde korrigiert; ein einzelner TNC-Fehler markiert die gesamte Nachricht nicht mehr sofort als `failed`, solange dieselbe TX-Runde noch auf anderen Interfaces laeuft oder eines davon bereits erfolgreich gesendet hat.
- `Messages / retry`: eine Nachricht wechselt jetzt erst dann nach `failed`, wenn die komplette Senderunde fuer dasselbe `scheduled_at` ohne irgendeinen Job im Zustand `sent` endet; damit funktioniert der normale Retry/ACK-Ablauf in Multi-TNC-Faellen vom Typ `fail + success` wieder korrekt.

## 1.8.45.dev - 2026-06-22
- `My Station / Beacon`: das Stationsrufzeichen im Beacon-Formular wurde auf maximal 6 druckbare ASCII-Zeichen begrenzt; die Validierung erfolgt auch im Backend.
- `My Station / Beacon`: die Felder `callsign` und `Beacon Path` werden jetzt sowohl im Formular als auch beim Speichern auf Grossbuchstaben normalisiert.
- `My Station / Location`: die manuelle Bearbeitung von `latitude` und `longitude` wurde gesperrt; Koordinaten werden jetzt nur noch ueber die Schaltflaeche `Get location` gesetzt.
- `Settings / Global settings`: die Schaltflaeche `Save Global Settings` wurde an das Ende des Blocks verschoben, und `Coverage fill opacity` verwendet jetzt standardmaessig `10%`, sofern der Benutzer keinen eigenen Wert gespeichert hat.
- `Settings / Global settings / I18N`: fehlende Uebersetzungen fuer das Feld `Icon set`, die Optionsliste und den Hilfetext unter dem Select wurden ergaenzt.

## 1.8.44 - 2026-06-22

### Stable release
- Stabile Uebernahme der Funktionen aus dem Branch `dev` nach `main`.

### Included development snapshots
- Aenderungen von `1.8.25.dev` bis `1.8.43.dev`

### Highlights
- `Map / UX / diagnostics`: die Kartenansicht und die Situationsuebersicht wurden ueberarbeitet: besseres Viewport-Layout, `Latest packet` / letzter Digi im Scroller, Sichtbarkeitsfilter pro TNC, aufgeraeumte Tooltips und verfeinertes APRS-Icon-Rendering.
- `Routing / TX / APRS-IS`: die logische Quelle `Local TX`, der neutrale Modus `Internal TX`, harte Guards fuer APRS-IS-Uplink und lokal erzeugte Frames sowie per-TNC-Pacing fuer TX-Warteschlangen wurden hinzugefuegt.
- `DIGI / flow engine`: `Path rule and DIGI guard` wurde erweitert, der `Rate limit filter` aktiviert, eine sichere Reihenfolge fuer RF-Schritte erzwungen und TNC-Umbenennungen werden jetzt in Flow-Referenzen uebernommen.
- `Objects / Bulletins / content`: geplante und wiederkehrende Objekt-Sendungen, `Valid until` mit Minutengenauigkeit, Objekt-Timestamp beim realen TX, manuelles `Send now`, ausgeblendete `killed`-Objekte sowie lokale Markdown-Hilfe fuer `Objects` und `Bulletins`.
- `Integrations / RX / parser`: `OpenWebRX MQTT (RX only)` mit `APRS/SONDE/ADSB`, lokaler Deduplizierung, erweiterter Diagnostik sowie verbesserter Mic-E-Decodierung und Darstellung wurde hinzugefuegt.
- `Maintenance / GUI / I18N`: Spanisch und mehrsprachige Changelogs (`PL/EN/ES/DE`), Docker-Mode-Guards fuer Host-Aktionen, SQLite-Runtime-Diagnostik mit sicherem Reset, Telegram/Webhook-Benachrichtigungen, das neue Sidebar-Logo und lokale Hilfedateien wurden hinzugefuegt.

## 1.8.43.dev - 2026-06-21
- `Traffic Monitor / KISS RX`: leere KISS-Datenframes (`0x00` ohne Payload) von TCP/IP-TNCs werden jetzt ignoriert, sodass der Traffic Monitor kein Rauschen vom Typ `AX.25 decode failed (payload too short (0B))` mehr zwischen gueltigen Paketen anzeigt.
- `Changelog / I18N`: eine deutsche Changelog-Datei und die `DE`-Auswahl anhand der aktuellen GUI-Sprache wurden hinzugefuegt.

### Hinweise
- Aeltere Eintraege sind noch nicht ins Deutsche uebersetzt.
