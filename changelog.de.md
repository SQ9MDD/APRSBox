# Changelog

## 1.12.20.dev - 2026-09-04
- `Karte / Stationsbeschriftungen`: Bei Zoom `10` und kleiner blendet die Karte die Rufzeichen neben Stationsmarkern aus; APRS-Symbole und Hover-Details bleiben sichtbar. Der Schwellenwert ist eine globale Einstellung und kann über ein kompaktes Feld in den globalen Einstellungen geändert werden; der Standardwert ist `10`.
- `Karte / Stationsspuren`: Gleichzeitig sichtbare Spuren erhalten jetzt unterschiedliche, kontrastreiche Farben aus einer Palette, die die vorherrschenden Straßen-, Wasser- und Vegetationsfarben üblicher Kartenkacheln vermeidet. Eine Spur behält ihre Farbe beim Aktualisieren.

## 1.12.19.dev - 2026-09-04
- `Dashboard / Installationszustand`: Die Kachel „APRSBox-Leistung“ bewertet nun die laufende Installation statt nur der letzten DIGI-Übertragungen. Sie funktioniert auch bei inaktiven Funkschnittstellen und verwendet die P95-Reaktionszeit von APRSBox über fünf Minuten, aktuelle Warteschlangenlast sowie aktuelle Überläufe oder verworfene Frames. Die Schwellenwerte sind für kleine Hosts abgestimmt: 46 ms ergeben 4/5, 132–191 ms ergeben 3/5.
- `Installer und Updater`: `uvloop` und `httptools` sind optionale Beschleuniger, die ausschließlich aus fertigen Wheels installiert werden. Fehlt ein kompatibles Wheel, wird die Installation oder Aktualisierung nicht mehr blockiert; Uvicorn nutzt dann Standard-`asyncio` und `h11` ohne Kompilierung aus dem Quellcode. Fehlen grundlegende Systemwerkzeuge, installiert der Updater sie mit `apt-get update` und `apt-get install` oder `apk add`, ohne ein vollständiges System-Upgrade auszuführen.

## 1.12.17.dev - 2026-09-02
- `Packet Routing / RF TX / Leistung`: Der DIGI-RF-Worker verwendet jetzt den vorhandenen Snapshot der Modemkonfiguration, statt SQLite für jeden Frame zu lesen. Nach erfolgreichem Senden wird der Verkehrsverlauf asynchron außerhalb des kritischen TX-Pfads gespeichert; die Speicherung beim kontrollierten Herunterfahren und die Fehlerbehandlung bleiben erhalten. Die DigiFlow-Meldung beim Einreihen eines Frames hat nun die Stufe `DEBUG`, und die Wartung läuft alle 5 statt alle 30 Sekunden, was die SQLite-Konkurrenz auf schwächerer Hardware verringert.

## 1.12.15.dev - 2026-09-01
- `Stabile Version`: Die Leistungsverbesserungen für RX, DigiFlow und Radar aus dem aktuellen Entwicklungszyklus wurden in den stabilen Kanal übernommen.
- `RX / Leistung`: aufwendige Persistenz- und Projektionsarbeiten wurden vom Echtzeitpfad von DigiFlow getrennt und in eine begrenzte, geordnete Side-Effect-Warteschlange mit kontrolliertem Herunterfahren sowie Metriken für Latenz, Überlauf und einzelne Verarbeitungsschritte verschoben.
- `Radar / Leistung`: Das Radar verarbeitet jetzt einen einzelnen, bereits geparsten Positionsrahmen in einem dedizierten Worker, statt die vollständige Stationsliste neu aufzubauen und die TNC2-Historie erneut zu parsen. Exact-/Wildcard-Regeln, Entfernungsprüfung, Wiederholungssperre und Benachrichtigungen bleiben erhalten; ergänzt wurden Metriken für die begrenzte Warteschlange und die einzelnen Zeitphasen.
- `Docker / Multiarch`: `uvloop` und `httptools` bleiben für Linux-Images auf `amd64` und `arm64` aktiviert, sind auf dem älteren `arm/v7` jedoch optional; Uvicorn verwendet dort das Standard-`asyncio` und `h11`, ohne diese Pakete aus dem Quellcode zu bauen. Die Aktionen für QEMU sowie Docker Build & Push wurden ebenfalls aktualisiert.

## 1.12.13.dev - 2026-09-01
- `Packet Routing / Diagnose`: DigiFlow-Metriken sind nach Quelle und Schnittstelle getrennt, erfassen Worker-Phasen sowie Event-Loop-Lag und verwenden gecachte Konfiguration, Pfade und Identitäten statt SQLite-Lesezugriffen pro Frame.
- `APRS-IS / uvloop`: Verbleibende Transportbytes nach erfolgreichem `drain()` gelten nicht mehr als TX-Fehler; geschlossene Transporte und echte Schreib-/Drain-Fehler bleiben behandelt. Danke an SQ5BUJ für die Hinweise.
- `Installer und Updater`: `/opt/aprsbox/venv` installiert `uvloop` und `httptools` aus `requirements.txt` und prüft ihre Imports; nach erfolgreichem Backup behält der Updater standardmäßig die vier neuesten Datenbanksicherungen.
- `Packet Routing / Latenz`: leichte Zeit- und Queue-Tiefen-Aggregate im RAM wurden ergänzt. Reguläres RF-DIGI umgeht nun persistente `outbound_jobs` und nutzt flüchtige Queues sowie eigene Worker pro Schnittstelle, sodass TX-Gap oder ein langsames TNC andere TNCs nicht blockieren.
- `APRS-IS / TX`: Das Routing übergibt Frames blockierungsfrei an eine begrenzte RAM-Queue; ein eigener Worker behält die bestehende Socket-, `drain()`- und Reconnect-Logik bei. Bei Überlauf wird der Frame sofort mit Warnung und Zähler verworfen.
- `DigiFlow / Trace`: Die Diagnose der einzelnen Schritte wird außerhalb des Echtzeitpfads in Batches mit bis zu 50 Ereignissen oder alle 75 ms in einer Transaktion gespeichert. Auch das Bereinigen der Historie wurde aus der Frame-Verarbeitung entfernt.

## 1.12.11 - 2026-08-31
- `Stabile Version`: Leistung und Regelverarbeitung von Packet Routing wurden verbessert, die Einstellungen und Farbpaletten wurden verfeinert, und abgelaufene DIGI- sowie APRS-IS-Frames werden jetzt verworfen, statt nach einer Verzögerung gesendet zu werden. Das Protokoll enthält Alter und Limit eines verworfenen Frames und erleichtert damit die Diagnose einer Überlastung von Backend oder TNC.

## 1.12.10.dev - 2026-08-31
- `Packet Routing / Schutz vor alten Frames`: Die DIGI-Weiterleitungswarteschlange bewahrt den ursprünglichen Empfangszeitpunkt und verwirft Frames, die älter als 5 Sekunden sind, automatisch vor dem RF-TX; nur die konfigurierte Viscous-Delay verlängert dieses Limit. Dasselbe Limit `5 s + Viscous Delay` gilt für den APRS-IS-Uplink einschließlich der abschließenden Prüfung direkt vor dem TCP-Schreibvorgang. Ein verworfenes Job protokolliert ein `WARNING` sowie einen Warteschlangengrund mit Frame-Alter, Limit und Empfangszeit, wodurch Verzögerungen durch überlastetes Backend oder TNC nachvollziehbar werden.

## 1.12.9.dev - 2026-08-30
- `Packet Routing / Leistung`: Regeleditor und Verlaufs-APIs verwenden jetzt gemeinsam eine SQLite-Verbindung, führen bei Lesezugriffen keine Alert-Wartungsschreibvorgänge aus und laden Kartenkonfiguration sowie initialen Verlauf beim Öffnen nicht mehr doppelt.

## 1.12.8.dev - 2026-08-28
- `GUI / Farbpaletten`: 29 abwechslungsreiche Paletten mit hellen und dunklen Varianten wurden ergänzt, darunter Pastell-, Gelände-, Retro- und Technik-Sets. Die Auswahl erfolgt jetzt über ein kompaktes, scrollbar angeordnetes Farbmuster-Raster, ohne die Speicherung der Einstellung zu ändern.
- `Einstellungen / Layout`: Rechts neben den globalen Einstellungen fasst eine kompakte Spalte jetzt Anwendungsaktualisierung, APRS-Geräteerkennung und Konfigurationssicherung zusammen. Wiederholte Angaben zur Verfügbarkeit und zum Aktualisierungszeitpunkt des lokalen Caches wurden aus dem Erkennungspanel entfernt; der verkürzte Hinweis auf einen instabilen Kanal steht jetzt neben der Auswahlliste.

## 1.12.7.dev - 2026-08-28
- `Objekte und Items / Liste`: Punktartefakte neben Symbolen und Statussymbolen wurden entfernt. Schmale Symbolzellen verwenden jetzt einen passenden Innenabstand und nicht mehr die für gekürzten Text vorgesehene Auslassungsmarkierung; die Kürzung von Überschriften und anderen langen Werten bleibt unverändert.

## 1.12.6.dev - 2026-08-28
- `Bandbedingungen / Bewertungsstabilität`: die stundenspezifische Referenzbasis wird jetzt erst nach 7–14 passenden Stichproben schrittweise einbezogen, statt die gesamte Historie bereits nach drei Stunden zu ersetzen. Die Voraussetzungen für W4 wurden verschärft; bei geringer Modellzuverlässigkeit wird der höchste ausgegebene Pegel auf W2, W3 oder W4 begrenzt, sodass eine unreife Basis kein falsches starkes Bandopening mehr meldet.

## 1.12.4 - 2026-08-28
- `Stabile Version`: diese Version konzentriert sich auf einen strikten, Burst-resistenten APRS-IS-Uplink und eine zuverlässigere Wiederherstellung nativer KISS-TCP-Verbindungen nach RX-Stille. Bei schlechter Verbindung verwirft APRSBox veraltete Frames bewusst, statt sie später gesammelt auszugeben.
- `APRS-IS / strikte Aktualität`: APRS-IS TX arbeitet bei Überlastung oder schlechter Verbindung jetzt fail-closed. Frames, die älter als 5 Sekunden sind, werden direkt vor dem Transport-Schreibvorgang verworfen; die gemeinsame Routing-Warteschlange ist auf 256 Frames begrenzt.
- `APRS-IS / TCP Anti-Burst`: Linux-TCP-Verbindungen verwenden einen 3-sekündigen `TCP_USER_TIMEOUT` und aggressives Keepalive. Ein belegter Transportpuffer führt zum sofortigen Abbruch der Verbindung, statt alte Frames später gesammelt zu übertragen.
- `Schnittstellen / RX-Stille`: der vorhandene `RX Silence Reconnect Timeout (s)` gilt jetzt auch für native KISS-TCP-Verbindungen. Der Timeout wird ab beliebigen empfangenen Bytes gemessen; nach Ablauf wird der Socket geschlossen und durch die vorhandene Schleife neu verbunden. `0` deaktiviert den Watchdog weiterhin. Die lokale TCP-Verbindung des seriellen Brokers startet keinen zweiten Watchdog, sodass Serial nur einen gemeinsamen Mechanismus am physischen Port verwendet.
- `Schnittstellen / GUI`: dasselbe RX-Timeout-Feld steht für SERIALL und TCP ohne Änderungen an Konfiguration oder Datenbank zur Verfügung.
- `Tests`: Regressionstests für veraltete APRS-IS-Frames, die begrenzte Warteschlange, den Transportabbruch und den durch beliebige Bytes zurückgesetzten KISS-TCP-Stille-Timeout wurden ergänzt.

## 1.12 - 2026-08-27
- `Stabile Version`: Karte und Stationstracks wurden durch das Auffächern überlappender Marker und die sofortige Aktualisierung des neuesten Frames verbessert. Die Bewertung und Diagnose der Bandbedingungen wurde überarbeitet, RF- und APRS-IS-Gruppen wurden getrennt, die Verwaltung von Schnittstellen und Hilfe vereinfacht und die APRS-IS-Best-Effort-Übertragung ohne Frame-Pufferung oder Wiederholungsversuche präzisiert.
- `Backend / Leistung`: N+1-Abfragen und I/O pro Datensatz wurden entfernt, Einstellungs- und Listendaten gebündelt geladen, SQLite-Verbindungswechsel reduziert und anhand von Abfrageplänen geprüfte Indizes ergänzt.

## 1.11.10.dev - 2026-08-26
- `Bandbedingungen / Servicedaten`: Unter den Modelldaten wurde ein Diagnosepanel ergänzt, das die gelernte Referenzbasis, Median und P90-Reichweite ortsfester Stationen, automatische Entfernungsschwellen sowie Zähler für Stationen, bestätigte Fernempfänge, geografische Gebiete und RF-Frames aus der für die sichtbare Bewertung verwendeten Stichprobe anzeigt.

## 1.11.8.dev - 2026-08-26
- `APRS-IS / Übertragung`: Der Uplink arbeitet jetzt nach einem eindeutigen Best-Effort-Vertrag ohne Pufferung oder Wiederholungsversuche für Frames. Ein Paket wird nur über den aktuell aktiven Transport geschrieben; eine fehlende Verbindung, ein sich schließender Transport, ein Schreibfehler oder Timeout führt zum sofortigen Verwerfen, während ein Reconnect ausschließlich neue Frames verarbeitet und frühere niemals erneut abspielt. Das Routing-Protokoll unterscheidet nun `sent` und `drop`, statt einen direkten Schreibvorgang als eingereiht zu bezeichnen.

## 1.11.7.dev - 2026-08-26
- `GUI / Hilfe`: Hilfefenster sind nicht modal, bleiben beim Ausfüllen von Formularen geöffnet und lassen sich über den Bildschirm ziehen.

## 1.11.6.dev - 2026-08-25
- `Bandbedingungen / Reichweitenmodell`: Die Bewertung W0–W5 wurde so überarbeitet, dass jeder Empfänger seine normale Reichweite aus genau einer repräsentativen Entfernung je ortsfester Station lernt. Außergewöhnliche Fernempfänge werden robust mit Median und MAD herausgefiltert; die Schwellen für entfernte und sehr entfernte Stationen werden automatisch aus dem lokalen RF-Footprint statt aus Einzelbeobachtungen abgeleitet.
- `Bandbedingungen / Zuverlässigkeit`: Third-Party-Frames gelten nicht mehr als physische RF-Beobachtungen, die Bestätigung einer entfernten Station erfordert nun Empfang in mindestens drei Zeitsegmenten und W3–W5 setzen klarere, wiederholbare Hinweise voraus. Außerdem wurden Referenzbasis, Reifung der Bewertungssicherheit und Modellparameter vereinheitlicht.

## 1.11.5.dev - 2026-08-24
- `Nachrichten / Gruppen`: Die bisherigen Zielgruppen wurden in `RF-Gruppen` und `APRS-IS-Gruppen` aufgeteilt; bei der ersten Verwendung übernimmt die APRS-IS-Liste die RF-Gruppen und kann anschließend unabhängig konfiguriert werden. APRS-IS-Gruppen werden im `g/...`-Filter der APRS-IS-Verbindung automatisch mit aktivierten Alarmgruppen zusammengeführt.
- `Karte / Quellen und Tracks`: Stationssymbole verwenden jetzt den chronologisch neuesten Positionsframe aus den aktuell sichtbaren Quellen, sodass der Marker sowohl bei aktivierten Quellen als auch nach Auswahl einer einzelnen Schnittstelle am Ende des zugehörigen Tracks bleibt. Ein einzelner sichtbarer Punkt positioniert das Symbol weiterhin, ohne eine künstliche Polylinie zu zeichnen; wiederholte Beobachtungen an derselben Position behalten die neueste Quelle und den neuesten Zeitstempel.

## 1.11.3.dev - 2026-08-21
- `Schnittstellen / Schnellaktionen`: In der Schnittstellenliste wurde eine kontextabhängige Schaltfläche zum Aktivieren oder Deaktivieren ergänzt, entsprechend der Aktion bei Routing-Regeln; die Statusänderung erfordert kein Öffnen des Editors, aktualisiert ausschließlich den Aktivitätszustand der Schnittstelle und verwendet das gemeinsame Fortschrittsmodal mit lokalisierter Ergebnismeldung und Fehlerbehandlung.

## 1.11.2.dev - 2026-08-20
- `Karte / Marker auffächern`: `OverlappingMarkerSpiderfier` wurde lokal eingebunden und das optionale Auffächern überlappender Einzelmarker bei hohem Zoom ergänzt; APRS-Symbole und Tooltips bleiben erhalten. Am Desktop fächert Hover die Gruppe auf, ein Klick öffnet immer die Details der gewählten Station, und das Verlassen des erweiterten Gruppenbereichs klappt sie verzögert wieder zusammen; auf Touch-Geräten gilt weiterhin erster Tap zum Auffächern, zweiter Tap für Details. Der Schwellenwert wird relativ zu `map.getMaxZoom()` berechnet, `Leaflet.markercluster` übergibt Marker ab derselben Zoomstufe und die Geometrie berücksichtigt die Größe des Symbolsatzes.
- `Einstellungen / Karte`: Die globalen Einstellungen enthalten jetzt einen Schalter zum Auffächern von Markern, die Anzahl der Stufen vor dem maximalen Zoom (Standard `2`) und den Überlappungsabstand in Pixeln (Standard `20`); die Werte werden validiert, in den Anwendungseinstellungen gespeichert und in Konfigurationssicherungen v2 aufgenommen.

## 1.11 - 2026-08-20
- `Stabile Version`: Die Änderungen aus `1.10.7.dev–1.10.16.dev` wurden zusammengeführt, darunter eine deutlich schnellere Karte und Stationsliste auf Basis einer persistenten Stationszustandsprojektion, ein neu gestaltetes Dashboard mit klarerer Bewertung der Stationsbereitschaft, vollständige HTTPS-Unterstützung für systemd und OpenRC, sicherere Aktualisierungen sowie einheitliche Dialoge, Hilfe und GUI-Symbole. Die Kompatibilität von APRS-Nachrichten wurde erweitert, Konversationen wurden als kompakte Liste mit Auswahl und Sammellöschung neu organisiert und die optionale Gruppierung überlappender Kartenstationen bleibt standardmäßig deaktiviert.

## 1.10.16.dev - 2026-08-20
- `APRS-Nachrichten / Konversationsliste`: Die Liste wurde als kompakte, einzeilige Datensätze mit festen Spalten für Auswahl, Rufzeichen, Hörstatus, Lesestatus und Löschen neu aufgebaut; die Zeit seit dem letzten Frame steht jetzt im Tooltip der Zeile, und die Statusanzeigen verwenden einheitliche Material-Design-Symbole.
- `APRS-Nachrichten / Mehrfachlöschen`: Checkboxen pro Konversation sowie eine gemeinsame Checkbox mit Zwischenzustand wurden im Listenkopf ergänzt und über der Auswahlspalte ausgerichtet; die Aktion zum Löschen der Auswahl steht über der Papierkorbspalte und entfernt die gewählten Konversationen samt Nachrichten nach einer einzigen Bestätigung.
- `Karte / Stationsgruppierung`: Das Zusammenfassen überlappender Symbole zu blauen Zählsymbolen ist jetzt optional; ein neuer globaler Schalter in den Einstellungen ist standardmäßig deaktiviert, sodass die Karte normalerweise einzelne APRS-Symbole darstellt.

## 1.10.15.dev - 2026-08-16
- `Einstellungen / HTTPS`: Ein Panel zur Verwaltung von `aprsbox.crt`, `aprsbox.key` und der optionalen CA-Kette in `/opt/aprsbox/data/ssl` wurde ergänzt; die Oberfläche prüft das Zertifikat-Schlüssel-Paar, zeigt den Dateistatus, unterstützt Upload und sicheres Löschen und ermöglicht den Download der CA-Kette. Lokale PKI-Erzeugung und Root-CA-Download bleiben vorerst deaktiviert.
- `HTTPS / Laufzeit`: Der Schalter speichert den HTTPS-Zustand und startet die Dienste neu; der HTTP-Modus lauscht auf Port `8000`, während der HTTPS-Modus diesen Listener deaktiviert, Uvicorn mit TLS auf `443` startet und einen separaten Dienst für die Weiterleitung von Port `80` zu HTTPS mit Status `308` verwendet.
- `Installer / Aktualisierung`: Redirect-Dienst und Uvicorn-Units wurden für systemd und OpenRC ergänzt und ersetzen Gunicorn als Starter für Web und Core; außerdem wurden Unit-Migration, explizite Übergabe des HTTPS-Zustands, `CAP_NET_BIND_SERVICE` und nachfolgende Aktualisierungen aus der GUI korrigiert.
- `HTTPS / Zuverlässigkeit und Hilfe`: Der abschließende Neustart läuft außerhalb der cgroup des Webdienstes und meldet seinen Abschluss, HTTP/HTTPS-Wechsel warten auf die Dienste und entfernen veraltete Jobzustände, und das SSL-Verzeichnis wird auf `aprsbox:aprsbox` mit Modus `0750` korrigiert; die lokalisierte Hilfe beschreibt mDNS, DNS-SAN-Einträge und Zertifikate für IP-Adressen.

## 1.10.14.dev - 2026-08-16
- `GUI / Alarme`: Der Eintrag `Alarme` in der Seitenleiste wird ausgeblendet, wenn `APRS-Alarme aktivieren` deaktiviert ist.

## 1.10.12.dev - 2026-08-15
- `Einstellungen / Dialoge`: Die nativen Browserdialoge `confirm` und `prompt` wurden für Anwendungsaktualisierung, Konfigurationsimport, Datenbankwartung, Dienstneustart und Host-Aktionen durch das gemeinsame APRSBox-Modal ersetzt; Bestätigungen für `REBOOT` und `POWER OFF` erfordern die exakte Eingabe, während die Schließen-Aktion des Fortschrittsmodals erst nach Abschluss des Vorgangs erscheint.
- `Einstellungen / Kartenquellen`: Speichern und Bearbeiten, Umsortieren, Festlegen der Standardquelle, Löschen und Leeren des Caches verwenden jetzt denselben asynchronen Modalablauf mit Spinner, lokalisierter Ergebnismeldung und Fehlerbehandlung wie die übrigen Systemaktionen; die Formularvalidierung erfolgt weiterhin vor dem Absenden.

## 1.10.11.dev - 2026-08-15
- `GUI / Hilfe`: Das gemeinsame Modal für alle Hilfedokumente besitzt jetzt eine sichtbare, schmale und an das aktive Theme angepasste Bildlaufleiste; das Scrollen bleibt im Dialog und wird nicht an die dahinterliegende Seite weitergegeben.
- `APRS / Symbolauswahl`: Die Symbollisten in `Meine Station`, `Objekte / Elemente` und im Symbolfilter von `Packet Flow` zeigen jetzt neben Symbol und Code die offizielle Beschreibung aus dem aprs.fi-Symbolindex; Beschreibung und Vorschau folgen der ausgewählten primären `/` beziehungsweise alternativen `\` Tabelle.
- `APRS / Modern-Symbole`: Die fehlerhaften Symbole `/!` (Polizeistation), `\!` (Notfall) sowie `/q` und `\q` (Gitternetzvarianten) wurden korrigiert; falsche Dateien, darunter Dateien mit einem vollständigen Symbolblatt, wurden durch die richtigen Kacheln aus den Quell-Symbolblättern ersetzt.

## 1.10.10.dev - 2026-08-14
- `Packet Routing / Speichern`: Das Aktivieren und Deaktivieren von Regeln sowie das Speichern im Editor verwenden jetzt den APRSBox-Standarddialog mit Spinner, Ergebnismeldung und Fehlerbehandlung ohne Neuladen der Seite; nach erfolgreichem Speichern kehrt der Benutzer zur passenden Liste oder zur bearbeiteten Regel zurück.
- `GUI / Hilfe`: Alle Hilfeschaltflächen verwenden jetzt ein um 50 % vergrößertes Symbol mit einem einheitlichen blauen Akzent für Symbol, Rahmen und Hintergrund, sodass Hilfeelemente in allen Ansichten und Farbpaletten sofort erkennbar sind.
- `Karte / QTH-Gitter`: Die Beschriftungen vierstelliger Locator-Felder wurden bei Zoomstufe `6` verkleinert, damit sie in der dichten Gitteransicht nicht dominieren oder sich überlagern.

## 1.10.9.dev - 2026-08-14
- `APRS-Nachrichten / Kompatibilität`: Eingehende Nachrichten sowie `ack`-Bestätigungen und `rej`-Ablehnungen akzeptieren jetzt alphanumerische Kennungen mit 1 bis 5 Zeichen; eine erneut übertragene nummerierte Nachricht desselben Absenders wird auch bei geänderter Konversationszuordnung nicht dupliziert, aber weiterhin erneut bestätigt.

## 1.10.8.dev - 2026-08-14
- `Dashboard / Stationsbereitschaft`: Die Bewertung basiert jetzt auf der APRS-IS-Verbindung, dem Flow `Local TX → APRS-IS`, einer definierten Bake sowie vollständigen Richtungen `RF → APRS-IS`, `APRS-IS → RF` und `RF → RF` für aktive Schnittstellen; Zustände werden mit Symbolen dargestellt, während aktive Schnittstellen bei Vollständigkeit grün, bei teilweiser Aktivität dunkelgelb und bei null rot markiert sind.
- `Dashboard / Layout`: Die Stationsbereitschaft wurde in den hervorgehobenen Bereich neben dem Diagramm verschoben; die Karte der letzten wichtigen Ereignisse sowie die doppelte Zusammenfassung von Schnittstellen und RF-Aktivität wurden entfernt und der verbleibende Inhalt an das aktuelle Fenster angepasst. Der irreführende Gesamtzähler, der deaktivierte Schnittstellen ausließ, wurde ebenfalls entfernt.
- `Dashboard / Konfigurationshilfe`: Der Konfigurationslink der Bereitschaftskarte wurde durch das in die Karte eingebettete Standardsymbol für Hilfe ersetzt. Eine verständliche Anleitung in vier Sprachen führt durch `Schnittstellen → Meine Station → Packet Routing` und erklärt den Unterschied zwischen dem eigenen Flow `Local TX → APRS-IS` und dem Uplink von über RF empfangenen Frames. Die automatische Aktualisierung pausiert bei geöffneter Hilfe und startet nach dem Schließen wieder mit vollen 30 Sekunden.
- `Einstellungen / Versionsprüfung`: `Version prüfen` lädt die GitHub-Datei `VERSION` jetzt direkt über HTTPS. Dadurch funktioniert die Prüfung auch im Docker-Image, in dem das Programm `git` nicht installiert ist; für andere Quellen bleibt der bisherige Git-Mechanismus als Fallback erhalten. Der Vergleich bietet eine neuere Entwicklungsversion nicht mehr als „Update“ auf eine ältere stabile Version an.

## 1.10.7.dev - 2026-08-14
- `Karte / Stations-Backend`: Die dauerhafte Projektion `map_station_state` wurde ergänzt; sie wird beim Empfang und Senden von APRS-Frames aktualisiert und kann aus dem Verlauf neu aufgebaut werden. Kartenendpunkte rekonstruieren den Zustand nicht mehr durch erneutes Parsen von `traffic_frames` (die gemessene TTFB von `stations-lite` sank von etwa `3,4 s` auf etwa `63 ms`).
- `Stationen / Aktualisierung`: Karte und Stationsliste lesen die vorbereitete Projektion; revisionsbasiertes Polling lädt nur geänderte Datensätze und Löschungen. Auch die RF-Zusammenfassung durchsucht den Verlauf nicht mehr.
- `Dashboard / Leistung`: Zuletzt gehörte Stationen und das anfängliche Diagramm verwenden vorhandene Projektionen; Verkehrs-KPIs werden mit einer Abfrage berechnet und Stationsschlüssel bei verfügbarem Stundenpuffer nicht erneut aus `traffic_frames` geparst.

## 1.10.6 - 2026-08-13
- `Stabile Version`: Die Änderungen aus `1.10.2.dev–1.10.5.dev` wurden zusammengeführt, darunter die sicherere Konfigurationssicherung v2, vereinheitlichte GUI-Aktionen und Dialoge, Verbesserungen bei Scrollen und Bedienbarkeit, die automatische Aktualisierung von APRS Device Identification, das themeabhängige Maidenhead/QTH-Gitter mit adaptiver Genauigkeit, die korrigierte Weltwiederholung der Karte und der Standarddialog zur Bestätigung einer Anwendungsaktualisierung.

## 1.10.5.dev - 2026-08-13
- `Einstellungen / Anwendungsaktualisierung`: Die browsernative Bestätigungsabfrage vor einer Aktualisierung wurde durch den Standarddialog von APRSBox ersetzt, der auch bei anderen Aktionen und in beiden Farbthemen verwendet wird; Abbrechen, Escape, Klick auf den Hintergrund und die korrekte Fokuswiederherstellung werden unterstützt.

## 1.10.4.dev - 2026-08-13
- `Karte / Maidenhead-QTH-Locator`: Eine optionale Locator-Gitterebene mit gespeichertem Sichtbarkeitsschalter wurde ergänzt; die Detailstufe wechselt mit dem Zoom von 2-stelligen Feldern über 4- und 6-stellige Locator bis zu 8-stelligen erweiterten Quadraten.
- `Karte / QTH-Gitter / Lesbarkeit`: Beschriftungen werden innerhalb der tatsächlichen Web-Mercator-Zellgrenzen zentriert, dynamisch an die Zellgröße angepasst und verwenden eigene kontrastreiche Farben, Konturen und Gitterlinien für helle und dunkle Themes.
- `Karte / Weltumbruch`: Gespeicherte Ansichten und Zentrierbefehle normalisieren den Längengrad auf `-180…180°`; `worldCopyJump` verhindert, dass die Karte auf einer benachbarten Weltkopie ohne Stationsmarker, Tracks und Abdeckungskreise verbleibt.

## 1.10.3.dev - 2026-08-09
- `GUI / Aktionen und Dialoge`: Speichern, Senden und Löschen wurden in Schnittstellen, Meine Station, WX, Benachrichtigungen, Objekten und Bulletins mit gemeinsamen Bestätigungen, Spinner-Dialogen und Ergebnismeldungen vereinheitlicht.
- `Benachrichtigungen / Packet Routing`: Formulare behalten die Position des bearbeiteten Blocks bei; im Flow-Editor liegen die Aktionen in der Spalte der aktuellen Schritte, der Arbeitsbereich passt sich deren Inhalt an und der Filter- und Regelkatalog scrollt unabhängig.
- `GUI / Scrollen und Karte`: Dezente, themeabhängige Scrollbars wurden im Routing-Katalog, in Konversationen, im Traffic Monitor und im Karten-Scroller ergänzt; ein Klick auf eine Station im Scroller zentriert sie auf der Karte.
- `APRS Device Identification`: Beim Öffnen der Einstellungen wird die Datenbank im Hintergrund aktualisiert, wenn sie noch nie oder seit mehr als 30 Tagen nicht erfolgreich aktualisiert wurde; nach Fehlern gilt ein Wiederholungsabstand von 24 Stunden.
- `Einstellungen / Ergonomie`: Aktionen, die Bearbeitung von Kartenquellen und Neuladevorgänge nach dem Speichern behalten das aktive Panel und die Scrollposition bei, statt zum Seitenanfang zurückzukehren.

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
