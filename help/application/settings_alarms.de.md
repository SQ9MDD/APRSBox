# APRS-Alarmeinstellungen

Dieses Panel konfiguriert den reinen Empfangskanal für APRS-Gruppenalarme. Es legt fest, welche Zielgruppen als Alarme gelten, welche Ereignisse in die Alarmliste gelangen, welche ein Notfall-Popup öffnen dürfen und welche Gruppen dem APRS-IS-Empfangsfilter hinzugefügt werden.

## Schnellkonfiguration

- `APRS-Alarme` aktivieren.
- Kommagetrennte Gruppenadressen eintragen, zum Beispiel `PL-WARN, NWS-WARN`.
- Für jede Ereigniskategorie die Schwellen `Alarme` und `Alarm-Popup` festlegen.
- Speichern und die unter dem Formular angezeigten wirksamen RF-Gruppen sowie den automatischen APRS-IS-Filter prüfen.

Ein Gruppenname darf 1–9 Großbuchstaben, Ziffern oder Bindestriche enthalten. Kleinbuchstaben werden umgewandelt, Duplikate entfernt und Bulletin-Adressen mit `BLN...` abgewiesen.

## Verarbeitung eines empfangenen Frames

- Nur eine APRS-Nachricht an eine aktivierte und konfigurierte Alarmgruppe gelangt in diesen Pfad.
- Der Ereignisname wählt eine Kategorie wie Tornado, Gewitter, Hochwasser, Wind, Hitze oder `Sonstige / unbekannt`.
- Die Endziffern des Ereigniscodes werden als Schweregrad interpretiert.
- `Alarme` bestimmt, ob der Frame einen Eintrag in der Alarmliste anlegt oder aktualisiert.
- `Alarm-Popup` bestimmt unabhängig, ob der erste Frame dieses Alarms das globale Popup öffnen darf.
- Die Kartenebene besitzt auf der Kartenseite einen eigenen Sichtbarkeitsschalter und benötigt für jeden Gebietscode einen passenden lokalen Geometrieeintrag.

Eine numerische Schwelle akzeptiert diesen und alle höheren Grade. `Aus` deaktiviert die Kategorie in der jeweiligen Spalte. Ein unbekannter Schweregrad bleibt bei aktivierter Kategorie erhalten, damit neue oder fehlerhafte Formate nicht still verworfen werden; er hat keine gelbe, orange oder rote Einstufung und erscheint bei vorhandener Geometrie grau.

## Unterstützte Warnformate

- [Ausführliche CAWF-Hilfe](settings_alarms_cawf.de.md) — Länderprofile wie `PL-WARN`, mehrteilige Alarme, Geometrie, Lebenszyklus und Vertrauen.
- [Ausführliche NWS-WARN-Hilfe](settings_alarms_nws_warn.de.md) — US-County-Warnformat, UGC-Codes, Kartenabdeckung und Grenzen von APRSBox.
- [Alarmliste, Stummschalten und Löschen](alerts.de.md) — Bedienung nach Annahme eines Alarms.

## Wichtige Grenzen

- Der Schalter betrifft konfigurierte Alarmgruppen. Native APRS-Emergency- und Mic-E-Emergency-Frames verwenden das gemeinsame Alarmsystem unabhängig davon.
- Alarmgruppen-Nachrichten erscheinen nicht in normalen Unterhaltungen, lösen keine üblichen Nachrichten-Benachrichtigungstransporte aus und werden nie mit einem APRS-ACK bestätigt.
- APRSBox authentifiziert Warnherausgeber derzeit nicht und führt keine Liste vertrauenswürdiger Absender pro Gruppe. Der Empfang über APRS-IS allein beweist keine amtliche Herkunft.
- Eine ungültige oder fehlende Ablaufzeit `DDHHMMz` kann nicht automatisch aufgelöst werden. Ein solcher Eintrag kann aktiv bleiben, bis er ersetzt oder manuell gelöscht wird.
