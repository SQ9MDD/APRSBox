# Changelog

## 1.9.2.dev - 2026-07-29
- `GUI / Menü`: Reihenfolge und Bereiche der Seitenleiste wurden neu geordnet und die Benutzerleiste auf kompakte, ausgerichtete Symbole reduziert.

## 1.9.1.dev - 2026-07-29
- `APRS-Notfallalarme`: eine eigene Registerkarte fasst Frames nach vollständigem Quellrufzeichen zusammen, führt Verlauf und Zähler, unterstützt zeitlich begrenztes oder unbegrenztes Stummschalten und löscht Alarme sicher, ohne Frames aus dem Traffic Monitor zu entfernen.
- `Alarme / GUI`: ein globales Alarm-Modal, Markierungen und Links im Traffic Monitor, Alarm-Liste und -Details, ein Navigationszähler sowie erneutes Anzeigen bei weiteren nicht stummgeschalteten Frames wurden hinzugefügt; die Hilfe erklärt die nötige Browser-Berechtigung für automatische Tonwiedergabe.
- `Dashboard`: die Startseite wurde mit übersichtlicheren bereichsbezogenen KPI, einem RF-Aktivitätsdiagramm und kompakten Übersichten zu Konfiguration, Diensten und Runtime überarbeitet.
- `Band Condition / Karte`: der Ausbreitungsverlauf bietet jetzt `24h / 7d / 30d / 365d` und einen Punkt für die aktuelle Stunde; außerdem wurden der letzte Kartenstand und die globale Deckkraft der Reichweitenfüllung korrigiert.

## 1.9.0 - 2026-07-26
- `Stable release`: ein grosses Paket von Aenderungen aus `1.8.45.dev–1.8.57.dev` wurde nach `main` uebernommen, darunter APRS-IS/iGate, Nachrichten, Bandbedingungen, Traffic Monitor, Karte, GUI, Leistung und der Alpine-Installer.

## 1.8.57.dev - 2026-07-25
- `Bandbedingungen / Schnittstellen`: die Ausbreitungsbewertung ist jetzt pro Schnittstelle optional und standardmaessig deaktiviert; als ueberwachte Baender stehen `2 m` und `70 cm` zur Wahl, ohne manuelle Auswahl von Referenzstationen.
- `Bandbedingungen / W0–W5-Modell`: die uebliche Reichweite und Hoerbarkeit fester Stationen wird fuer jede Schnittstelle automatisch gelernt. Die erste Bewertung erscheint nach 24 Stunden; zur Erkennung von Bandoeffnungen werden Stationszahl, typische Reichweite, Entfernungen, weit entfernte Stationen und neu gehoerte geografische Gebiete beruecksichtigt.
- `Bandbedingungen / Sicherheit und Verlauf`: ein konservativer, mit der Datenmenge wachsender Sicherheitsindex, der nach dem ersten Tag auf 30%, nach einer Woche auf 55% und nach 30 Tagen auf 90% begrenzt ist, eine einfache W0–W5-Anzeige mit klarer Skalenlegende und stuendlichem Verlauf der letzten 365 Tage sowie ein separater dezenter Modelldaten-Block mit erfassten Werten, Lernphase und Fortschritt bis zur ersten und ausgereiften Bewertung wurden hinzugefuegt.
- `Bandbedingungen / Leistung`: die Analyse wurde aus dem Hot Path des Frame-Empfangs in den gemeinsamen Fuenf-Minuten-Aggregator verschoben; Frames werden nur einmal geparst und Detailbeobachtungen sowie Verlauf besitzen eine begrenzte Aufbewahrungszeit.

## 1.8.56.dev - 2026-07-24
- `Nachrichten / APRS-IS`: ACKs und automatische Antworten an die lokale Station wurden korrigiert; sie laufen ueber `Local TX → APRS-IS` zurueck, ohne RF-Sendung.
- `Traffic Monitor / Farben`: Zeilen werden jetzt nach Herkunft und Richtung der Frames markiert; hinzu kamen eine modale Legende sowie eine gelbe Warnmarkierung für `APRS-IS → RF` mit dem Badge `IS → RF`.
- `APRS-IS → RF`: Rufzeichen und Radius lassen sich nun gemeinsam leeren, um den reinen Nachrichtenmodus wiederherzustellen.

## 1.8.55.dev - 2026-07-23
- `iGate / Nachrichten`: die obligatorische Zustellregel verwendet automatisch alle aktiven TNCs mit erlaubtem TX; geeignete Nachrichten und die zugehoerige Absenderposition umgehen die Rufzeichen- und Radiusregel, leere Regelfelder aktivieren den reinen Nachrichtenmodus.
- `Routing / Logs`: Schritte, die fuer ein Paket nicht gelten oder umgangen wurden, erscheinen als `uebersprungen` statt `bestanden`.

## 1.8.54.dev - 2026-07-23
- `APRS-IS / Routing`: APRS-IS wurde als Interface sowie sicheres Routing `APRS-IS → RF` hinzugefügt.
- `iGate / Nachrichten`: bidirektionales APRS-Nachrichten-Gating mit lokaler Erreichbarkeitsprüfung und korrektem `qAR`/`qAO` wurde hinzugefügt.

## 1.8.53.dev - 2026-07-14
- `Nachrichten / Gruppenunterhaltungen`: Threads fuer explizit konfigurierte Zielgruppen mit Absenderkennzeichnung wurden hinzugefuegt; andere Gruppen werden ignoriert, Gruppennachrichten werden einmalig ohne Nachrichtennummer, ACK oder Wiederholung gesendet.
- `Nachrichten / Einstellungen / GUI`: Standardpfad, Empfang fuer jede SSID des eigenen Rufzeichens und eine validierte Gruppenliste (`ALL`, `QST`, `CQ` bei der ersten Verwendung) wurden ergaenzt; der Bereich wurde vereinfacht und die mehrsprachige Hilfe erweitert.

## 1.8.52.dev - 2026-07-08
- `GUI / Layout / Konsistenz`: Margins, Abstaende und Panel-Rahmen zwischen den Ansichten wurden vereinheitlicht; `Map`, `Traffic Monitor`, `Statistics`, `My Station` und die Settings-Formulare folgen jetzt demselben Stil, und die einklappbare Sidebar wurde weiter verfeinert.

## 1.8.50.dev - 2026-07-05
- `Help / GUI / I18N`: vollstaendige lokale Markdown-Hilfedateien in `PL/EN/ES/DE` fuer `iGate settings`, `Notifications`, `Messages`, `WX`, `My Station` und `TNC` wurden hinzugefuegt, an das kontextuelle Hilfe-Icon angebunden und die Icon-Position in Seitenkoepfen vereinheitlicht.

## 1.8.49.dev - 2026-06-29
- `Performance / runtime / SQLite`: Hot Paths fuer schwache Hardware wurden entlastet: Radar prueft `radar_enabled` jetzt vor der teuren Auswertung, das Cleanup von `traffic_frames` wurde aus dem RX-Hot-Path in ein Batch-Maintenance verschoben, kurze Caches fuer Traffic-/Stations-Snapshots und SQLite-Indizes fuer Outbound-/Messages-Hot-Paths wurden hinzugefuegt, der WX-Scheduler lagert blockierendes Refresh in einen Thread aus und die Seite `Messages` pollt `unread-status` nicht mehr doppelt.
- `Map / erster Ladevorgang / Rendering`: der erste Kartenaufruf verwendet jetzt ein leichtes Marker-Payload (`stations-lite`), waehrend Stationsdetails und `mobile_tracks` erst nach dem ersten Render separat geladen werden; das Frontend aktualisiert Marker, PHG-Abdeckung und Tracks nun inkrementell statt per Full-Redraw, wodurch Punkte schneller sichtbar werden und das Overlay-Flackern verschwindet.

## 1.8.48.dev - 2026-06-25
- `Traffic Monitor / Filter`: als Reaktion auf GitHub `issue #53` (`Traffic monitor - filters`) gibt es in der Hauptleiste jetzt frontend-only Schnellfilter fuer `RX`, `TX` und Remote-Client-`TX`-Frames, einen grep-aehnlichen Textfilter sowie `Clear filters`; alle Filter wirken live auch auf nachfolgende SSE-Aktualisierungen, ganz ohne Backend-Aenderungen.

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
