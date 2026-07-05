# WX

Der WX-Tab konfiguriert die lokale APRSBox-Wetterstation. Daten werden aus HTTP-Quellen gelesen, in das APRS complete WX Format normalisiert und als lokaler Wetterframe gesendet.

## Reihenfolge der Einrichtung

- Setze das Stationsrufzeichen in `My Settings`.
- Wähle eine eigene `WX SSID` für die Wetterstation.
- Lege eine Quelle in `WX data sources` an.
- Teste die Quelle oder starte `Discover source`.
- Weise Quellen und Kennungen in `WX data mapping` zu.
- Starte Testlesungen für die Pflichtparameter.
- Aktiviere `Enable WX`, speichere die Konfiguration und prüfe `WX TX Log`.

## Global WX configuration

- `Callsign` wird aus `My Settings` gelesen und in diesem Tab nicht bearbeitet.
- `WX SSID` bildet das Rufzeichen der Wetterstation, zum Beispiel `SQ9XYZ-13`. Die SSID der Hauptstation ist für WX nicht verfügbar.
- `Interface` wählt den TNC für den WX-Frame oder die Option zum Senden über alle aktiven Schnittstellen.
- `Path` setzt den APRS-Pfad für den WX-Frame. Ein leeres Feld oder `RFONLY` gilt als direkte Aussendung ohne Digipeater.
- Leerer Pfad und `RFONLY` erlauben kürzere Intervalle. Ein gerouteter Pfad wie `WIDE2-2` begrenzt die Liste auf längere Intervalle.
- `Latitude` und `Longitude` definieren die Position der Wetterstation. `Get location` erlaubt die Auswahl auf der Karte.
- `Refresh / TX interval` steuert den Zyklus für Datenabruf und WX-Sendeplanung.
- `Allow cached values on failure` erlaubt die Nutzung des letzten gültigen Werts, wenn eine Quelle vorübergehend nicht antwortet.
- `Default max cache age (s)` legt fest, wie lange ein Cache-Wert noch nutzbar ist.

`Refresh now` liest die konfigurierten Zuordnungen und aktualisiert den Cache. `Send now` speichert die Formularwerte, führt einen manuellen Refresh aus und stellt erst danach den WX-Frame in die Sendewarteschlange.

## WX data mapping

Eine Zuordnung verbindet einen APRS-WX-Parameter mit einer Quelle und einer Kennung innerhalb dieser Quelle.

Die Pflichtparameter für den einfachen WX-Frame sind:

- `Wind direction` in Grad,
- `Wind speed` in mph,
- `Temperature` in Fahrenheit.

Optionale Parameter sind Windböe, Regen der letzten Stunde, Regen in 24 Stunden, Regen seit Mitternacht, Luftfeuchte, Luftdruck, Schnee, Helligkeit, Rohzähler für Regen, Wasserstand, Batteriespannung und Strahlung.

`Raw value` und `Normalized` zeigen den aus der Quelle gelesenen Wert und den in die APRS-Einheit umgerechneten Wert. `LIVE` bedeutet frische Lesung, `CACHED` bedeutet Nutzung des letzten gültigen Werts, und `MISSING`, `STALE` oder `ERROR` bedeuten, dass Quelle, Kennung oder Einheit geprüft werden sollten.

## WX data sources

- `Home Assistant` nutzt die Home-Assistant-API und benötigt `Bearer token`.
- `Domoticz` nutzt die Domoticz-API und unterstützt keine Authentifizierung oder `Basic auth`.
- `Base URL` sollte auf die Hauptadresse des Systems zeigen, zum Beispiel `http://127.0.0.1:8123`.
- `Timeout (s)` begrenzt die Wartezeit auf eine Antwort der Quelle.
- `Verify TLS certificate` sollte bei gültigen HTTPS-Zertifikaten aktiviert bleiben.
- `Enable source` entscheidet, ob die Quelle für Lesungen verwendet werden kann.

Das Testsymbol prüft die Verbindung zur Quelle. Das Discovery-Symbol lädt erkannte Entitäten oder Geräte und hilft beim Eintragen des richtigen `Identifier` in der Zuordnung.

## WX TX Log

Das Log zeigt aktuelle WX-Jobs: Zeit, Typ, Status, Schnittstelle, Versuche, Fehler und TNC2-Framevorschau. Wenn ein Frame nicht gesendet wird, prüfe zuerst Pflichtzuordnungen, Position, aktiviertes WX, aktiven TNC und die Fehlermeldung im Log.
