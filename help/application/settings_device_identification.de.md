# APRS-Geräteerkennung

APRSBox verwendet diese Datenbank, um APRS-Software und -Hardware anhand von Ziel-`TOCALL`-Werten und Mic-E-Kennungen zu erkennen. Das Ergebnis erscheint in Stationsdetails und Gerätestatistiken.

## Aktive Datenquelle

APRSBox bevorzugt einen gültigen lokalen Cache. Ist kein gültiger Cache vorhanden, wird der mitgelieferte Datenbestand verwendet.

- `Status` meldet, ob Cache oder mitgelieferter Rückfallbestand aktiv ist.
- `Aktive Quelle` zeigt die aktuell für Suchen verwendete Quelle.
- `Erstellungszeit` ist der im Identifikationsdatensatz enthaltene Zeitstempel.
- `Letzte erfolgreiche Aktualisierung` speichert den letzten abgeschlossenen Download.
- `Lokaler Cache` und `Lokaler Cache aktualisiert` beschreiben die heruntergeladene Datei.
- `Letzter Aktualisierungsfehler` bleibt nach einem fehlgeschlagenen Versuch sichtbar.

## Aktualisieren

`Jetzt aktualisieren` lädt einen neuen Datensatz, prüft seine Struktur und ersetzt den lokalen Cache erst nach erfolgreicher Validierung. Ein fehlgeschlagener Download entfernt weder den nutzbaren mitgelieferten Bestand noch einen zuvor gültigen Cache.

Die Aktualisierung benötigt Netzwerkzugriff und kann nur von Administratoren oder Operatoren gestartet werden.
