# IRLP-Objekte in APRS

Der Zweck solcher Objekte besteht darin, lokale Funkressourcen auf eine Weise anzuzeigen, die für mobile Operatoren lesbar und möglichst kompatibel mit der Praxis von APRS Frequency Objects ist. Das Objekt soll bei der Beantwortung einfacher Fragen helfen:

- wo sich die Ressource befindet,
- auf welcher Frequenz es arbeitet,
- welche Zugriffsparameter es benötigt,
- welchen Status oder welche Kurzbeschreibung es hat.

Objekte dieses Typs sollten eine lokale Bedeutung haben. Sie sollten nicht weit über den Bereich hinaus übertragen werden, in dem die Ressource tatsächlich nützlich ist.

## 1. Wann sollte ein solches Objekt verwendet werden?

Ein IRLP-Objekt dient dazu, einen lokalen IRLP-Knoten und die zugehörige Nutzfrequenz zu beschreiben. Für mobile Operatoren sind vor allem folgende Punkte wichtig:

- die IRLP-Knotennummer,
- die Betriebsfrequenz,
- der CTCSS-Ton, DCS oder andere Zugangsinformationen,
- der Knotenstatus,
- das Rufzeichen oder eine kurze Beschreibung.

## 2. Beispielobjektrahmen

Schematisches Beispiel:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
```

Der Frame besteht aus mehreren Teilen:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- callsign or description
|        | |      |        | |        | |          |    |    +------- status
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- tone / access
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- IRLP symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 3. Objektname

Für IRLP-Objekte werden die folgenden Namen empfohlen:

```text
IRLP-1234
IRLP12345
```

Die erste Form ist typisch für vierstellige Knotennummern. Die zweite kann verwendet werden, wenn die Nummer fünf Ziffern hat.

Beispiele:

```text
IRLP-1234
IRLP-5678
IRLP12345
```

Die Knotennummer sollte im Objektnamen sichtbar sein, da ein mobiler Operator sie zum Nutzen des Links benötigt.

## 4. Aktiv-/Inaktiv-Flag und Zeit

Für ein aktives Objekt verwenden Sie:

```text
*
```

Für ein festes Objekt wird häufig Folgendes verwendet:

```text
111111z
```

Beispiel:

```text
;IRLP-1234*111111z
```

## 5. Koordinaten und Symbol

Im IRLP-Format werden die Symboltabelle `I` und das Symbol `0` verwendet:

```text
5215.00NI02055.00E0
```

Aufschlüsselung:

```text
5215.00N   latitude
I          IRLP symbol table
02055.00E  longitude
0          symbol
```

Sollte der genaue Standort nicht veröffentlicht werden, kann eine ungefähre Position verwendet werden, solange sie noch zum lokalen Versorgungsbereich des Knotens passt.

## 6. Frequenz

Die Frequenz ist im Kommentar angegeben:

```text
438.700MHz
```

Empfohlenes Format:

```text
xxx.xxxMHz
```

## 7. Ton, DCS und Shift

Nach der Frequenz können Ton, DCS und Shift angegeben werden.

Beispiele:

```text
T103       CTCSS tone 103 Hz
C127       CTCSS 127 Hz, tone access and tone transmit
D023       DCS 023
-760       shift -7.6 MHz
-060       shift -600 kHz
+760       shift +7.6 MHz
```

## 8. Knotenstatus

Der Status sollte kurz und lesbar sein.

Beispiele:

```text
IDLE    idle
BUSY    busy
OFF_    unavailable
```

## 9. Empfohlene Feldreihenfolge

Zur besseren Lesbarkeit lohnt es sich, die Reihenfolge einzuhalten:

```text
frequency tone/DCS shift status callsign-or-description
```

Beispiel:

```text
438.700MHz T103 -760 IDLE SR5ABC
```

Weitere Beispiele:

```text
145.575MHz T088 -060 IDLE IRLP
439.000MHz D023 -760 BUSY SR9XYZ
438.700MHz Toff -760 OFF_ Local
```

## 10. Gute Praktiken

- Übernehmen Sie die Nummer des IRLP-Knotens in den Objektnamen.
- Geben Sie im Kommentar die Frequenz im Format `xxx.xxxMHz` an.
- Ergänzen Sie bei Bedarf Ton, DCS oder Shift, um den Knoten nutzen zu können.
- Der Status sollte kurz sein.
- Verwenden Sie keine lange Beschreibung. Ein mobiler Operator sollte die wichtigsten Daten ohne Scrollen erfassen können.
- Das Objekt sollte lokal ausgesendet werden, in dem Bereich, in dem der Knoten tatsächlich nützlich ist.

## 11. Kurzreferenz

```text
;             start of object
IRLP-1234     object name with IRLP Knoten number
IRLP12345     variant for a five-Ziffern-number
*             active object
111111z       fixed timestamp
I             IRLP symbol table
0             IRLP symbol
438.700MHz    frequency
T103          CTCSS tone 103 Hz
D023          DCS 023
-760          shift -7.6 MHz
IDLE          example status
SR5ABC        callsign or short description
```
