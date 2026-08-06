# Gefahrenzone

Diese Aktionen beeinflussen laufende Dienste oder den gesamten Host. Sie stehen nur Administratoren und Operatoren zur Verfügung und sind innerhalb von Docker deaktiviert.

## Dienste neu starten

Startet `aprsbox-core` und `aprsbox-web` neu. Funk- und Webverarbeitung pausieren währenddessen; der Browser kann kurz die Verbindung verlieren.

## Host neu starten

Startet das Betriebssystem neu. Alle APRSBox-Dienste und der Fernzugriff werden unterbrochen. Im Bestätigungsdialog muss exakt `REBOOT` eingegeben werden.

## Host ausschalten

Fährt das Betriebssystem herunter. Der Fernzugriff wird unterbrochen, und zum erneuten Einschalten kann physischer oder Out-of-Band-Zugriff erforderlich sein. Im Bestätigungsdialog muss exakt `POWER OFF` eingegeben werden.

Unter Docker sollte der Container über Docker oder die Bereitstellungsplattform neu gestartet oder erstellt werden, statt diese Host-Aktionen zu verwenden.
