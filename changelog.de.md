# Changelog

## 1.10.2.dev - 2026-08-08
- `Konfigurationssicherung v2`: Der Exportumfang wurde erweitert und ein sicherer Import ohne Verlust von Runtime-Verknüpfungen eingeführt; v1-Dateien werden nicht unterstützt.

## 1.10 - 2026-08-06
- `Stabile Version`: Die Änderungen aus `1.9.1.dev–1.9.8.dev` wurden zusammengeführt, darunter APRS- und Wetteralarme, ein neues Dashboard, erweiterte Bandbedingungen, eine übersichtlichere APRS-IS- und GUI-Konfiguration, ausgebaute Hilfe, Stationsfilter sowie sicherere Anwendungsaktualisierungen und Systemaufträge.

## 1.9.8.dev - 2026-08-05
- `Einstellungen / Systemaufträge`: Anwendungsaktualisierung, Dienstneustart, Host-Neustart und Host-Abschaltung übergeben die Auftrags-ID und den Datenbankpfad nun explizit über die Berechtigungsgrenze an ihre Skripte, sodass Status und Fortschritt auch bei Verwendung von `sudo` im selben Datensatz bleiben.
- `Einstellungen / Auftragswiederherstellung`: Die Statusüberwachung erkennt verwaiste Aktualisierungs- oder Neustartaufträge, die nach dem Ende ihres Prozesses beim Start hängen bleiben; sie markiert diese als fehlgeschlagen und empfiehlt, vor einem erneuten Versuch die installierte Version zu prüfen.

## 1.9.7.dev - 2026-08-04
- `Stationen / Filter`: Eine kompakte einzeilige Kartenleiste mit Symbolen und Tooltips wurde ergänzt, einschließlich des Filters `Direkt gehört` für über RF ohne verbrauchten Digipeater-Hop empfangene Stationen.
- `Einstellungen / Anwendungsaktualisierung`: Das Modal zeigt nun die tatsächliche Phase und den Fortschritt in Prozent, behält die Überwachung während des Webdienst-Neustarts bei und endet erst bei einem terminalen Prozessstatus statt bereits bei erneut erreichbarem Health-Endpunkt.

## 1.9.6.dev - 2026-08-01
- `Einstellungen / Hilfe`: Eigene Markdown-Hilfe für 8 Panels in EN/DE/PL/ES/TLH hinzugefügt und die Oberfläche durch Entfernen wiederholter Beschreibungen vereinfacht.
- `Hilfe / Renderer`: Externe Links aus Hilfedokumenten werden nun sicher geöffnet.
- `Alarme / Hilfe`: Verlinkte und quellenbasierte CAWF- und NWS-WARN-Anleitungen in EN/DE/PL/ES/TLH ergänzt; sie erklären Frameformat, Fragmentierung, UGC, Karte, Lebenszyklus, Schwellen und Vertrauensgrenzen.

## 1.9.5.dev - 2026-07-31
- `Bandbedingungen / GUI und Runtime`: Die Registerkarte wird ausgeblendet und die Datenerfassung und -verarbeitung deaktiviert, wenn keine aktive RF-Schnittstelle die Bandbewertung aktiviert hat; alle anderen Funkstatistiken funktionieren unverändert weiter.
- `Alarme / Formate`: Empfang und Verarbeitung von Wetteralarmen in den Formaten `CAWF` und `NWS-WARN` wurden hinzugefügt.
- `Alarme / Polen / Verwaltungsgebiete`: Polnische Landkreisgrenzen (`Powiat`) und die Zuordnung von Warngebietskennungen wurden ergänzt, damit Alarme die zugehörigen Gebiete auf der Karte anzeigen können.
- `Karte / Leistung / Erstladen`: Alarmgebiete werden getrennt nach den primären Kartendaten geladen, während Stationssymbole und Rufzeichen schrittweise in priorisierten Paketen erscheinen; dadurch bleiben die Kartenkacheln nicht lange ohne Marker und die Karte bleibt reaktionsfähig.

## 1.9.4.dev - 2026-07-29
- `GUI / Texte`: Alle Hauptansichten wurden geprüft und überflüssige Abschnittsbeschreibungen, wiederholte Anweisungen und offensichtliche Hinweise entfernt; Statusangaben, Formatvorgaben, Validierung sowie RF- und administrative Sicherheitswarnungen bleiben erhalten.
- `Dashboard / Station`: Die Empfangsbeschreibung und der Zeitstempel der letzten RF-Aktivität wurden aus der Hauptkarte der Station entfernt; außerdem wurden Höhe und Abstände reduziert.

## 1.9.3.dev - 2026-07-29
- `Schnittstellen / APRS-IS`: Der separate Navigationseintrag `iGATE-Einstellungen` wurde entfernt; Server, Port, Login, Passcode, Filter und Verbindungsdiagnose befinden sich jetzt direkt im Formular der Schnittstelle `APRS-IS (RX/TX)`, während die alte URL dorthin weiterleitet.
- `Schnittstellen / Formular`: Der Editor verwendet nun einen stabilen gemeinsamen Bereich und eigene Panels für SERIALL, TCP, OpenWebRX MQTT und APRS-IS, sodass Felder beim Wechsel des Verbindungstyps nicht unerwartet Spalte oder Reihenfolge ändern.
- `Schnittstellen / APRS-IS / GUI`: die APRS-IS-Verbindung wird jetzt korrekt als RX/TX beschrieben; der Schalter `APRS-IS-Verbindung aktivieren` steuert den gesamten gemeinsamen Transport, während die TX-Spalte den aktiven Flow `TX APRS-IS` statt einer irreführenden TNC-Sperre anzeigt.
- `Schnittstellen / APRS-IS / Runtime`: das Deaktivieren der Verbindung stoppt jetzt sowohl APRS-IS-Empfang als auch -Senden; außerdem werden nur für physische TNCs relevante Felder korrekt ausgeblendet.
- `Packet Routing / APRS-IS`: Quelle und Ziel APRS-IS sind erst nach Definition einer APRSIS-Schnittstelle verfügbar; die Backend-Validierung blockiert das Speichern oder erneute Aktivieren solcher Flows nach dem Entfernen der Schnittstelle.
- `Packet Routing / Schnittstellen / GUI`: die Formulare wurden durch Entfernen von Beschreibungen und wiederholten Bezeichnungen vereinfacht, die bereits in der ausführlichen Hilfe stehen; Sicherheitsmeldungen, Validierung und dynamische Konfigurationswerte bleiben sichtbar.
- `Hilfe / I18N`: die TNC-Hilfe und die Übersetzungen PL/EN/ES/DE dokumentieren jetzt das Senden über `Receiver RF → TX APRS-IS` und `Local TX → TX APRS-IS` durch dieselbe Verbindung.

## 1.9.2.dev - 2026-07-29
- `GUI / Menü`: Reihenfolge und Bereiche der Seitenleiste wurden neu geordnet und die Benutzerleiste auf kompakte, ausgerichtete Symbole reduziert.
- `GUI / Beacon`: eine Schnellaktion zum Senden eines Beacons mit zentrierter Bestätigung und einer durch ein abgeblendetes Symbol dargestellten 10-sekündigen Sendesperre wurde hinzugefügt.

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
