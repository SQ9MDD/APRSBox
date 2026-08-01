# NWS-WARN-Warnungen in APRSBox

`NWS-WARN` ist das spezielle APRSBox-Empfangsprofil für kompakte US-County-Warnungen an die APRS-Gruppe `NWS-WARN`. Es ist eine APRS-Transporthülle, keine direkte Verbindung zum National Weather Service und kein vollständiges NWS-CAP- oder VTEC-Produkt.

APRSBox lädt keine Warnungen von `api.weather.gov`. Es interpretiert ausschließlich APRS-Frames, die über eine konfigurierte RF- oder APRS-IS-Schnittstelle eintreffen.

## Konfiguration

- APRS-Alarme aktivieren und die genaue Gruppe `NWS-WARN` hinzufügen.
- Für die benötigten Ereigniskategorien eine Alarmschwelle setzen. Ohne sie bleibt der Frame im Traffic Monitor, erzeugt aber keinen NWS-WARN-Eintrag.
- Popup-Schwellen nur für Kategorien aktivieren, die den Bediener unterbrechen sollen.
- Prüfen, ob der automatische APRS-IS-Filter `g/NWS-WARN` enthält und die Empfangsschnittstelle aktiv ist.

## Von APRSBox gelesene Paketform

```text
SOURCE>APRS,...::NWS-WARN :DDHHMMz,EVENTLEVEL,SSCnnn[,SSCnnn...]{MSGID
```

```text
NWSWX>APRS,TCPIP*::NWS-WARN :010200z,TORNADO3,TNC037,TNC189{N1001
```

Im neunstelligen APRS-Adressfeld wird `NWS-WARN` mit einem Leerzeichen aufgefüllt. Als Gruppenbulletin wird die Nachricht von APRSBox nie mit ACK bestätigt.

## Interpretierte Felder

- `DDHHMMz` ist Ablauftag, -stunde und -minute in UTC. APRSBox wählt den nächstliegenden gültigen Monat und das Jahr zum Empfang. `z` oder `Z` ist für den automatischen Ablauf erforderlich.
- `EVENTLEVEL` ist die Ereignisbezeichnung. Historische APRS-Unterlagen definieren den Typ als Freitext; APRSBox liest zusätzlich Endziffern als Schweregrad. Für berechenbare Schwellen und Kartenfarben sollte ein normalisierter Code mit `1`, `2` oder `3` enden, etwa `TORNADO3`.
- `SSCnnn` ist ein NWS Universal Geographic Code in County-Form. Mehrere kommagetrennte Countys bilden einen Alarm.
- `MSGID` ist eine alphanumerische APRS-Nachrichtenkennung mit 1–5 Zeichen. Sie dient der Deduplizierung, ist nur Referenzinformation und fordert kein ACK an.

Der historische APRS-Wettertext beschrieb außerdem namensbasierte County-Etiketten und höchstens fünf County-Felder. Das heutige kartierte APRSBox-Profil erwartet stattdessen maschinenstabile UGC-County-Codes für eine zuverlässige Geometriezuordnung.

## UGC-County-Codes

Der auf der Karte akzeptierte Code hat genau sechs Zeichen:

```text
SS C nnn
```

- `SS` ist die zweistellige Kennung eines US-Bundesstaats oder Territoriums.
- `C` bezeichnet County, Parish oder unabhängige Stadt.
- `nnn` ist der dreistellige County-Anteil der FIPS-Kennung.
- `TNC037` bezeichnet in dieser Form Davidson County, Tennessee.

NWS verwendet auch `Z` für öffentliche Vorhersagezonen und Seegebiete. APRSBox kartiert absichtlich nur County-Codes nach `[A-Z]{2}C[0-9]{3}`. `TNZ037` oder `ANZ630` bleibt im gespeicherten Alarm, wird aber nicht gezeichnet. Auch ein syntaktisch gültiger, im mitgelieferten Datensatz fehlender oder veralteter County-Code wird auf der Karte ausgelassen.

Der NWS-County-Grenzdatensatz ändert sich. Wird ein amtlicher Code nicht gezeichnet, sind die installierte APRSBox-Geometrieversion und der aktuelle NWS-GIS-Datensatz zu vergleichen.

## Ereignisstufe und Schwellen

APRSBox verwendet die gemeinsame Skala:

```text
1 = gelb
2 = orange
3 = rot
```

Dieser Zahlensuffix ist eine APRSBox/CAWF-Transportkonvention, nicht das vollständige NWS-CAP-Schweregradmodell und keine Definition der historischen APRS-NWS-Syntax. Der Weiterleitungsbetreiber muss dokumentieren, wie das amtliche NWS-Produkt auf 1–3 abgebildet wird.

Fehlt der Suffix oder liegt er außerhalb 1–3, ist der Schweregrad unbekannt. Bei aktivierter Kategorie bewahrt APRSBox den Alarm; vorhandene Geometrie ist grau. Bekannte Namenspräfixe bestimmen die Kategorie, unbekannte Namen verwenden `Sonstige / unbekannt`.

## Lebenszyklus, Wiederholungen und Aufhebung

- Ein angenommener Frame erstellt einen Alarm mit allen County-Codes und einem Link zum Quellframe im Traffic Monitor.
- Gleicher Absender, gleiche Gruppe und gleiche APRS-Nachrichtenkennung bezeichnen eine Wiederholung. Zähler und letzte Empfangszeit werden aktualisiert, ohne ein Duplikat anzulegen.
- Bei einer neuen Nachrichtenkennung fehlt in dieser Hülle eine gemeinsame logische NWS-Ereignis-ID. APRSBox behandelt sie daher selbst bei gleichem Ereignis und gleichen Countys als eigenen Alarm.
- Ein aufgelöstes `DDHHMMz` deaktiviert den Alarm beim Ablauf; Frames und Verlauf bleiben erhalten.
- Die historische APRS-Familie enthält `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` und `NWS-CANCL`. Nur `NWS-WARN` besitzt in APRSBox eine eigene US-County-Geometrie; `NWS-CANCL` hebt keinen bestehenden Alarm auf.
- Eine fehlende oder ungültige Ablaufzeit kann den Alarm bis zur manuellen Löschung aktiv halten. Bei fehlerhaften Frames ist die Detailansicht zu prüfen.

## Fehlende Inhalte gegenüber amtlichen NWS-Daten

Amtliche NWS-Dienste verteilen Watches, Warnings, Advisories und ähnliche Produkte als CAP v1.2. Diese können Überschrift, Beschreibung, Anweisungen, Dringlichkeit, Schweregrad, Gewissheit, Wirkungszeiten, UGC-Zonen, Polygone und VTEC-Zustände enthalten.

Die kompakte NWS-WARN-Hülle transportiert nur Ablauf, Ereignis-und-Stufe-Token, County-Codes, Absender und APRS-Nachrichtenkennung. Ausgelassene Anweisungen, Polygone, Gewissheit, VTEC-Aktionen, amtliche IDs und Aktualisierungsbeziehungen lassen sich nicht rekonstruieren. Für betriebliche Entscheidungen ist, wenn verfügbar, das zugehörige amtliche NWS-Produkt zu verwenden.

## Vertrauen und sichere Nutzung

Das Ziel `NWS-WARN` beweist nicht, dass der Absender der National Weather Service ist. APRS und APRS-IS authentifizieren diese Hülle nicht kryptografisch; APRSBox besitzt derzeit keine Liste vertrauenswürdiger Absender je Gruppe.

Der Frame ist als zusätzliche Lageinformation zu behandeln. Wirkungsstarke Warnungen müssen über einen amtlichen NWS-Endpunkt geprüft werden, besonders bei unbekanntem Quellrufzeichen, undokumentierter Stufenzuordnung, ungültigem Ablauf oder fehlender County-Geometrie.

## Quellen

- [TAPR APRS Protocol Reference — NWS-Bulletinadressen und kein ACK](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- Mitgelieferte historische APRS-Wetterreferenz `APRS-SPEC/WX.TXT` für `NWS-WARN`, `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` und `NWS-CANCL`.
- [NOAA/NWS-Richtlinie zum Universal Geographic Code](https://www.weather.gov/media/directives/010_pdfs_archived/pd01017002b.pdf).
- [NOAA/NWS-GIS-Datensatz U.S. Counties](https://www.weather.gov/gis/Counties).
- [NWS-CAP-Warndienst-Dokumentation](https://www.weather.gov/documentation/services-web-alerts).
- [NWS-VTEC-Dokumentation](https://www.weather.gov/vtec/).

[Zurück zu den APRS-Alarmeinstellungen](settings_alarms.de.md)
