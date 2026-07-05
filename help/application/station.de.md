# Meine Station

Dieser Tab konfiguriert die Hauptstation von APRSBox: Rufzeichen, Positionsbeacon, separaten APRS Status, Kartensymbol und manuelles Senden lokaler Frames.

## Position Beacon

Der Positionsbeacon ist ein APRS-Frame mit der Position der lokalen Station. Er wird von Karten, anderen Stationen und `Local TX`-Routingregeln verwendet.

- `Callsign` ist das Hauptrufzeichen ohne SSID.
- `SSID` wählt den Rufzeichen-Suffix, zum Beispiel `SQ9XYZ-4`.
- `Interface` wählt den sendenden TNC, alle aktiven Schnittstellen oder `Internal TX`.
- `Beacon Comment` wird in den Positionsframe übernommen und hat ein kurzes Limit für druckbares ASCII.
- `Beacon at every` setzt das automatische Beacon-Intervall oder den Modus `Proportional Path`.
- `Beacon Path` setzt den RF-Pfad, zum Beispiel ein leeres Feld für lokale Aussendung oder `WIDE2-1`.
- `Get location` setzt die Koordinaten über die Karte.
- `Symbol Table`, `Symbol Code` und `Overlay` wählen das APRS-Symbol auf Karten.
- `Enable automatic beacon transmission every selected interval` aktiviert periodische Beacon-Aussendung.

`Send beacon` speichert das aktuelle Formular und stellt sofort einen Beacon-Frame in die Warteschlange.

## Pfad und Kanallast

APRSBox zeigt eine Warnung, wenn der gewählte Pfad und das Intervall zu viel RF-Kanallast erzeugen können.

- Leerer Pfad, `DIRECT` oder kein Wide-Pfad bedeutet lokale Aussendung.
- Ein Ein-Hop-Pfad sollte normalerweise ein längeres Intervall verwenden.
- Ein Zwei-Hop-Pfad wie `WIDE2-2` braucht besondere Vorsicht.
- `Proportional Path` sendet häufige lokale Frames und seltenere Full-Path-Frames, um die Kanallast zu reduzieren.

Wenn die Anwendung beim Speichern eine Bestätigung verlangt, kann diese Einstellung den RF-Verkehr deutlich erhöhen.

## PHG Generator

Das Rechnersymbol neben `Beacon Comment` erzeugt einen `PHG`-Code aus Leistung, Antennenhöhe, Gewinn und Antennenrichtung. Der erzeugte Code wird an den Anfang des Beacon-Kommentars eingefügt.

PHG ist vor allem für feste Stationen, Repeater, Gateways und Digipeater nützlich. Eine normale Mobilstation benötigt ihn meistens nicht.

## APRS Status

`APRS Status` ist ein separater Frame mit dem Datentypkennzeichen `>`. Er ersetzt nicht den Kommentar des Positionsbeacons.

- `Status Text` ist der Statustext und hat ein eigenes Längenlimit.
- `APRS Status at every` setzt das periodische Statusintervall.
- `Enable periodic APRS Status transmission` aktiviert automatisches Senden des Status.

`Send status` speichert das aktuelle Formular und stellt einen Status-Frame in die Warteschlange. Wenn Status aktiviert ist, darf der Statustext nicht leer sein.

## Internal TX

`Internal TX` sendet nicht direkt über einen physischen TNC. Frames werden lokal erzeugt und können danach von `Packet Routing`-Regeln verarbeitet werden, zum Beispiel `Local TX -> TX APRS-IS`.

Wenn keine aktive Regel `Local TX -> TX APRS-IS` vorhanden ist, verhält sich Internal TX wie ein lokales schwarzes Loch: Der Frame wird in APRSBox erzeugt, verlässt das System aber nicht.

## Station TX Log

Das Log zeigt aktuelle Beacon- und Status-Jobs: Zeit, Typ, Status, Schnittstelle, Versuche, Fehler und TNC2-Framevorschau. Eine durchgestrichene Zeile bedeutet, dass der Job gespeichert wurde, die Übertragung aber übersprungen wurde, zum Beispiel wegen deaktiviertem oder TX-gesperrtem TNC.
