# Anwendungsaktualisierung

Dieses Panel prüft die installierte APRSBox-Version und aktualisiert die Anwendung bei unterstützten Installationen aus dem ausgewählten Kanal.

## Aktualisierungskanal

Der Kanal bezeichnet den Quell-Branch für Versionsprüfung und Aktualisierung. Ein anderer Kanal als der stabile kann unfertige oder inkompatible Änderungen enthalten; bei einer solchen Auswahl bleibt die Warnung im Panel sichtbar.

`Aktualisierungskanal speichern` ändert die Quelle für spätere Prüfungen und Updates. Allein das Speichern aktualisiert die Anwendung nicht.

## Aktionen

- `Version prüfen` vergleicht die installierte Version mit dem gewählten Kanal und verändert die Installation nicht.
- `Anwendung aktualisieren` lädt den Code aus diesem Kanal, führt die Datenbankinitialisierung aus und startet abschließend `aprsbox-core` und `aprsbox-web` neu.
- Während des Neustarts kann die GUI vorübergehend die Verbindung verlieren. Der Fortschrittsdialog verfolgt den Hintergrundauftrag und versucht die Verbindung wiederherzustellen.

## Docker-Installationen

In Docker dient der Versionsvergleich nur zur Information; Aktualisierungsaktionen auf Host-Ebene sind deaktiviert. APRSBox wird aktualisiert, indem das gewünschte Image geladen und der Container mit dem verwendeten Bereitstellungswerkzeug neu erstellt wird.

Nur Administratoren und Operatoren können den Kanal ändern oder ein Update starten.
