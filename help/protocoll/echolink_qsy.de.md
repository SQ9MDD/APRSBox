# EchoLink-Objekte in APRS

Der Zweck solcher Objekte besteht darin, lokale Funkressourcen auf eine Weise anzuzeigen, die für mobile Operatoren lesbar und möglichst kompatibel mit der Praxis von APRS Frequency Objects ist. Das Objekt soll bei der Beantwortung einfacher Fragen helfen:

- wo sich die Ressource befindet,
- auf welcher Frequenz es arbeitet,
- welche Zugriffsparameter es benötigt,
- welchen Status oder welche Kurzbeschreibung es hat.

Objekte dieses Typs sollten eine lokale Bedeutung haben. Sie sollten nicht weit über den Bereich hinaus übertragen werden, in dem die Ressource tatsächlich nützlich ist.

## 1. Wann sollte ein solches Objekt verwendet werden?

Ein EchoLink-Objekt dient dazu, einen lokalen EchoLink-Knoten und die zugehörige Nutzfrequenz zu beschreiben. Für mobile Operatoren sind in der Regel vor allem folgende Punkte wichtig:

- die EchoLink-Knotennummer,
- die Betriebsfrequenz,
- den Ton CTCSS oder DCS, falls erforderlich,
- der Knotenstatus,
- das Rufzeichen oder eine kurze Beschreibung.

## 2. Beispielobjektrahmen

Schematisches Beispiel:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
```

In der Praxis sollten Koordinaten und Beschreibung durch eigene Daten ersetzt werden.

Der Frame besteht aus mehreren Teilen:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- callsign or short description
|        | |      |        | |        | |          |    +------- Knoten status
|        | |      |        | |        | |          +------------ tone / access
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- longitude
|        | |      |        +---------------------------------- EchoLink symbol table
|        | |      +------------------------------------------- latitude
|        | +-------------------------------------------------- timestamp
|        +---------------------------------------------------- object name
+------------------------------------------------------------- frame type: object
```

## 3. Objektname

Für EchoLink-Objekte wird der folgende Name empfohlen:

```text
EL-123456
```

Dabei ist `123456` die Nummer des EchoLink-Knotens.

Das ist wichtig, weil ein mobiler Operator oft die Knotennummer selbst benötigt und nicht nur das Rufzeichen der Station. Durch Einfügen der Nummer in den Objektnamen wird diese in der Sender- oder Objektliste eines APRS-Radios sichtbar.

Beispiele:

```text
EL-123456
EL-045678
EL-987654
```

## 4. Aktiv-/Inaktiv-Flag und Zeit

Für ein aktives Objekt verwenden Sie:

```text
*
```

Für ein festes Objekt wird häufig der folgende Zeitstempel verwendet:

```text
111111z
```

Beispiel:

```text
;EL-123456*111111z
```

## 5. Koordinaten und Symbol

Im EchoLink-Format werden die Symboltabelle `E` und das Symbol `0` verwendet:

```text
5215.00NE02055.00E0
```

Aufschlüsselung:

```text
5215.00N   latitude
E          EchoLink symbol table
02055.00E  longitude
0          symbol
```

Einige Beispiele verwenden absichtlich reduzierte Positionsgenauigkeit. Wenn Sie den genauen Standort des Knotens nicht anzeigen möchten, verwenden Sie eine ungefähre Position, die für einen lokalen Benutzer noch aussagekräftig ist.

## 6. Frequenz

Die Frequenz ist im Kommentar angegeben:

```text
438.700MHz
```

Empfohlenes Format:

```text
xxx.xxxMHz
```

Beispiele:

```text
145.550MHz
438.700MHz
439.000MHz
```

## 7. Ton, DCS und Zugriff

Nach der Frequenz können Sie den Ton CTCSS, DCS oder die Information angeben, dass kein Ton verwendet wird.

Beispiele:

```text
T103    CTCSS tone 103 Hz
C127    CTCSS 127 Hz, tone access and tone transmit
D023    DCS 023
Toff    no tone
```

## 8. Knotenstatus

EchoLink-Objekte können einen kurzen Status enthalten. Es sollte sehr kurz sein, idealerweise 4 Zeichen.

Beispiele:

```text
IDLE    idle
BUSY    busy
CONF    conference
OFF_    unavailable
```

Wenn der Status unbekannt ist, ist es besser, eine kurze Beschreibung zu verwenden oder dieses Feld wegzulassen, anstatt einen langen Text zu schreiben.

## 9. Empfohlene Feldreihenfolge

Zur besseren Lesbarkeit lohnt es sich, die Reihenfolge einzuhalten:

```text
frequency tone/DCS status callsign-or-description
```

Beispiel:

```text
438.700MHz T103 IDLE SR5ABC
```

Weitere Beispiele:

```text
145.550MHz T088 IDLE SR9XYZ
439.000MHz D023 BUSY EchoLink
438.700MHz Toff OFF_ SR5ABC
```

## 10. Gute Praktiken

- Geben Sie die Nummer Knoten als `EL-xxxxxx` in den Objektnamen ein.
- Geben Sie im Kommentar die Frequenz im Format `xxx.xxxMHz` an.
- Fügen Sie Ton oder DCS hinzu, falls für den Zugriff erforderlich.
- Der Status sollte kurz sein, idealerweise 4 Zeichen.
- Beschreiben Sie nicht die vollständige EchoLink-Konfiguration im Kommentar. Der Rahmen sollte im Radio lesbar bleiben.
- Das Objekt sollte lokal übertragen werden, wo der Knoten tatsächlich sinnvoll ist.

## 11. Kurzreferenz

```text
;             start of object
EL-123456     object name with EchoLink Knoten number
*             active object
111111z       fixed timestamp
E             EchoLink symbol table
0             EchoLink symbol
438.700MHz    frequency
T103          CTCSS tone 103 Hz
D023          DCS 023
IDLE          example status
SR5ABC        callsign or short description
```
