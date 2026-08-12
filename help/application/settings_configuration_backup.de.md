# Konfigurationssicherung

Dieses Panel exportiert und importiert einen APRSBox-GUI-Konfigurationsstand als UTF-8-kodierte `JSON`-Datei.

## Enthaltene Daten

Die v2-Sicherung enthält globale, Nachrichten- und Benachrichtigungseinstellungen sowie Konfigurationen für Kartenquellen, TNC- und APRS-IS-Schnittstellen, Station und WX, Benachrichtigungstransporte und Radarregeln, Routing-Flows und -Regeln, APRS-Objekte und -Elemente sowie Bulletins.

Laufzeitverkehr, Transporttestergebnisse, Benachrichtigungsradarstatus, Ereignisprotokolle, Nachrichtenverlauf, eigene APRS-Alarme, Benutzerkonten und andere Tabellen außerhalb des unterstützten Sicherungsformats sind nicht enthalten.

Die Datei kann Rufzeichen, APRS-IS-Verbindungsdaten, Pfade, Endpunkte, Webhook- und Telegram-Tokens und weitere betriebliche Konfiguration enthalten. Behandeln Sie sie als sensible Daten.

## Export und Import

- `Konfigurationssicherung exportieren` lädt den aktuellen Stand herunter.
- `Konfigurationssicherung importieren` prüft Format und Version und ersetzt danach die unterstützten Konfigurationstabellen in einer Datenbanktransaktion.
- Bei einem Validierungs- oder Datenbankfehler wird der Import zurückgerollt.
- Nur das v2-Format wird unterstützt. Von älteren Versionen erstellte v1-Dateien können nicht importiert werden.

Der Import überschreibt die aktuelle unterstützte Konfiguration. Exportieren Sie den aktuellen Stand, bevor Sie eine andere Datei einspielen. Starten Sie nach erfolgreichem Import die APRSBox-Dienste neu; unter Docker muss der Container mit dem Bereitstellungswerkzeug neu erstellt oder gestartet werden.
