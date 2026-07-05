# APRS-Pfade in der Praxis

Diese Seite erklaert APRS-Pfade aus Sicht des Protokolls: wie eine Schreibweise wie `WIDE2-1` zu lesen ist, worin der Unterschied zwischen verfolgten und nicht verfolgten Pfaden besteht und wie einteilige und zweiteilige Pfade tatsaechlich abgearbeitet werden.

## 1. Was ein APRS-Pfad ist

Ein APRS-Pfad ist eine Liste von Hops oder Aliasen, die dem RF-Netz vorgibt, wie ein Frame weiter wiederholt werden darf.

Beispiele:

```text
WIDE2-1
SP2-2
WIDE1-1,WIDE2-1
SP1-1,SP2-2
WIDE2-1,RFONLY
```

Wichtige Regeln:

- die Pfadelemente werden durch Kommas getrennt,
- der Pfad wird von links nach rechts verarbeitet,
- das naechste Element wird erst angefasst, wenn das erste noch unverbrauchte Element bearbeitet wurde,
- `RFONLY` und `NOGATE` sind keine Wiederhol-Hops, sondern Markierungen, die das Gating zu APRS-IS einschraenken.

In der Praxis bedeutet lokale Aussendung ohne Digipeater einfach: kein Pfad. Viele Programme und Geraete verwenden auch die bequeme Bezeichnung `DIRECT`, aber auf Protokollebene bedeutet das nur Aussendung ohne Digi-Hops.

## 2. Wie man `N-N` liest

Bei Pfaden wie `WIDEn-N` oder `SPn-N` beschreibt die linke Zahl die Aliasfamilie und ihre anfaengliche Reichweite, waehrend die rechte Zahl als Zaehler fuer verbleibende Wiederholungen dient.

Beispiel:

```text
WIDE2-2
```

bedeutet, dass der Frame noch zwei Mal von aufeinanderfolgenden Digipeatern wiederholt werden darf. Nach der ersten Wiederholung wird der Zaehler reduziert:

```text
WIDE2-2 -> WIDE2-1
```

Nach der zweiten Wiederholung ist der Pfad verbraucht:

```text
WIDE2-1 -> WIDE2*
```

Das Sternchen `*` markiert ein Element, das bereits benutzt wurde und fuer weitere Wiederholungen nicht noch einmal verwendet werden soll.

Analog:

```text
SP2-2 -> SP2-1 -> SP2*
```

## 3. Verfolgte und nicht verfolgte Pfade

Der wichtigste Unterschied ist, ob der Digipeater sein eigenes Rufzeichen in den Pfad eintraegt.

### Verfolgter Pfad

Bei einem verfolgten Pfad hinterlaesst jeder Digipeater, der den Frame wiederholt, eine sichtbare Spur. Dadurch kann spaeter nachvollzogen werden, welchen Weg das Paket im RF genommen hat.

Beispiel:

```text
SP8XYZ-9>APRS,WIDE2-2:...
```

Nach dem ersten Digi:

```text
SP8XYZ-9>APRS,SR5AAA*,WIDE2-1:...
```

Nach dem zweiten Digi:

```text
SP8XYZ-9>APRS,SR5AAA*,SR5BBB*:...
```

Vorteile:

- der Weg des Pakets laesst sich leichter nachvollziehen,
- das Verhalten des Netzes ist leichter zu diagnostizieren.

Nachteil:

- der Frame wird mit jeder Wiederholung laenger, weil weitere Digi-Rufzeichen eingefuegt werden.

### Nicht verfolgter Pfad

Bei einem nicht verfolgten Pfad traegt der Digipeater sein eigenes Rufzeichen nicht ein. Er reduziert nur den Zaehler oder markiert das Element als verbraucht.

Beispiel:

```text
SP8XYZ-9>APRS,SP2-2:...
```

Nach dem ersten Digi:

```text
SP8XYZ-9>APRS,SP2-1:...
```

Nach dem zweiten Digi:

```text
SP8XYZ-9>APRS,SP2*:...
```

Vorteile:

- kuerzerer Frame,
- weniger Paketwachstum ueber mehrere Hops hinweg.

Nachteil:

- es ist nicht sichtbar, welche konkreten Digipeater den Frame weitergeleitet haben.

In der Praxis sind `WIDE`-Aliase meist verfolgt, waehrend nationale oder regionale Aliase wie `SP` oder `WM` manchmal als nicht verfolgt konfiguriert werden. Das ist keine magische Eigenschaft des Aliasworts selbst, sondern das Ergebnis der lokalen Digi-Netzkonfiguration.

## 4. Einteiliger Pfad

Ein einteiliger Pfad hat genau ein Element, aber das bedeutet nicht automatisch nur eine Wiederholung.

Beispiele:

```text
WIDE2-1
WIDE2-2
SP2-1
SP2-2
```

Interpretation:

- `WIDE2-1` ist ein Pfadelement und eine Wiederholung,
- `WIDE2-2` ist ein Pfadelement und zwei Wiederholungen,
- `SP2-1` ist ein Pfadelement und eine Wiederholung,
- `SP2-2` ist ein Pfadelement und zwei Wiederholungen.

Das ist eine haeufige Falle: die Anzahl der Pfadelemente ist nicht dasselbe wie die Anzahl der Wiederholungen.

Verfolgtes einteiliges Beispiel:

```text
WIDE2-2
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Nicht verfolgtes einteiliges Beispiel:

```text
SP2-2
-> SP2-1
-> SP2*
```

## 5. Zweiteiliger Pfad

Ein zweiteiliger Pfad hat zwei durch Komma getrennte Elemente und wird immer von links nach rechts verarbeitet.

Beispiel:

```text
WIDE1-1,WIDE2-1
```

Zuerst muss das erste Element verbraucht werden:

```text
WIDE1-1,WIDE2-1
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Hier lohnt sich ein wichtiger praktischer Hinweis: ein erstes Element wie `WIDE1-1` oder `SP1-1` hat meist die besondere Rolle eines Abschnitts fuer Hilfs-Digis, also fuer `fill-in digi`.

Ein solches Digi sollte grundsaetzlich nur dieses erste Element verbrauchen und den restlichen Pfad nicht weiter wiederholen. Bei einer Handfunk- oder Mobilstation ist `WIDE1-1` im Wesentlichen genau dafuer da, dass nahe Heimstationen oder andere lokale Hilfs-Digis aus einem lokalen Funkloch heraushelfen koennen, aber nach der Bearbeitung von `WIDE1-1` aufhoeren.

Weiteres Beispiel:

```text
SP1-1,SP2-2
```

Abarbeitung:

```text
SP1-1,SP2-2
-> SP1*,SP2-2
-> SP1*,SP2-1
-> SP1*,SP2*
```

Wichtige Schlussfolgerungen:

- `WIDE1-1,WIDE2-1` sind zwei Pfadelemente und insgesamt zwei Wiederholungen,
- `WIDE1-1,WIDE2-2` sind zwei Pfadelemente, aber insgesamt drei Wiederholungen,
- `SP1-1,SP2-2` sind ebenfalls zwei Pfadelemente und insgesamt drei Wiederholungen.
- ein erstes Element wie `WIDE1-1` oder `SP1-1` ist meist als Hilfsabschnitt fuer ein Digi sinnvoll, das nach genau diesem einen Hop aufhoert.

Ein verfolgter zweiteiliger Pfad waechst schneller als ein nicht verfolgter Pfad, weil jeder Hop ein weiteres Digi-Rufzeichen hinzufuegen kann.

## 6. `RFONLY` und `NOGATE`

Am Ende eines Pfads koennen zusaetzliche Markierungen auftauchen:

```text
WIDE2-1,RFONLY
WIDE1-1,WIDE2-1,NOGATE
```

In der Praxis haben sie einen aehnlichen Zweck: sie blockieren das Gating von RF-Verkehr zu APRS-IS.

Diese Elemente:

- fuegen keine Wiederhol-Hops hinzu,
- vergroessern die RF-Reichweite nicht,
- begrenzen nur den Uebergang des Verkehrs zur Internet-Seite.

## 7. Praktische Schlussfolgerungen

- kein Pfad bedeutet lokale Aussendung ohne Digi-Wiederholungen,
- ein einteiliger Pfad reicht oft aus, wenn nicht viele Wiederholungen noetig sind,
- ein zweiteiliger Pfad bringt mehr Reichweite, erhoeht aber schnell die Zahl der Kopien auf dem Kanal,
- verfolgte Pfade sind besser fuer die Diagnose,
- nicht verfolgte Pfade halten den Frame meist kuerzer,
- Kombinationen mit `WIDE1-1` am Anfang sind nur sinnvoll, wenn sie zur lokalen Praxis und zur lokalen Netztopologie passen,
- am besten haelt man sich immer an die Empfehlungen der eigenen Region, weil das lokale Digi-Netz entscheidet, welche Aliase tatsaechlich funktionieren und wie sie verarbeitet werden.
