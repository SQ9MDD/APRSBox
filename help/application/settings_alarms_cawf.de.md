# CAWF-Warnungen in APRSBox

CAWF, das Common APRS Warning Format, ist eine kompakte, länderneutrale Hülle zur Verteilung räumlich begrenzter öffentlicher Warnungen als APRS-Gruppennachrichten. Diese Hilfe beschreibt CAWF v1 nach dem bereitgestellten Entwurf und benennt anschließend das Verhalten und die Grenzen des APRSBox-Empfängers.

CAWF ist ein Transportformat. Es ersetzt weder die amtliche nationale Warnquelle noch CAP oder das NWS-WARN-Profil.

## Modell von der Quelle bis zum Empfänger

- Ein territorialer CAWF HUB liest eine autoritative Quelle und bildet Ereignis, Schweregrad und Gebiete nach einem veröffentlichten Länderprofil ab.
- Er sendet eine oder mehrere APRS-Nachrichten an eine Warngruppe. Das empfohlene Muster ist `CC-WARN`, zum Beispiel `PL-WARN`.
- APRSBox empfängt die Gruppe über RF oder den automatisch erweiterten APRS-IS-Filter, setzt Fragmente zusammen, wendet Schwellen an, speichert den Alarm und verbindet Gebietscodes mit lokaler GeoJSON-Geometrie.
- Warngruppen sind Rundrufziele. APRSBox sendet kein ACK.

## CAWF-v1-Nutzlast

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]{MESSAGE_ID
```

Beispiel:

```text
012300z,TSTORM2,@3569,1/2,0609,1206,1409{A6474
```

Eine konforme Nutzlast hat eine feste Feldreihenfolge, Protokolltoken in ASCII-Großbuchstaben mit Ausnahme des wörtlichen kleinen `z`, keine internen Leerzeichen und einschließlich APRS-Nachrichtenkennung höchstens 67 Zeichen.

## Felder

- `EXPIRY` hat das Format `DDHHMMz`: Tag, Stunde und Minute in UTC. APRSBox bestimmt Monat und Jahr als nächstes gültiges Vorkommen zum Empfangszeitpunkt. Ein unmöglicher oder fehlerhafter Wert kann den Alarm nicht automatisch ablaufen lassen.
- `EVENT_LEVEL` verbindet Ereigniscode und abschließende einstellige Stufe, zum Beispiel `TSTORM2`.
- `ALERT_ID` besteht aus `@` und vier hexadezimalen Großzeichen. Alle Fragmente eines logischen Alarms verwenden dieselbe Kennung. Ihr Gültigkeitsbereich ist Quellrufzeichen plus Warngruppe plus Alarm-ID; sie ist nicht global eindeutig.
- `PART/TOTAL` beginnt bei `1/1`. Teilenummern sind eindeutig, `PART` darf `TOTAL` nicht überschreiten und alle Fragmente sollten dieselbe Gesamtzahl angeben.
- `AREA` enthält 1–8 Großbuchstaben, Ziffern oder Bindestriche. Führende Nullen sind signifikant und der Code muss exakt zur Geometriekennung des Profils passen.
- `MESSAGE_ID` sind fünf hexadezimale Großzeichen nach `{`. Sie bezeichnet ein Fragment, nicht den Gesamtalarm. Eine identische Wiederholung sollte dieselbe ID behalten; ein geändertes Fragment benötigt eine neue. Eine schließende Klammer gibt es nicht.

Zur Interoperabilität akzeptiert APRSBox eine etwas breitere alphanumerische APRS-Nachrichtenkennung; Herausgeber sollten dennoch die strengere CAWF-v1-Form verwenden.

## Schweregrade und Ereignisse

CAWF v1 definiert aktive Stufen:

```text
1 = gelb
2 = orange
3 = rot
```

Stufe `0` bedeutet keine aktive Warnung und darf nicht als aktive CAWF-Warnung gesendet werden. Stufe `4` ist reserviert. Das Länderprofil muss die Abbildung der amtlichen Quelle auf 1–3 dokumentieren.

Das anfängliche CAWF-Ereignisregister lautet:

```text
TSTORM WIND RAIN FLOOD FFLOOD SNOW ICE HEAT COLD FOG
COASTAL AVALANC FIRE DUST OTHER
```

APRSBox bewahrt den genauen Ereigniscode und nutzt bekannte Präfixe für UI-Kategorie und Symbol. Codes ohne eigene Kategorie bleiben unter `Sonstige / unbekannt` sichtbar und verwenden deren Schwellen.

## Fragmente und Duplikate

- Fragmente dürfen in beliebiger Reihenfolge eintreffen. APRSBox gruppiert sie nach Quellrufzeichen, Zielgruppe und `ALERT_ID`.
- Der Alarmeintrag enthält die Vereinigungsmenge eindeutiger Gebietscodes und zeigt empfangene sowie deklarierte Teile.
- Nach Empfang aller Teile von 1 bis `TOTAL` wird der Status `vollständig`, vorher bleibt er `unvollständig`.
- Ein wiederholtes Fragment mit gleicher APRS-Nachrichtenkennung wird dem vorhandenen Alarm zugeordnet und gezählt, ohne einen zweiten logischen Alarm anzulegen.
- Der CAWF-Entwurf empfiehlt, eine unvollständige Zusammensetzung nach 15 Minuten aufzugeben. APRSBox bewahrt sie derzeit bis zum normalen Ablauf oder zur manuellen Löschung; der Vollständigkeitsstatus muss daher beachtet werden.

## Lebenszyklus

- Das erste Fragment aktiviert oder erstellt den logischen Alarm, sofern die Alarmschwelle dies zulässt.
- Weitere Fragmente und identische Wiederholungen aktualisieren denselben Eintrag und behalten Verknüpfungen zu den Frames im Traffic Monitor.
- Die Wiederverwendung derselben `ALERT_ID` aktualisiert den auf Quelle und Gruppe begrenzten Eintrag. Herausgeber sollten eine Wiederverwendung mindestens 48 Stunden nach Ablauf vermeiden.
- Bei `EXPIRY` deaktiviert APRSBox den Alarm, bewahrt aber Frames und Verlauf.
- CAWF v1 kennt keine standardisierte ausdrückliche Aufhebung. Eine Stornoadresse oder ein eigener Token darf nicht als Aufhebung eines bestehenden APRSBox-Alarms vorausgesetzt werden.

## Länderprofile und Kartengeometrie

Ein Profil soll Gruppenbetreiber, autoritative Datenquelle, Herausgeber-Rufzeichen, Ereignis- und Schweregradabbildung, Bedeutung der Gebietscodes, Geometrieversion, Gültigkeits- und Wiederholungsregeln sowie Kontaktweg veröffentlichen.

Für eine Gruppe nach `CC-WARN` sucht APRSBox lokales GeoJSON im Verzeichnis des entsprechenden zweistelligen Ländercodes. Die Geometrie muss ein WGS84-`Polygon` oder `MultiPolygon` sein und ihre Kennung exakt dem übertragenen `AREA` entsprechen. `PL-WARN` verwendet einen eigenen Datensatz polnischer Landkreise.

Ein unbekannter Gebietscode bleibt im Alarm, wird auf der Karte aber ausgelassen. Betreffen mehrere aktive Alarme dieselbe Geometrie, bestimmt die höchste bekannte Stufe die Farbe; alle beteiligten Alarme werden aufgelistet.

## Vertrauen und Betriebssicherheit

CAWF v1 bietet keine kryptografische Authentifizierung. Der Entwurf empfiehlt pro Gruppe eine Liste vertrauenswürdiger Herausgeber sowie öffentliche Angaben zu HUB-Betreiber und Quelle. APRSBox erzwingt derzeit keine solche Liste; jeder Absender kann an eine konfigurierte Gruppe senden.

APRS ist als zusätzlicher Lagekanal zu behandeln. Wirkungsstarke Warnungen sollten bei der zuständigen Behörde geprüft werden, insbesondere bei unerwartetem Absender, unvollständigem Alarm, ungültigem Ablauf oder fehlender Geometrie. APRS-IS-Empfang belegt nur den Transport, nicht die Echtheit.

## Quellen

- Bereitgestellte Dateien `CAWF.md` und `CAWF-PL.md`, CAWF-v1-Entwurf.
- [TAPR APRS Protocol Reference — NWS-Bulletins und Nachrichtenregeln](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- [Dokumentation des NWS-CAP-Warndienstes](https://www.weather.gov/documentation/services-web-alerts) zur Abgrenzung vollständiger amtlicher Warnungen vom kompakten APRS-Transport.

[Zurück zu den APRS-Alarmeinstellungen](settings_alarms.de.md)
