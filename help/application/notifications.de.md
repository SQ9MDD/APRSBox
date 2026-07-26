# Benachrichtigungen

Diese Registerkarte konfiguriert externe Benachrichtigungen, die APRSBox sendet. Benachrichtigungen funktionieren in zwei Schritten: zuerst wird ein Transport definiert, danach werden die Ereignistypen aktiviert, die gesendet werden sollen.

## Transporte

Ein Transport legt fest, wohin APRSBox ein Ereignis sendet.

- `Webhook` sendet das Ereignis als HTTP `POST` mit JSON-Inhalt an die konfigurierte URL.
- `Telegram` sendet eine Nachricht über einen Telegram-Bot an die konfigurierte `Chat ID`.
- Beim normalen Ereignisversand werden nur Transporte mit `Enabled` verwendet.
- Die Testschaltfläche sendet ein Ereignis `APRSBox notification test` und speichert das Testergebnis des Transports.

Für Webhooks können `Secret header name` und `Secret token` konfiguriert werden. Wenn beide Felder ausgefüllt sind, fügt APRSBox diesen HTTP-Header zur Anfrage hinzu.

`Timeout` wird in Sekunden gezählt. Der erlaubte Bereich ist `1` bis `60`, der Standardwert ist `5`.

Beim Bearbeiten eines bestehenden Transports bleibt ein vorhandenes Geheimnis unverändert, wenn das Geheimnisfeld leer bleibt.

## Benachrichtigungseinstellungen

- `Enable APRS message notifications` aktiviert Benachrichtigungen für eingehende APRS-Nachrichten.
- `Include message content` steuert, ob der Text der APRS-Nachricht in der Benachrichtigung enthalten ist.
- `Enable radar notifications` aktiviert Stationsradar-Regeln.
- `Ignored radar patterns` schließt Stationen von der Radarverarbeitung aus. Muster können mit Kommas oder Zeilenumbrüchen getrennt werden. Der Platzhalter `*` wird unterstützt.

Das Deaktivieren der Radarbenachrichtigungen löscht den gemerkten Wiederholungssperrstatus und das Radar-Ereignislog.

## Radarregeln

Eine Radarregel erkennt Stationen, die zu einem Rufzeichenmuster und optional zu einem Entfernungslimit von `My Station` passen.

- `Radar rule` ist ein Rufzeichen oder Rufzeichenmuster, zum Beispiel `SQ6ODL-*`, `SR*` oder `*`.
- `Distance (m)` ist die maximale Entfernung von den Koordinaten der lokalen Station.
- Der Wert `0` bedeutet kein Entfernungslimit.
- Wenn die Entfernung größer als `0` ist, erfüllt eine Station ohne bekannte Koordinaten die Regel nicht.

Radar sendet eine Benachrichtigung nur dann, wenn eine Station in den Bereich der Regel eintritt. Solange die Station im Bereich bleibt, werden Wiederholungsbenachrichtigungen blockiert. Die Sperre wird erst entfernt, wenn die Station den Bereich verlässt oder ihre Position aus den sichtbaren Daten abläuft.

Die lokale Station und die aktive APRSBox-Wetterstation werden automatisch ignoriert.

## Radar-Ereignislog

Das Log zeigt die letzten Änderungen des Radarstatus: Benachrichtigung gesendet, Wiederholungssperre angelegt und Sperre entfernt, nachdem die Station den Bereich verlassen hat.
