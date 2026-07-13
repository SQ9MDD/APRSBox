# APRS-Nachrichten

Diese Registerkarte dient für APRS-Unterhaltungen, die lokal in der SQLite-Datenbank gespeichert werden. Die Liste links zeigt Gesprächspartner, der rechte Bereich zeigt den ausgewählten Thread und das Sendefeld.

## Unterhaltungen

- `Start new conversation` akzeptiert ein APRS-Rufzeichen in der Form `CALL` oder `CALL-SSID`.
- Das Basisrufzeichen darf bis zu 6 Zeichen haben, mit optionaler SSID `0-15`, zum Beispiel `SP9XYZ-7`.
- Ausgewählte APRS-Dienstziele sind ebenfalls erlaubt, zum Beispiel `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` oder `CQ`.
- Beim Öffnen einer Unterhaltung werden eingehende Nachrichten in diesem Thread als gelesen markiert.
- Das Symbol `Messages` in der Seitenleiste ändert sich, wenn ungelesene Nachrichten vorhanden sind.

Die Unterhaltungszeile zeigt außerdem, ob die Station kürzlich gehört wurde. Grün bedeutet frischen Verkehr, Warnung bedeutet älteren aktuellen Verkehr, und kein Eintrag bedeutet, dass es keinen aktuellen Frame in der lokalen Verkehrshistorie gibt.

## Nachrichteneinstellungen

Der Bereich `Nachrichteneinstellungen` befindet sich unter dem Unterhaltungsbereich:

- `Standardpfad` wird für neue Unterhaltungen, Gruppennachrichten und automatische APRS-Antworten verwendet.
- `Nachrichten für jede SSID meines Rufzeichens empfangen` erlaubt die Anzeige von Nachrichten an andere SSIDs desselben Basisrufzeichens. Nur das exakt konfigurierte `CALL-SSID` erhält ein `ACK` oder eine automatische Antwort.
- `Zielgruppen` definiert die gemeinsamen Nachrichtenadressen, die APRSBox empfängt.

Bei der ersten Verwendung, solange noch keine Gruppeneinstellung gespeichert wurde, enthält die Liste `ALL`, `QST` und `CQ`. Entfernt der Benutzer diese Werte und speichert ein leeres Feld, bleibt die Liste leer.

Gruppen werden in einem Feld eingegeben und durch Kommas getrennt, zum Beispiel `CQ, QST, ALL, WAW, BEM`. Leerzeichen um die Namen werden entfernt, Buchstaben in Großbuchstaben umgewandelt und Duplikate verworfen. Jeder Name muss zwischen `1` und `9` Zeichen aus `A-Z` oder `0-9` enthalten. Leere Einträge, Sonderzeichen, innere Leerzeichen und mit `BLN` beginnende Adressen werden abgelehnt.

## Gruppenunterhaltungen

- Eine Gruppenunterhaltung wird nur für einen Adressaten erstellt, der in der gespeicherten Liste `Zielgruppen` enthalten ist.
- Eine Nachricht an eine nicht definierte Gruppe wie `BEM` wird ignoriert: Es entstehen keine Unterhaltung, kein Verlaufseintrag, kein Ungelesen-Status, keine Benachrichtigung und kein `ACK`.
- Der Schlüssel der Unterhaltung ist die Gruppenadresse, zum Beispiel `WAW`, nicht das Rufzeichen des Absenders. Nachrichten mehrerer Stationen erscheinen im selben chronologischen `WAW`-Thread.
- Der tatsächliche Absender, zum Beispiel `SQ5WLA-9`, wird über jeder Gruppennachricht angezeigt. Eine eigene Nachricht ist mit `Du · CALL-SSID` gekennzeichnet.
- Eine von APRSBox an eine Gruppe gesendete Nachricht wird einmal übertragen: ohne Nachrichtennummer, ohne Warten auf ein `ACK` und ohne automatische Wiederholungen.
- APRSBox bestätigt niemals eine Gruppennachricht, auch wenn das sendende Gerät eine Nachrichtennummer angefügt hat.
- Das Entfernen einer Gruppe aus den Einstellungen stoppt den Empfang neuer Nachrichten an diese Gruppe, löscht aber nicht den vorhandenen Unterhaltungsverlauf.

Eine Gruppe ist keine Station; deshalb zeigt ihr Thread keinen Status „kürzlich gehört“. `BLN...`-Bulletinadressen werden getrennt verarbeitet und können nicht als normale Nachrichtengruppen hinzugefügt werden.

## Senden

- APRS-Nachrichtentext ist auf `67` druckbare ASCII-Zeichen begrenzt.
- Nationale Zeichen und Steuerzeichen werden blockiert, weil das klassische APRS-Nachrichtenformat ein kurzes ASCII-Feld ist.
- Das Feld `Path` setzt den RF-Pfad für die Übertragung. Wenn es leer bleibt, wird der `Standardpfad` aus den Nachrichteneinstellungen verwendet.
- Der Pfad wird pro Unterhaltung gespeichert und kann auch von automatischen ACKs verwendet werden.

Eine normale Nachricht in einer direkten Unterhaltung erhält eine APRS-Nachrichtennummer und wartet auf `ACK` oder `REJ` von der Gegenstation. Für Gruppennachrichten gelten die oben beschriebenen Regeln ohne ACK und Wiederholungen.

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

Eingehende nummerierte Nachrichten und Abfragen werden nur dann automatisch mit einem `ack`-Frame bestätigt, wenn sie exakt an das konfigurierte lokale `CALL-SSID` adressiert sind. Gruppennachrichten und Nachrichten an eine andere SSID des lokalen Rufzeichens werden weder bestätigt noch durch automatische Antworten verarbeitet.
