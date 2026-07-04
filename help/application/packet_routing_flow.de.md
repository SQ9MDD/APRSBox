# Detaillierte Beschreibung der Routing-Blocke

Dieses Dokument beschreibt die Blocke im Editor fur eine einzelne Routing-Regel. Jede Regel hat eine Quelle, null oder mehr Filter in der Mitte und ein Ziel.

## Wie eine Regel ausgewertet wird

Pakete laufen von oben nach unten durch die Regel.

1. Das Paket kommt aus der Quelle.
2. Es durchlauft jeden Filter- oder Regelblock der Reihe nach.
3. Wenn ein Block das Paket ablehnt, werden die folgenden Schritte nicht mehr ausgefuhrt.
4. Wenn das Paket alle Schritte passiert, erreicht es das Ziel.

## Quellblocke

### `Receiver RF`

Eingang fur Pakete, die von einem bestimmten Funkmodem empfangen wurden.

Verwende ihn, wenn die Regel eingehenden RF-Verkehr behandeln soll.

### `Local TX`

Eingang fur Frames, die APRSBox lokal selbst erzeugt.

Dazu gehoren:

- Beacons,
- Status,
- Wetter,
- Objekte,
- Items,
- Bulletins,
- Nachrichten.

Nicht dazu gehoren per RF empfangene oder bereits digipeatete Frames.

## Filter- und Regelblocke

### `Strict Filter`

Das ist der Systemsicherheitsfilter fur Regeln mit APRS-IS als Ziel.

Er:

- lehnt Pakete mit `TCPIP` oder `TCPXX` ab,
- lehnt Pakete mit `NOGATE` oder `RFONLY` ab,
- validiert Third-Party-Frames,
- blockiert fehlerhafte aussere oder innere Pfade.

Verwende ihn:

- als verpflichtenden Schutz fur `TX APRS-IS`,
- um APRS-IS-Weiterleitung sicher und regelkonform zu halten.

### `Path rule and DIGI guard`

Das ist der zentrale Block fur `RF -> RF`-Regeln.

Er:

- analysiert den Digi-Pfad,
- entscheidet, ob die lokale Station das Paket noch wiederholen soll,
- blockiert lokal adressierte Nachrichten und Anfragen,
- blockiert Third-Party-Verkehr, der nicht wiederholt werden soll,
- blockiert Frames, die von dieser Station bereits wiederholt wurden.

Verwende ihn:

- in jeder RF-Wiederholregel,
- als Kernblock fur Digi-Verhalten und Pfadsteuerung.

### `Duplicate Filter (viscous-delay)`

Dieser Block offnet ein kurzes Horfenster und pruft, ob ein anderes Digi denselben Frame bereits wiederholt hat.

Wenn ja:

- wird das Paket verworfen.

Wenn nein:

- lauft das Paket nach Ablauf des Fensters weiter.

Verwende ihn:

- in RF-Digi-Pfaden, wenn Doppelungen reduziert werden sollen,
- als ersten Filter in einer typischen RF-Regel.

### `Direct Only`

Lasst nur direkt gehorte Pakete ohne bereits verbrauchten Digi-Hop durch.

Verwende ihn:

- wenn die Regel nur auf lokal gehorte Stationen reagieren soll,
- wenn bereits wiederholter Verkehr ignoriert werden soll.

### `DIGI Filter`

Prugt, welche Digipeater bereits im verbrauchten Pfad auftauchen.

Modi:

- `allow` lasst nur passende Pakete durch,
- `deny` lehnt passende Pakete ab.

Verwende ihn:

- um nur Verkehr aus bestimmten Digi-Ketten zu akzeptieren,
- um Pakete zu blockieren, die bereits uber bestimmte Digis gelaufen sind.

### `Callsign Filter`

Vergleicht das Quellrufzeichen des Pakets.

Modi:

- `allow` lasst nur passende Rufzeichen durch,
- `deny` lehnt passende Rufzeichen ab.

Verwende ihn:

- fur Allowlists und Blocklists,
- um Club-, Service- oder Testverkehr zu trennen.

### `Packet Type Filter`

Arbeitet mit den wichtigsten APRS-Paketgruppen.

Unterstutzte Gruppen:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Verwende ihn:

- um Positionen, Nachrichten, Wetter oder Objekte unterschiedlich zu behandeln,
- um eine Regel auf eine Verkehrsklasse zu beschranken.

### `Icon Filter`

Vergleicht das APRS-Symbol.

Verwende ihn:

- um bestimmte Symboltypen zuzulassen oder zu blockieren,
- um getrennte Wege fur mobilen, Wetter- oder Spezialobjekt-Verkehr zu bauen.

### `Distance Filter`

Lasst ein Paket nur dann durch, wenn seine decodierte Position in mindestens einer konfigurierten Zone liegt.

Eigenschaften:

- es konnen 1 bis 3 Zonen definiert werden,
- jede Zone hat Mittelpunkt und Radius,
- Pakete ohne decodierbare Position werden von diesem Filter nicht automatisch abgelehnt.

Verwende ihn:

- um Verkehr auf einen geografischen Bereich zu begrenzen,
- um lokale Digi- oder Gate-Zonen aufzubauen.

### `Rate Limit Filter`

Begrenzt, wie oft Pakete eines Rufzeichens oder Rufzeichenmusters weiterlaufen durfen.

Er:

- misst die Zeit seit dem zuletzt durchgelassenen Paket fur jede passende Regel,
- blockiert das nachste Paket, wenn es vor Ablauf des Limits eintrifft.

Verwende ihn:

- um sehr aktive Stationen zu beruhigen,
- um RF vor wiederholten Bursts zu schutzen,
- um Verkehr zu reduzieren, ohne eine Quelle komplett zu sperren.

## Zielblocke

### `TX RF`

Sendet das Paket uber das gewahlte Funkmodem.

Verwende ihn fur:

- lokale Digi-Pfade,
- Cross-Band,
- RF-Port-zu-Port-Weiterleitung.

### `TX APRS-IS`

Sendet das Paket zu APRS-IS.

Verwende ihn fur:

- iGate-Uplink,
- Weiterleitung lokal erzeugten Anwendungsverkehrs zu APRS-IS.

Dieses Ziel ist systemseitig auf den verpflichtenden `Strict Filter` beschrankt.

### `Black Hole`

Protokolliert die Ausfuhrung, ohne das Paket weiterzuleiten.

Verwende ihn fur:

- Diagnose,
- Tests,
- Beobachtung des Filterverhaltens.

### `Action Drop`

Beendet die Regel durch absichtliches Verwerfen des Pakets.

Verwende ihn fur:

- explizite Sperrregeln,
- saubere Trennung zwischen akzeptierten und abgelehnten Pfaden.

## Einschränkungen des Editors

- Eine Regel hat immer genau eine Quelle und ein Ziel.
- `Local TX` darf nur zu `TX APRS-IS` oder `Black Hole` fuhren.
- `TX APRS-IS` behalt immer den verpflichtenden `Strict Filter`.
- `TX RF` erfordert einen aktiven `Path rule and DIGI guard`.
- `Duplicate Filter` darf nur einmal vorkommen.
- `Distance Filter` darf nur einmal vorkommen.
- `Rate Limit Filter` ist fur Flows gedacht, die mit `TX RF` enden.

## Gute Praxis

- Wähle zuerst Quelle und Ziel, danach die Filter.
- Bei `RF -> RF` sollte Kanalschutz vor Reichweite kommen.
- Bei `RF -> APRS-IS` sollte nur passender Verkehr auf die Internet-Seite gelangen.
- Starte Tests mit `Black Hole`, wenn du die Logik ohne Aussendung prufen willst.
- Nach dem Speichern hilft das Ausfuhrungsprotokoll dabei, genau zu sehen, an welchem Schritt ein Paket passiert oder abgelehnt wurde.
