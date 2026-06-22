# Changelog

## 1.8.45.dev - 2026-06-22
- `My Station / Beacon`: das Stationsrufzeichen im Beacon-Formular wurde auf maximal 6 druckbare ASCII-Zeichen begrenzt; die Validierung erfolgt auch im Backend.
- `My Station / Location`: die manuelle Bearbeitung von `latitude` und `longitude` wurde gesperrt; Koordinaten werden jetzt nur noch ueber die Schaltflaeche `Get location` gesetzt.

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
