# APRS-Nachrichten

Diese Registerkarte dient für APRS-Unterhaltungen, die lokal in der SQLite-Datenbank gespeichert werden. Die Liste links zeigt Gesprächspartner, der rechte Bereich zeigt den ausgewählten Thread und das Sendefeld.

## Unterhaltungen

- `Start new conversation` akzeptiert ein APRS-Rufzeichen in der Form `CALL` oder `CALL-SSID`.
- Das Basisrufzeichen darf bis zu 6 Zeichen haben, mit optionaler SSID `0-15`, zum Beispiel `SP9XYZ-7`.
- Ausgewählte APRS-Dienstziele sind ebenfalls erlaubt, zum Beispiel `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` oder `CQ`.
- Beim Öffnen einer Unterhaltung werden eingehende Nachrichten in diesem Thread als gelesen markiert.
- Das Symbol `Messages` in der Seitenleiste ändert sich, wenn ungelesene Nachrichten vorhanden sind.

Die Unterhaltungszeile zeigt außerdem, ob die Station kürzlich gehört wurde. Grün bedeutet frischen Verkehr, Warnung bedeutet älteren aktuellen Verkehr, und kein Eintrag bedeutet, dass es keinen aktuellen Frame in der lokalen Verkehrshistorie gibt.

## Senden

- APRS-Nachrichtentext ist auf `67` druckbare ASCII-Zeichen begrenzt.
- Nationale Zeichen und Steuerzeichen werden blockiert, weil das klassische APRS-Nachrichtenformat ein kurzes ASCII-Feld ist.
- Das Feld `Path` setzt den RF-Pfad für die Übertragung. Wenn es leer bleibt, wird der Standardpfad der Station aus den Beacon-Einstellungen verwendet.
- Der Pfad wird pro Unterhaltung gespeichert und kann auch von automatischen ACKs verwendet werden.

Eine normale Nachricht erhält eine APRS-Nachrichtennummer und wartet auf `ACK` oder `REJ` von der Gegenstation.

## Status

- `Queued` bedeutet, dass die Nachricht in der Outbound-Warteschlange wartet.
- `Sent` bedeutet, dass der Frame gesendet wurde.
- `Sent X/Y` zeigt die Versuchszahl und das Versuchslimit für eine nummerierte Nachricht.
- `ACK` bedeutet, dass die Gegenstation die Nachricht bestätigt hat.
- `Rejected (REJ)` bedeutet, dass die Gegenstation sie abgelehnt hat.
- `No ACK` bedeutet, dass nach dem Wiederholungsfenster keine Bestätigung empfangen wurde.

Für normale Nachrichten plant APRSBox automatische Wiederholungen in späteren Versuchen. Nach Ausschöpfen der Versuche kann eine fehlgeschlagene Nachricht mit der Schaltfläche `No ACK` manuell erneut gesendet werden.

## APRS-Abfragen

Wenn der Text mit `?` beginnt, wird die Nachricht als APRS-Abfrage behandelt. Solche Frames werden ohne Nachrichtennummer gesendet und verwenden nicht dasselbe automatische ACK-/Retry-Fenster wie normale Nachrichten.

APRSBox erkennt und beantwortet eingehende Abfragen automatisch:

- `?APRS`,
- `?APRSP`,
- `?APRSS`,
- `?APRSD`,
- `?DX`,
- `?APRSV`,
- `?VER`.

Eingehende nummerierte Nachrichten und Abfragen werden automatisch mit einem `ack`-Frame bestätigt.
