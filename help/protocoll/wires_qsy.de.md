# WiRES / WiRES-X Objekte in APRS

Der Zweck solcher Objekte besteht darin, lokale Funkressourcen auf eine Weise anzuzeigen, die für mobile Operatoren lesbar und möglichst kompatibel mit der Praxis von APRS Frequency Objects ist. Das Objekt soll bei der Beantwortung einfacher Fragen helfen:

- wo sich die Ressource befindet,
- auf welcher Frequenz es arbeitet,
- welche Zugriffsparameter es benötigt,
- welchen Status oder welche Kurzbeschreibung es hat.

Objekte dieses Typs sollten eine lokale Bedeutung haben. Sie sollten nicht weit über den Bereich hinaus übertragen werden, in dem die Ressource tatsächlich nützlich ist.

## 1. Wann sollte ein solches Objekt verwendet werden?

Ein WiRES- oder WiRES-X-Objekt dient dazu, einen lokalen Knoten oder Repeater im Yaesu-WiRES-/WiRES-X-Netz zu beschreiben. Solch ein Objekt kann für mobile Operatoren nützlich sein, die APRS-Informationen zu einer lokalen Ressource im Radio sehen und schnell auf die richtige Frequenz umschalten möchten.

Typische Anwendungen:

- ein lokaler Repeater mit WiRES-X-Zugriff,
- ein lokaler WiRES-Knoten,
- Informationen über Frequenz, DCS/CTCSS, Shift und Reichweite,
- eine kurze Beschreibung oder ein Repeater-Rufzeichen.

## 2. Beispielobjektrahmen

Praxisbeispiel:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
```

Der Frame besteht aus mehreren Teilen:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- callsign or short description
|        | |      |        | |        | |          |    |    +------- range
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- DCS / SQL / tone
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 3. Objektname

Für WiRES-Objekte ein Name, der beginnt mit:

```text
WIR-
```

wird empfohlen.

Beispiele:

```text
WIR-17967
WIR-1101D
```

Der Name sollte die Nummer oder Kennung des WiRES-Knotens enthalten, da diese Nummer für den Bediener wichtig ist, der das Objekt in der Stationsliste sieht.

Für ein WiRES-X-Objekt, das mit einem Repeater verknüpft ist, lohnt es sich, den Namen in der Form `WIR-xxxxx` beizubehalten und die Frequenzs-, Shifts- und Zugriffsparameter in den Kommentar einzufügen.

## 4. Aktiv-/Inaktiv-Flag und Zeit

Nach dem Objektnamen kommt das Alive/Dead-Flag:

```text
*
```

Bedeutung:

```text
*  - active object
_  - deleted or inactive object
```

Für ein festes Objekt wird häufig der folgende Zeitstempel verwendet:

```text
111111z
```

Beispiel:

```text
;WIR-17967*111111z
```

## 5. Koordinaten und Symbol

Das Beispiel verwendet das klassische Repeater-Symbol:

```text
5356.33N/02150.80Er
```

Aufschlüsselung:

```text
5356.33N   latitude
/          symbol table
02150.80E  longitude
r          Repeater symbol
```

In der Praxis von APRS Frequency Objects für WiRES sehen Sie möglicherweise auch die Symboltabelle `W` und das Symbol `0`, die zum Markieren eines WiRES Knoten vorgesehen sind. Wenn das Objekt in der Praxis ein Repeater mit WiRES-X beschreibt, ist das Repeater-Symbol `r` für den Benutzer möglicherweise klarer.

## 6. Frequenz

Die Frequenz ist im Kommentar angegeben:

```text
438.525MHz
```

Empfohlenes Format:

```text
xxx.xxxMHz
```

Beispiele:

```text
438.525MHz
439.000MHz
145.600MHz
```

## 7. DCS, CTCSS, SQL und Zugriff

Im Beispiel:

```text
DOFF
```

bedeutet Informationen im Zusammenhang mit DCS oder Squelch. In WiRES / WiRES-X-Objekten können unterschiedliche lokale Praktiken vorhanden sein. Das Wichtigste ist daher, dass die Notation für Operatoren in der Region kurz und eindeutig ist.

Beispiele für Zugriffsfelder:

```text
D023    DCS 023
D754    DCS 754
DOFF    DCS disabled or no DCS, according to local description practice
T103    CTCSS tone 103 Hz
C127    CTCSS 127 Hz, Repeater opened by tone and transmitting tone
```

## 8. Shift

Shift wird als Offset ohne Dezimaltrennzeichen geschrieben:

```text
-760
```

Bedeutung:

```text
-760  - shift -7.6 MHz
-060  - shift -600 kHz
+760  - shift +7.6 MHz
+060  - shift +600 kHz
```

## 9. Reichweite

Der Bereich kann wie folgt angegeben werden:

```text
Rxxk
Rxxm
```

Beispiele:

```text
R99k  - range about 99 km
R25k  - range about 25 km
R15m  - range about 15 miles
```

## 10. Empfohlene Feldreihenfolge

Zur besseren Lesbarkeit lohnt es sich, eine feste Reihenfolge einzuhalten:

```text
frequency DCS/CTCSS shift range description
```

Beispiel:

```text
438.525MHz DOFF -760 R99k SR4MIT
```

Weitere Beispiele:

```text
438.525MHz D023 -760 R50k Wires Knoten
439.000MHz T103 -760 R30k Local Wires
145.600MHz C127 -060 R25k WIRES-X
```

## 11. Gute Praktiken

- Verwenden Sie den Namen `WIR-xxxxx`, wenn Ihnen die Knotennummer bekannt ist.
- Geben Sie im Kommentar die Frequenz im Format `xxx.xxxMHz` an.
- Fügen Sie eine Shift hinzu, wenn die Ressource über ein Repeater funktioniert.
- Fügen Sie bei Bedarf DCS, CTCSS oder eine kurze Zugriffsnotiz hinzu.
- Fügen Sie den Bereich nur hinzu, wenn Sie einen sinnvollen Näherungswert haben.
- Der letzte Kommentar sollte kurz sein, zum Beispiel ein Repeater-Rufzeichen oder ein lokaler Name.

## 12. Kurzreferenz

```text
;             start of object
WIR-17967     object name with WiRES Knoten number
*             active object
111111z       fixed timestamp
r             Repeater symbol, practical for a Repeater object
438.525MHz    frequency
D023          DCS 023
DOFF          no DCS or DCS disabled, according to local practice
T103          CTCSS tone 103 Hz
-760          shift -7.6 MHz
R99k          range about 99 km
SR4MIT        callsign or short description
```
