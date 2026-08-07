# APRS-Notfallalarme

Die Registerkarte `Alarme` zeigt logische Alarme aus nativen APRS-Notfallframes sowie aus CAWF- und `NWS-WARN`-Gruppennachrichten. Alle erscheinen in derselben Liste und bieten Details, Frame-Verlauf, Stummschaltung und Löschen.

`NWS-WARN` dient zum Empfang kompakter US-Wetterwarnungen auf County-Ebene. Die Alarmdetails enthalten unter anderem Ereignis, Stufe, Ablaufzeit und UGC-Gebietscodes; erkannte Countys werden auf der Karte hervorgehoben. Dieses Profil ist nur für den Empfang bestimmt: APRSBox kann einen `NWS-WARN`-Alarm weder senden noch aufheben. Gruppenkonfiguration, Frame-Format, Stufen, Gebietszuordnung und Einschränkungen beschreibt die [ausführliche NWS-WARN-Hilfe](settings_alarms_nws_warn.de.md).

- Ein Klick auf eine Zeile öffnet das Modal mit dem neuesten Alarmframe.
- Die Schaltfläche mit den Alarmdetails öffnet den vollständigen Datensatz und den Verlauf der zugehörigen Frames.
- Das Stummschalten stoppt weder die Aktualisierung des Alarms noch den Frame-Zähler.
- Beim Löschen eines Alarms bleiben die ursprünglichen Frames im Verkehrsmonitor erhalten.

## Alarmton im Browser

Browser können die automatische Tonwiedergabe standardmäßig blockieren. In diesem Fall erscheint das Alarm-Modal korrekt, der Ton beginnt jedoch erst nach einem Klick auf die Seite.

Auf dem Computer, auf dem APRSBox angezeigt wird:

1. Öffne die Website-Berechtigungen neben der Adressleiste.
2. Suche die Einstellung `Automatische Wiedergabe`.
3. Wähle `Audio und Video erlauben` oder die entsprechende Option, die Ton erlaubt.
4. Lade den APRSBox-Tab neu.

Diese Berechtigung muss im Browser des Anzeigegeräts gesetzt werden. Der APRSBox-Server kann auf einem anderen Gerät laufen.

Prüfe außerdem, ob Tab, Browser und Betriebssystem nicht stummgeschaltet sind und ob der richtige Audioausgang ausgewählt ist.

Nachdem die automatische Wiedergabe erlaubt wurde, öffnet ein nicht stummgeschalteter Frame, der den Popup-Schwellwert erfüllt, das Modal und startet den Ton ohne zusätzlichen Klick. Das gilt auch für `NWS-WARN`, wenn Kategorie und Stufe den konfigurierten Popup-Schwellwert erreichen. Ein stummgeschalteter Alarm wird weiterhin aktualisiert, bleibt aber absichtlich lautlos.

## Stummschalten

Alarme können für `1 Stunde`, `4 Stunden`, `24 Stunden` oder unbegrenzt stummgeschaltet werden. Nach Ablauf einer zeitlichen Stummschaltung kann erst ein weiterer Frame dieses Alarms das Modal und den Ton auslösen.

## Löschen

Beim Löschen werden der logische Alarmdatensatz und seine Beziehungen entfernt. Die ursprünglichen Frames bleiben im Verkehrsmonitor. Ein späterer passender Frame kann den Alarm erneut erstellen.
