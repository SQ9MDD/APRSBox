# APRS-Alarmeinstellungen

Dieses Panel steuert Alarmempfang, Übernahme in die Alarmliste, Notfall-Popups und den automatischen APRS-IS-Filter für Alarmgruppen.

## Hauptschalter und Gruppen

- `APRS-Alarme aktivieren` schaltet die Alarmverarbeitung ein oder aus.
- `Alarmgruppen` akzeptiert einen oder mehrere durch Kommas getrennte APRS-Gruppennamen.
- Gespeicherte Alarmgruppen werden den wirksamen RF-Empfangsgruppen und dem automatischen APRS-IS-Gruppenfilter hinzugefügt.

Die Zusammenfassung unter dem Formular zeigt die wirksamen RF-Gruppen und den exakten automatisch erzeugten Filter.

## Schwellen je Ereignistyp

Jede Ereigniskategorie besitzt zwei unabhängige Schwellen:

- `Alarme` steuert die Übernahme von Nachrichten in die Alarmliste.
- `Alarm-Popup` steuert das Notfall-Popup.
- Ein Zahlenwert akzeptiert diese und alle höheren Schweregrade.
- `Aus` deaktiviert die Kategorie in der jeweiligen Spalte.

Unbekannte Schweregrade werden aus Sicherheitsgründen beibehalten und nicht stillschweigend verworfen.

Die Sichtbarkeit von Alarmen auf der Karte wird direkt im Alarmpanel der Kartenseite eingestellt. Diese Einstellungen ersetzen diesen Kartenschalter nicht.
