# Ratenbegrenzungsfilter

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

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
