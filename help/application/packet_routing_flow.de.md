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

Fur Frames aus `Empfänger RF`:

- er pruft den kompletten ausseren Pfad,
- er lehnt den Frame ab, wenn der Pfad `TCPIP`, `TCPXX`, `NOGATE` oder `RFONLY` enthalt,
- er validiert Third-Party-Kapselung,
- bei gueltigen Third-Party-Frames pruft er auch den inneren Pfad auf dieselben gesperrten Tokens.

Fur `Local TX` ist er strenger:

- der Frame muss in Metadaten als lokal von APRSBox erzeugt markiert sein,
- Third-Party-Kapselung wird abgelehnt,
- jede `q..`-Konstruktion im Pfad wird abgelehnt,
- `TCPIP`, `TCPXX`, `NOGATE` und `RFONLY` bleiben gesperrt.

Wichtige Hinweise:

- bei `TX APRS-IS` ist dieser Filter verpflichtend,
- er ersetzt keine RF-Digi-Pfadlogik,
- wenn TNC2-Parsing fehlschlaegt, wird der Frame abgelehnt.

Typische Anwendungsfalle:

- `Empfänger RF -> Strenger Filter -> TX APRS-IS`,
- `Local TX -> Strenger Filter -> TX APRS-IS`.

### `Pfadregel und DIGI-Schutz`

Dies ist der zentrale Block fur Flows, die in `TX RF` enden. Er fuehrt zuerst den DIGI-Schutz aus und danach die Pfad-Umschreibung.

Der Schutzteil lehnt ab:

- Third-Party-Frames,
- APRS-Nachrichten an lokale `My station`,
- APRS-Queries an lokale `My station`,
- APRS-Nachrichten an lokale `WX station`,
- APRS-Queries an lokale `WX station`,
- Frames, in denen die lokale Station bereits als verbrauchter Hop vorkommt, zum Beispiel `MYCALL-SSID*`.

Erst danach wird der Pfad bearbeitet:

- ist der Pfad leer, wird der Frame abgelehnt,
- sind alle Hops bereits verbraucht, wird der Frame abgelehnt,
- nur der erste noch nicht verbrauchte Hop wird gepruft,
- spaetere Hops bleiben unberuehrt, bis dieser erste Hop behandelt ist.

Konfigurationsfelder:

- `Paths (TRACE / traced)`:
  Wenn der erste unverbrauchte Hop zu dieser Liste passt, verbraucht APRSBox ihn und fuegt das lokale Digi-Rufzeichen aus `My settings` ein.
- `Paths (NO TRACE / not traced)`:
  Wenn der erste unverbrauchte Hop zu dieser Liste passt, wird der Hop nur als verbraucht markiert, ohne das lokale Digi-Rufzeichen einzutragen.

Was eingetragen werden kann:

- ein voller Hop wie `WIDE1-1`, `WIDE2-1`, `WIDE2-2` oder `SP2-2`,
- ein Familienalias wie `WIDE`; dann passen Mitglieder wie `WIDE1-1` und `WIDE2-2`.

Typische Umschreibungen:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `WIDE2-2` -> `WIDE2-2*,WIDE2-1`,
- NO TRACE `SP2-2` -> `SP2-2*,SP2-1`,
- wenn der Hop nicht im Format `N-N` ist, fuegt NO TRACE nur `*` hinzu.

Typische Starteintraege:

- `TRACE`: `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: das eigene `CALLSIGN-SSID` aus `My settings` plus lokale Ausnahmen gemaess Netzpolitik.

Warum das eigene Rufzeichen oft in `NO TRACE` steht:

- um Pakete zu verbrauchen, die direkt an das eigene Rufzeichen adressiert sind, ohne es erneut in den Pfad einzutragen,
- um explizite lokale Hops ohne TRACE-Spur zu behandeln.

Wichtige Hinweise:

- wenn TRACE passt, aber das lokale Rufzeichen nicht konfiguriert ist, wird der Frame abgelehnt,
- wenn der erste unverbrauchte Hop weder zu TRACE noch zu NO TRACE passt, wird der Frame abgelehnt.

Typische Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

### `Duplikatfilter (viscous-delay)`

Dieser Block laesst den Frame nicht sofort durch. Der erste Frame mit einem bestimmten Fingerprint wird bis zum Ende des Horfensters zurueckgehalten.

Tatsaechliches Verhalten:

- der Fingerprint besteht aus `source callsign + info field`,
- der Pfad spielt beim Duplikatvergleich keine Rolle,
- der erste Frame wartet bis zum Ende des Fensters,
- erscheint waehrenddessen ein zweiter Frame mit demselben Fingerprint, werden beide verworfen,
- erscheint kein Duplikat, laeuft der erste Frame erst nach Ablauf des Timers weiter.

Praktische Folgen:

- zwei Frames derselben Station mit identischer Nutzlast, aber unterschiedlichem Pfad, zaehlen trotzdem als Duplikat,
- dies ist echtes viscous-delay: erst warten, dann entscheiden,
- er darf nur einmal vorkommen und sollte der erste Filter eines RF-Wiederholpfads sein.

Verwende ihn, wenn:

- mehrere Digis dieselbe Quellstation horen koennen,
- unnoetige Wiederholungen ohne sofortiges TX reduziert werden sollen.

### `Nur direkt`

Dieser Filter laesst nur direkt gehoerte Pakete durch.

Tatsaechliches Verhalten:

- er prueft nur, ob der Pfad bereits einen verbrauchten Hop mit `*` enthaelt,
- unverbrauchte Hops wie `WIDE1-1` stoeren ihn nicht,
- `...,WIDE1-1:` passiert,
- `...,SR5ABC*,WIDE1-1:` wird abgelehnt.

Verwende ihn, wenn:

- die Regel nur auf direkt gehoerte Stationen reagieren soll,
- bereits wiederholter Verkehr ignoriert werden soll,
- du Direktabdeckung getrennt untersuchen willst.

### `DIGI-Filter`

Dieser Filter betrachtet nicht den gesamten Pfad und nicht die noch unverbrauchten Hops. Er untersucht nur Hops, die bereits mit `*` markiert sind, nachdem dieses Zeichen entfernt wurde.

Tatsaechliches Verhalten:

- aus `SR5BCD-2*,WIDE1-1` sieht er nur `SR5BCD-2`,
- aus `WIDE1-1` sieht er nichts, weil noch kein Hop verbraucht wurde,
- Muster werden gegen verbrauchte Hops gepruft; `*` darf an beliebiger Stelle stehen,
- `allow` laesst nur durch, wenn mindestens ein verbrauchter Hop passt,
- `deny` lehnt nur ab, wenn mindestens ein verbrauchter Hop passt.

Praktische Folgen:

- eine leere `allow`-Liste lehnt alles ab,
- eine leere `deny`-Liste laesst alles durch,
- `*` in `deny` blockiert jeden bereits digipeateten Frame,
- `*` in `deny` blockiert keine echten Direct-Frames, weil es dort keinen verbrauchten Hop zum Pruefen gibt.

Beispiele:

- Pfad `SR5BCD-2*,WIDE1-1` plus Muster `SR5BCD*` -> Treffer,
- Pfad `SR5ABC*,WIDE1-1` plus `deny: *` -> Drop,
- Pfad `WIDE1-1` plus `deny: *` -> Pass.

Verwende ihn, wenn:

- nur Verkehr ueber ausgewaehlte Digis passieren soll,
- bereits von bestimmten Zwischenstationen wiederholter Verkehr ausgeschlossen werden soll.

### `Rufzeichenfilter`

Dieser Filter prueft nur das Quellrufzeichen. Pfad, Digi-Hops und Ziel spielen keine Rolle.

So arbeitet er:

- ohne `*` ist der Treffer exakt,
- `SQ9MDD` passt nicht zu `SQ9MDD-4`,
- `*` darf an beliebiger Stelle stehen,
- `allow` arbeitet wie eine Allowlist,
- `deny` arbeitet wie eine Blocklist.

Praktische Folgen:

- eine leere `allow`-Liste lehnt alles ab,
- eine leere `deny`-Liste laesst alles durch.

Beispiele:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Verwende ihn, wenn:

- Club-, Test-, Service- oder Operatorverkehr getrennt werden soll,
- eine bekannte Quelle blockiert oder isoliert werden soll.

### `Pakettypfilter`

Dieser Filter arbeitet auf dem, was der APRSBox-Decoder als APRS-Gruppe oder APRS-Typ erkannt hat.

Uebliche Selektoren:

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
- `weather` bedeutet nur weather-only-Frames,
- eine Position mit Wetterdaten bleibt `position`,
- zur Rueckwaertskompatibilitaet funktionieren auch alte Selektoren wie `M`, `S`, `O` und `W` sowie rohe Typcodes des Parsers.

So arbeitet er:

- im Modus `allow` passiert der Frame nur, wenn erkannte Gruppe oder Typ zur Liste passt,
- im Modus `deny` faellt der Frame nur, wenn erkannte Gruppe oder Typ zur Liste passt,
- wenn der Decoder Gruppe/Typ nicht bestimmen kann, lehnt `allow` ab und `deny` laesst durch.

Verwende ihn, wenn:

- Positionen, Objekte, Nachrichten oder Wetter getrennt geroutet werden sollen,
- eine Regel auf eine Verkehrsklasse begrenzt bleiben soll.

### `Symbolfilter`

Dieser Filter vergleicht das APRS-Symbol exakt im Format `table+code`.

So arbeitet er:

- der Vergleich ist exakt und verwendet keinen Wildcard,
- er vergleicht genau den Symbolwert, den der APRSBox-Parser geliefert hat,
- im Modus `allow` bedeutet kein Treffer Ablehnung,
- im Modus `deny` bedeutet kein Treffer Durchlass,
- wenn das Symbol nicht decodiert werden kann, lehnt `allow` ab und `deny` laesst durch.

Beispiele:

- `/>`,
- `\\l`.

Verwende ihn, wenn:

- bestimmte Symbolklassen einen eigenen Pfad bekommen sollen,
- die Symbolbedeutung wichtiger ist als der Pakettyp.

### `Distanzfilter`

Dieser Filter laesst einen Frame nur durch, wenn die decodierte Position in mindestens einer konfigurierten Zone liegt.

So arbeitet er:

- es koennen 1 bis 3 Zonen definiert werden,
- jede Zone hat Mittelpunkt und Radius,
- die Zonen arbeiten mit OR-Logik,
- wenn keine gueltige Zone vorhanden ist, wird der Filter uebersprungen,
- wenn der Frame keine decodierbare Position hat, wird der Filter uebersprungen,
- nur ein Frame mit Position ausserhalb aller Zonen wird abgelehnt.

Verwende ihn, wenn:

- Verkehr auf ein geografisches Gebiet begrenzt werden soll,
- lokales Routing von Abdeckung oder Veranstaltungsgebiet abhaengen soll.

### `Ratenbegrenzungsfilter`

Dieser Filter zaehlt nicht Pakete pro Minute. Er ist eine einfache Zeitbremse auf Basis des Quellrufzeichens.

Regelformat:

```text
CALL_OR_PATTERN - LIMIT
```

Beispiele:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

So arbeitet er:

- er arbeitet nur auf dem Quellrufzeichen,
- der erste passende Frame geht immer durch,
- der naechste Frame derselben Quelle unter derselben passenden Regel wird bis zum Ablauf des Limits blockiert,
- der Zeitstempel wird nur bei Frames aktualisiert, die wirklich durchgelassen wurden,
- passt keine Regel zur Quelle, blockiert der Filter nichts.

Wie Muster gepruft werden:

- `SQ9MDD-7` ohne Wildcard passt nur zu genau diesem SSID,
- `SQ9MDD` ohne Wildcard und ohne SSID passt zu diesem Rufzeichen mit jedem SSID,
- `SQ*` arbeitet als Wildcard,
- wenn mehrere Regeln passen, waehlt runtime die spezifischste; bei Gleichstand gewinnt die fruehere Zeile.

Formatgrenzen:

- `LIMIT` kann als `30`, `30s` oder `30S` geschrieben werden,
- erlaubt sind 5 bis 300 Sekunden,
- der Schritt betraegt 5 Sekunden.

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
