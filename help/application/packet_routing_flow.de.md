# Packet Flow - Detailreferenz

Diese Hilfedatei gehort zum Editor `Packet Flow`, der geoffnet wird, wenn du aus der Liste `Packet Routing` eine konkrete Regel auswahlst.

Sie beschreibt den detaillierten Aufbau der Regel, typische Anwendungsfalle, die Reihenfolge der Schritte, die Filterblocke, die Zielblocke und fertige Regelschemata.

## Was dieser Bildschirm macht

Eine Routing-Regel legt fest, was APRSBox mit einem Paket tun soll, nachdem es empfangen oder lokal erzeugt wurde.

Jede Regel hat:

- eine Quelle,
- null oder mehr Filter- oder Regelblocke in der Mitte,
- ein finales Ziel.

Pakete laufen immer von oben nach unten. Wenn ein Block das Paket ablehnt, werden die folgenden Schritte nicht mehr ausgefuhrt.

## Wie man eine Regel liest und aufbaut

Die einfachste Denkweise fur eine Regel ist:

1. Wo das Paket eintritt.
2. Welche Bedingungen es erfullen muss.
3. Wo es enden soll.

Empfohlene Reihenfolge:

1. Quelle auswahlen.
2. Ziel auswahlen.
3. Nur die wirklich benotigten Filter hinzufugen.
4. Regel speichern und das Ausfuhrungsprotokoll ansehen.

## Haufige Anwendungsfalle

### `Empfänger RF -> TX APRS-IS`

Das ist der klassische iGate-Pfad.

Minimale Form:

```text
Empfänger RF -> Strenger Filter -> TX APRS-IS
```

Verwende ihn, wenn:

- lokal gehorter RF-Verkehr an APRS-IS weitergeleitet werden soll,
- verschiedene RF-Ports unterschiedliche Uplink-Regeln haben sollen,
- RF-Eingang und lokal erzeugter Verkehr getrennt bleiben sollen.

Wichtige Hinweise:

- `Strenger Filter` ist verpflichtend,
- nicht jedes per RF empfangene Paket soll zu APRS-IS gehen,
- das ist ein Uplink-Pfad, kein Digi-Pfad.

### `Empfänger RF -> TX RF`

Das ist der klassische Digipeater-Pfad.

Minimale Form:

```text
Empfänger RF -> Pfadregel und DIGI-Schutz -> TX RF
```

Haufigere Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

Verwende ihn, wenn:

- APRS-Verkehr per RF wiederholt werden soll,
- du ein lokales Digi aufbaust,
- du Cross-Band oder RF-Port-zu-Port-Weiterleitung willst,
- nur ausgewahlte Verkehrsarten nach zusatzlichen Filtern weiterlaufen sollen.

Wichtige Hinweise:

- `Pfadregel und DIGI-Schutz` ist verpflichtend,
- `Duplikatfilter (viscous-delay)` ist oft ein sinnvoller erster Schritt,
- auf diesem Pfad ist Kanalschutz besonders wichtig.

### `Local TX -> TX APRS-IS`

Dieser Pfad ist fur Frames gedacht, die APRSBox selbst erzeugt.

Form:

```text
Local TX -> Strenger Filter -> TX APRS-IS
```

Verwende ihn, wenn:

- Beacons, Status, Wetter, Objekte, Bulletins oder Nachrichten zu APRS-IS gehen sollen,
- lokal erzeugter Anwendungsverkehr einen Internet-Uplink braucht.

Wichtige Hinweise:

- `Local TX` ist kein per RF empfangener Verkehr,
- es ist ein eigener interner Strom,
- `Strenger Filter` bleibt verpflichtend.

### `Empfänger RF -> Black Hole`

Das ist ein Test- und Diagnosepfad.

Formen:

```text
Empfänger RF -> Black Hole
```

oder:

```text
Empfänger RF -> Nur direkt -> Black Hole
```

Verwende ihn, wenn:

- du Filter ohne Weiterleitung testen willst,
- du einen bestimmten RF-Port beobachten willst,
- du eine Regel vor dem Aktivieren von TX RF oder TX APRS-IS pruefen willst.

### `Local TX -> Black Hole`

Das ist ein Diagnosepfad fur intern erzeugten Verkehr.

Verwende ihn, wenn:

- du sehen willst, was APRSBox selbst erzeugt,
- du Objekte, Status, Wetter oder Bulletins ohne Weiterleitung testen willst.

## Quellblocke

### `Empfänger RF`

Dies ist die Quelle fur Pakete, die vom gewahlten Funkmodem empfangen wurden.

Verwende sie, wenn:

- die Regel auf Verkehr aus der Luft reagieren soll,
- mehrere RF-Empfanger getrennte Routing-Logik brauchen.

In der Praxis:

- jede Regel `Empfänger RF -> ...` beginnt hier,
- das gewahlte Modem bestimmt, welcher Eingang uberhaupt in die Regel gelangen kann.

### `Local TX`

Dies ist die Quelle fur Frames, die APRSBox lokal selbst erzeugt.

Dazu gehoren:

- Beacons,
- Statuspakete,
- Wetter,
- Objekte,
- Items,
- Bulletins,
- Nachrichten.

Nicht dazu gehoren:

- per RF empfangener Verkehr,
- bereits digipeateter Verkehr,
- normaler Eingangsverkehr vom TNC.

In der Praxis:

- das ist der interne Sendestrom der Anwendung,
- `Local TX` darf nur zu `TX APRS-IS` oder `Black Hole` fuhren.

## Filter- und Regelblocke

### `Strenger Filter`

Dies ist der Systemsicherheitsblock fur Regeln, die in `TX APRS-IS` enden.

Er:

- lehnt Pakete mit `TCPIP` oder `TCPXX` ab,
- lehnt Pakete mit `NOGATE` oder `RFONLY` ab,
- validiert Third-Party-Frames,
- validiert den ausseren und inneren Pfad von Third-Party-Verkehr,
- halt unpassenden Verkehr von APRS-IS fern.

Verwende ihn:

- immer mit `TX APRS-IS`,
- niemals als Ersatz fur die Pfadlogik eines RF-Digis.

Typische Anwendungsfalle:

- `Empfänger RF -> Strenger Filter -> TX APRS-IS`,
- `Local TX -> Strenger Filter -> TX APRS-IS`.

### `Pfadregel und DIGI-Schutz`

Dies ist der wichtigste Block fur Flows, die in `TX RF` enden.

Er:

- analysiert den Digi-Pfad,
- entscheidet, ob die lokale Station das Paket noch wiederholen soll,
- blockiert lokal adressierte APRS-Nachrichten und Anfragen,
- blockiert Third-Party-Verkehr, der nicht wiederholt werden soll,
- blockiert Frames, die von derselben lokalen Station bereits wiederholt wurden.

Warum er verpflichtend ist:

- ohne diesen Block hat eine RF-Regel keinen grundlegenden Digi-Schutz,
- dieser Block stellt die zentrale Pfadlogik fur sicheres Wiederholen im Funk bereit.

Konfigurationsfelder:

- `Paths (TRACE / traced)`:
  Aliase oder explizite Hops, die verbraucht werden sollen und dabei das lokale Digi-Rufzeichen in den Pfad eintragen.
- `Paths (NO TRACE / not traced)`:
  Aliase oder explizite Hops, die verbraucht werden sollen, ohne das lokale Digi-Rufzeichen einzutragen.

In der Praxis:

- `WIDE1-1` wird oft als traced konfiguriert,
- die no-trace-Liste hangt von der lokalen Netzpolitik ab,
- dieser Block sitzt meist nahe am Ende der Kette, direkt vor `TX RF`.

Typische Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

### `Duplikatfilter (viscous-delay)`

Dieser Block offnet ein kurzes Horfenster, sobald der Frame in den Flow eintritt.

Er:

- wartet wahrend des konfigurierten Fensters,
- pruft, ob ein anderes Digi denselben Frame bereits wiederholt hat,
- verwirft den Frame bei erkannter Doppelwiederholung,
- lasst den Frame weiterlaufen, wenn keine Doppelwiederholung gehort wurde.

Wichtiges Verhalten:

- er darf nur einmal vorkommen,
- er sollte der erste Filter in einem RF-Wiederholpfad sein,
- er ist besonders nutzlich in klassischen Digi-Regeln.

Verwende ihn, wenn:

- doppelte Wiederholungen reduziert werden sollen,
- mehrere Digis dieselbe Quellstation horen konnen.

### `Nur direkt`

Dieser Filter lasst nur direkt gehorte Pakete durch.

Das bedeutet:

- der Pfad darf keinen bereits verbrauchten Digi-Hop enthalten,
- wenn der Pfad verbrauchte Elemente mit `*` enthalt, wird der Frame abgelehnt.

Verwende ihn, wenn:

- die Regel nur auf lokal direkt gehorte Stationen reagieren soll,
- bereits wiederholter Verkehr ignoriert werden soll,
- du die Direktabdeckung getrennt untersuchen willst.

### `DIGI-Filter`

Dieser Filter untersucht verbrauchte Digi-Hops im Pfad.

So arbeitet er:

- er vergleicht nur bereits verbrauchte Hops,
- Muster unterstutzen `*`,
- `allow` lasst nur passende Pakete durch,
- `deny` lehnt passende Pakete ab.

Beispiele:

- `SR5ABC`,
- `SR5*`,
- `*`.

Verwende ihn, wenn:

- nur Verkehr aus bestimmten Digi-Ketten passieren soll,
- Verkehr uber bestimmte Digis ausgeschlossen werden soll.

### `Rufzeichenfilter`

Dieser Filter vergleicht das Quellrufzeichen.

So arbeitet er:

- er arbeitet auf dem Quellrufzeichen des Pakets,
- er unterstutzt Wildcard `*`,
- `allow` funktioniert wie eine Allowlist,
- `deny` funktioniert wie eine Blocklist.

Beispiele:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Verwende ihn, wenn:

- Club-, Test-, Service- oder Operatorverkehr getrennt werden soll,
- eine bekannte Quelle blockiert oder isoliert werden soll.

### `Pakettypfilter`

Dieser Filter arbeitet auf APRS-Paketgruppen.

Erwartete Werte:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Praktische Bedeutung:

- `message` umfasst auch ACK/REJ, bulletin und announcement,
- `weather` bedeutet weather-only-Frames,
- eine Position mit Wetterdaten zahlt weiterhin als `position`.

Verwende ihn, wenn:

- Positionen, Objekte, Nachrichten oder Wetter getrennt geroutet werden sollen,
- eine Regel auf eine Verkehrsklasse begrenzt bleiben soll.

### `Symbolfilter`

Dieser Filter vergleicht das APRS-Symbol im Format `table+code`.

Beispiele:

- `/>`,
- `\\l`.

Verwende ihn, wenn:

- bestimmte Symbolklassen einen eigenen Pfad bekommen sollen,
- die Symbolbedeutung wichtiger ist als der Pakettyp.

### `Distanzfilter`

Dieser Filter lasst ein Paket nur durch, wenn seine decodierte Position in mindestens einer konfigurierten Zone liegt.

So arbeitet er:

- es konnen 1 bis 3 Zonen definiert werden,
- jede Zone hat Mittelpunkt und Radius,
- die Zonen arbeiten mit OR-Logik,
- Pakete ohne decodierbare Position werden nicht automatisch abgelehnt.

Verwende ihn, wenn:

- Verkehr auf ein geografisches Gebiet begrenzt werden soll,
- lokales Routing von Abdeckung oder Veranstaltungsgebiet abhangen soll.

### `Ratenbegrenzungsfilter`

Dieser Filter begrenzt, wie oft Pakete eines Rufzeichens oder Rufzeichenmusters weiterlaufen durfen.

Regelformat:

```text
CALL_OR_PATTERN - LIMIT
```

Beispiele:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
* - 20s
```

So arbeitet er:

- er misst die Zeit seit dem zuletzt durchgelassenen Frame pro passendem Muster,
- er blockiert den nachsten Frame, wenn er vor Ablauf des Limits ankommt.

Verwende ihn, wenn:

- sehr aktive Stationen zu viel Verkehr erzeugen,
- ein RF-Pfad sanfte Verkehrsbegrenzung ohne Komplettsperre braucht.

## Zielblocke

### `TX RF`

Dieses Ziel sendet das Paket uber das gewahlte Funkmodem.

Verwende es fur:

- lokale Digi-Pfade,
- Cross-Band,
- RF-Port-zu-Port-Weiterleitung.

Typische Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

### `TX APRS-IS`

Dieses Ziel sendet das Paket zu APRS-IS.

Verwende es fur:

- iGate-Uplink,
- lokal von APRSBox erzeugten Verkehr, der APRS-IS erreichen soll.

Wichtige Einschränkung:

- dieses Ziel behalt immer den verpflichtenden `Strengen Filter`.

### `Black Hole`

Dies ist ein Diagnoseziel. Das Paket endet dort und wird nicht weitergeleitet.

Verwende es fur:

- Tests,
- Verkehrsbeobachtung,
- Validierung von Filtern vor dem Aktivieren der Aussendung.

## Einschränkungen des Editors

- Eine Regel hat immer genau eine Quelle und ein Ziel.
- `Local TX` darf nur zu `TX APRS-IS` oder `Black Hole` fuhren.
- `TX APRS-IS` behalt immer den verpflichtenden `Strengen Filter`.
- `TX RF` erfordert eine aktive `Pfadregel und DIGI-Schutz`.
- `Duplikatfilter (viscous-delay)` darf nur einmal vorkommen.
- `Distanzfilter` darf nur einmal vorkommen.
- `Ratenbegrenzungsfilter` ist fur Flows gedacht, die mit `TX RF` enden.

## Fertige Regelskizzen

### Einfaches RF-iGate

```text
Empfänger RF -> Strenger Filter -> TX APRS-IS
```

### Klassisches RF-Digi

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

### Digi nur fur direkt gehorte Stationen

```text
Empfänger RF -> Nur direkt -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

### Lokal erzeugter Verkehr zu APRS-IS

```text
Local TX -> Strenger Filter -> TX APRS-IS
```

### Diagnose ohne Weiterleitung

```text
Empfänger RF -> Black Hole
```

## Gute Praxis

- Wähle zuerst Quelle und Ziel, danach die Bedingungen.
- Bei `TX RF` sollte Kanalschutz vor Reichweite kommen.
- Bei `TX APRS-IS` sollte nur passender Verkehr auf die Internet-Seite gelangen.
- Fur Tests beginne mit `Black Hole`.
- Nach dem Speichern zeigt das Ausfuhrungsprotokoll genau, welcher Schritt ein Paket durchgelassen oder abgelehnt hat.
