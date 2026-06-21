# Winlink-Objekte in APRS

Der Zweck solcher Objekte besteht darin, lokale Funkressourcen auf eine Weise anzuzeigen, die für mobile Operatoren lesbar und möglichst kompatibel mit der Praxis von APRS Frequency Objects ist. Das Objekt soll bei der Beantwortung einfacher Fragen helfen:

- wo sich die Ressource befindet,
- auf welcher Frequenz es arbeitet,
- welche Zugriffsparameter es benötigt,
- welchen Status oder welche Kurzbeschreibung es hat.

Objekte dieses Typs sollten eine lokale Bedeutung haben. Sie sollten nicht weit über den Bereich hinaus übertragen werden, in dem die Ressource tatsächlich nützlich ist.

## 1. Wann sollte ein solches Objekt verwendet werden?

Ein Winlink-Objekt dient dazu, einen lokalen Funkzugangspunkt zu Winlink zu beschreiben, zum Beispiel ein Packet-Gateway. Es ist kein typisches Sprach-Repeater-Objekt. Sein Zweck besteht darin, dem Bediener zu zeigen, wo sich die lokale Winlink-Ressource befindet und welche Parameter verwendet werden können, um eine Verbindung zu ihr herzustellen.

Die wichtigsten Informationen:

- das Rufzeichen oder die Kennung des Gateways,
- die Betriebsfrequenz,
- die Packet-Geschwindigkeit,
- eventuelle Offset- oder lokale Notizen,
- ein kurzer Kommentar.

## 2. Beispielobjektrahmen

Schematisches Beispiel:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
```

Der Frame besteht aus mehreren Teilen:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- short description
|        | |      |        | |        | |          |    +------- offset / additional information
|        | |      |        | |        | |          +------------ Packet-Geschwindigkeit
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- longitude
|        | |      |        +---------------------------------- Winlink symbol table
|        | |      +------------------------------------------- latitude
|        | +-------------------------------------------------- timestamp
|        +---------------------------------------------------- object name
+------------------------------------------------------------- frame type: object
```

## 3. Objektname

Für Winlink-Objekte werden folgende Namen verwendet:

```text
WL-CALL
W1-CALL
W2-CALL
...
W9-CALL
```

Beispiele:

```text
WL-SR5ABC
W1-SR5ABC
W2-SP9XYZ
```

`WL-` bezeichnet das Basisobjekt Winlink. Die Varianten `W1-` bis `W9-` können verwendet werden, wenn mehrere Objekte mit demselben Rufzeichen oder Standort verknüpft sind.

Der Name sollte kurz und lesbar sein, da er in der Objektliste angezeigt wird.

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
;WL-SR5ABC*111111z
```

## 5. Koordinaten und Symbol

Im Winlink-Format werden die Symboltabelle `W` und das Symbol `a` verwendet:

```text
5215.00NW02055.00Ea
```

Aufschlüsselung:

```text
5215.00N   latitude
W          Winlink symbol table
02055.00E  longitude
a          symbol
```

Wenn die genaue Position des Gateways nicht veröffentlicht werden soll, kann eine ungefähre Position innerhalb des Bereichs verwendet werden, in dem die Ressource nützlich ist.

## 6. Frequenz

Die Frequenz ist im Kommentar angegeben:

```text
144.950MHz
```

Empfohlenes Format:

```text
xxx.xxxMHz
```

Beispiele:

```text
144.950MHz
145.050MHz
430.525MHz
```

## 7. Packet-Geschwindigkeit

In einem Winlink-Objekt wird stattdessen die Stelle, an der Sprach-Repeater normalerweise Toninformationen tragen, für die Geschwindigkeit packet verwendet.

Beispiele:

```text
1200
9600
```

Beispielkommentar:

```text
144.950MHz 1200 -000 Winlink
```

## 8. Offset und Kommentar

Nach der Geschwindigkeit können Sie einen Versatz oder eine kurze Zusatznote hinzufügen.

Beispiele:

```text
-000    no offset, simplex
+060    offset +600 kHz
-060    offset -600 kHz
```

Der letzte Kommentar sollte kurz sein:

```text
Winlink
RMS
Packet
SR5ABC
```

## 9. Empfohlene Feldreihenfolge

Zur besseren Lesbarkeit lohnt es sich, die Reihenfolge einzuhalten:

```text
frequency speed offset/description short-comment
```

Beispiel:

```text
144.950MHz 1200 -000 Winlink
```

Weitere Beispiele:

```text
145.050MHz 1200 -000 RMS
430.525MHz 9600 -000 Winlink
144.950MHz 1200 Packet SR5ABC
```

## 10. Gute Praktiken

- Denken Sie daran, dass Winlink eine Packet-/Datenressource und kein Sprach-Repeater ist.
- Verwenden Sie im Namen `WL-` oder `W1-` bis `W9-` und ein Rufzeichen oder eine Kurzkennung.
- Geben Sie im Kommentar die Frequenz im Format `xxx.xxxMHz` an.
- Geben Sie die Geschwindigkeit packet an, zum Beispiel `1200` oder `9600`.
- Setzen Sie nicht den Ton CTCSS anstelle der Geschwindigkeit packet ein, wenn das Objekt einen typischen Punkt Winlink packet beschreibt.
- Die abschließende Beschreibung sollte kurz sein.

## 11. Kurzreferenz

```text
;             start of object
WL-SR5ABC     basic Winlink object name
W1-SR5ABC     additional variant
*             active object
111111z       fixed timestamp
W             Winlink symbol table
a             Winlink symbol
144.950MHz    frequency
1200          Packet-Geschwindigkeit
9600          Packet-Geschwindigkeit
-000          simplex / no offset
Winlink       short description
```
