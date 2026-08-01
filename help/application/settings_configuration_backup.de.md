# Konfigurationssicherung

Dieses Panel exportiert und importiert einen APRSBox-GUI-Konfigurationsstand als UTF-8-kodierte `JSON`-Datei.

## Enthaltene Daten

Die Sicherung enthält ausgewählte globale Einstellungen sowie Konfigurationen für Kartenquellen, TNC- und APRS-IS-Schnittstellen, Station und WX, Routing-Flows und -Regeln, APRS-Objekte und -Elemente, Bulletins und Referenzstationen für Bandbedingungen.

Laufzeitverkehr, Ereignisprotokolle, Nachrichtenverlauf, Benutzerkonten und andere Tabellen außerhalb des unterstützten Sicherungsformats sind nicht enthalten.

Die Datei kann Rufzeichen, APRS-IS-Verbindungsdaten, Pfade, Endpunkte und weitere betriebliche Konfiguration enthalten. Behandeln Sie sie als sensible Daten.

## Export und Import

- `Konfigurationssicherung exportieren` lädt den aktuellen Stand herunter.
- `Konfigurationssicherung importieren` prüft Format und Version und ersetzt danach die unterstützten Konfigurationstabellen in einer Datenbanktransaktion.
- Bei einem Validierungs- oder Datenbankfehler wird der Import zurückgerollt.

Der Import überschreibt die aktuelle unterstützte Konfiguration. Exportieren Sie den aktuellen Stand, bevor Sie eine andere Datei einspielen. Starten Sie nach erfolgreichem Import die APRSBox-Dienste neu; unter Docker muss der Container mit dem Bereitstellungswerkzeug neu erstellt oder gestartet werden.
