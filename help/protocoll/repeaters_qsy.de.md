# Repeater-Objekte in APRS

Dieses Dokument beschreibt ein praktisches Format für ein Repeater-Objekt in APRS. Es dient als Hilfedatei für Benutzer, die Frequency Objects erstellen, insbesondere für FM-Repeater.

Ziel ist es, einen Frame vorzubereiten, der für Operatoren gut lesbar ist, mit der Praxis von APRS Frequency Objects übereinstimmt und von mobilen APRS-Funkgeräten so gut wie möglich unterstützt wird.

## 1. Beispielobjektrahmen

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Der Frame besteht aus mehreren logischen Teilen:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- comment, callsign, or description
|        | |      |        | |        | |          |    |    +------- Repeater range
|        | |      |        | |        | |          |    +------------ Repeater shift
|        | |      |        | |        | |          +----------------- CTCSS tone and FM width
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- longitude
|        | |      |        +--------------------------------------- symbol table
|        | |      +------------------------------------------------ latitude
|        | +------------------------------------------------------- timestamp
|        +--------------------------------------------------------- object name
+------------------------------------------------------------------ frame type: object
```

## 2. Frame-Typ: Objekt

Ein APRS-Objekt beginnt mit einem Semikolon:

```text
;
```

Nach dem Semikolon kommt der Objektname:

```text
;438.462WX
```

Im Beispiel enthält der Objektname die Frequenz und ein lokales Suffix:

```text
438.462WX
```

Wo:

```text
438.462  - Repeater frequency shown as the object name
WX       - local suffix, in Poland often a county code
```

## 3. Objektname: Frequenz und lokales Suffix

Für Repeater-Objekte wird empfohlen, dass der Objektname mit der Frequenz beginnt:

```text
438.462WX
145.600WA
145.775KR
```

Diese Notation ist beabsichtigt. In APRS-Repeater- und Frequency-Objects verbessert das Einfügen der Frequenz in den Objektnamen die Lesbarkeit auf mobilen APRS-Funkgeräten. Das Radio zeigt den Objektnamen in der Stationsliste an, sodass der Bediener sofort die Repeater-Frequenz sehen kann, ohne die Objektdetails öffnen zu müssen.

Die Frequenz sollte auch im Objektkommentar wiederholt werden, zum Beispiel:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Das erste Vorkommen der Frequenz im Objektnamen dient hauptsächlich der Lesbarkeit in der Objektliste. Das zweite Vorkommen im Kommentar ist Teil der Frequenzinformationen und kann von Radios oder Anwendungen für QSY/TUNE-Funktionen oder zur Darstellung von Repeater-Parametern verwendet werden.

Die Frequenz im Namen und die Frequenz im Kommentar sollten nicht als falsches Duplikat behandelt werden. Es handelt sich um einen bewussten Kompromiss aus Kompatibilität und praktischem Nutzen von Frequency Objects.

## 4. Eindeutigkeit des Objektnamens

Der Objektname APRS hat eine begrenzte Länge, daher lautet die Notation:

```text
frequency + local suffix
```

ist ein Kompromiss zwischen Lesbarkeit und Einzigartigkeit.

Beispiel:

```text
438.462WX
```

bezeichnet ein Objekt für die Frequenz `438.462 MHz` mit dem lokalen Suffix `WX`.

In Polen wird als Suffix häufig ein Landkreis-Kürzel verwendet. Dies hilft bei der Unterscheidung von Repeater-Objekten, die an verschiedenen Standorten auf derselben Frequenz arbeiten.

Bedenken Sie jedoch bei permanenten Objekten, dass das Objekt in das gesamte APRS-IS-Netzwerk gelangen kann. Ein lokales Suffix wie ein Kreiscode verringert das Risiko lokaler Kollisionen, garantiert jedoch nicht vollständig die globale Eindeutigkeit.

Praktische Regel:

```text
recommended scheme:
    frequency + local suffix
    example: 438.462WX

recommendation:
    the object name should start with the frequency

warning:
    for permanent objects sent to APRS-IS, check
    whether the name is as globally unique as possible
```

Wenn der Repeater ein bekanntes Rufzeichen, einen bekannten Namen oder eine bekannte Kennung hat, kann diese Information in den abschließenden Kommentar aufgenommen werden, statt die Frequenz aus dem Objektnamen zu entfernen.

## 5. Aktiv-/Inaktiv-Flag

Nach dem Objektnamen kommt das Alive/Dead-Flag:

```text
*
```

Beispiel:

```text
;438.462WX*
```

Bedeutung:

```text
*  - active object
_  - deleted or inactive object
```

Für ein normal funktionierendes Repeater verwenden Sie `*`.

## 6. Zeitstempel

Das Beispiel verwendet:

```text
111111z
```

Vollständiges Fragment:

```text
;438.462WX*111111z
```

Der Zeitstempel `111111z` wird häufig als fester Zeitstempel für permanente Objekte verwendet.

Praktische Regel:

```text
fixed or permanent object:
    111111z

temporary object:
    current UTC time generated on each transmission
```

Bei einem festen Objekt ist die korrekte regelmäßige Aktualisierung des Objekts wichtiger als die Angabe des genauen Zeitpunkts seiner Generierung.

## 7. Koordinaten und Symbol

Beispielposition:

```text
5218.54N/02113.09Er
```

Aufschlüsselung:

```text
5218.54N   latitude
/          symbol table
02113.09E  longitude
r          symbol
```

Für das Repeater-Objekt im Beispiel wird das Symbol `r` verwendet.

## 8. Repeater-Frequenz im Kommentar

Geben Sie nach der Position die Betriebsfrequenz von Repeater an:

```text
438.462MHz
```

Empfohlenes Format:

```text
xxx.xxxMHz
```

Beispiele:

```text
145.600MHz
438.462MHz
439.000MHz
```

Die Frequenz im Kommentar sollte mit der Frequenz im Objektnamen übereinstimmen.

Richtiges Beispiel:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Verdächtiges Beispiel:

```text
;438.462WX*111111z5218.54N/02113.09Er439.000MHz C127 -760 R10k SR5WWL
```

Im zweiten Beispiel schlägt der Objektname `438.462 MHz` vor, der Kommentar gibt jedoch `439.000 MHz` an. Eine solche Notation kann den Betreiber irreführen.

## 9. CTCSS, Ton und FM width

Im Beispiel:

```text
C127
```

Dies bedeutet Informationen über den CTCSS-Ton und den Repeater-Modus.

Bedeutung der Buchstaben:

```text
t and c  - narrow FM
T and C  - wide FM

t and T  - Repeater opens with tone
c and C  - Repeater opens with tone and transmits tone
```

Beispielinterpretation:

```text
T127  - wide FM, Repeater opens with 127 Hz tone
C127  - wide FM, Repeater opens with 127 Hz tone and transmits tone
t127  - narrow FM, Repeater opens with 127 Hz tone
c127  - narrow FM, Repeater opens with 127 Hz tone and transmits tone
```

Es lohnt sich, ein Drei-digit-Format beizubehalten, wenn der Ton weniger als drei Ziffern hat:

```text
T088
c088
```

## 10. Repeater-Shift

Im Beispiel:

```text
-760
```

Es bedeutet Shift `-7.6 MHz`.

Notationsregel:

```text
-760  -> shift -7.6 MHz
-060  -> shift -600 kHz
+760  -> shift +7.6 MHz
+060  -> shift +600 kHz
```

Der Wert wird also als Offset ohne Dezimaltrennzeichen geschrieben.

Beispiele:

```text
145.600MHz -060
438.462MHz -760
439.000MHz +760
```

## 11. Repeater-Bereich: Rxxk / Rxxm

Für Repeater-Objekte kann der Bereich wie folgt angegeben werden:

```text
Rxxk
Rxxm
```

Bedeutung:

```text
R10k  - range about 10 km
R25k  - range about 25 km
R15m  - range about 15 miles
```

Im Beispiel:

```text
R10k
```

Die angegebene Reichweite von Repeater beträgt also etwa 10 km.

Für Repeater-Objekte wird die Notation `Rxxk` oder `Rxxm` bevorzugt. Sie sollte nicht mit der klassischen Erweiterung `RNGxxxx` verwechselt werden, bei der es sich um einen anderen Mechanismus zur Beschreibung der Funkabdeckung handelt.

## 12. Kommentar, Rufzeichen oder Beschreibung

Am Ende können Sie ein Rufzeichen, einen Repeater-Namen oder eine kurze Beschreibung einfügen:

```text
SR5WWL
```

Vollständiges Endfragment:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Der Kommentar sollte kurz sein. Ein APRS-Frame ist kein guter Ort für lange Beschreibungen, Website-Adressen oder Informationen aus mehreren Sätzen.

## 13. Empfohlene Feldreihenfolge im Kommentar

Aus Gründen der Lesbarkeit und Kompatibilität lohnt es sich, eine feste Reihenfolge einzuhalten:

```text
frequency mode/CTCSS shift range comment
```

Beispiel:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Weitere Beispiele:

```text
145.600MHz T103 -060 R25k SR9ABC
439.000MHz C123 +760 R30k Local
145.775MHz c088 -060 R15k SR5YYY
```

## 14. Empfohlene Formular- oder Generatorfelder

Beim Erstellen eines Repeater-Objekts ist ein einfacher Generator hilfreich, der den Objektnamen und den Kommentar aus separaten Feldern aufbaut.

Vorgeschlagene Felder:

```text
Object name:
    438.462WX

Object name mode:
    frequency + local suffix
    custom name

Local suffix:
    WX

Frequency:
    438.462

CTCSS tone:
    127

Tone mode:
    opens with tone
    opens with tone and transmits tone

FM width:
    narrow FM
    wide FM

Shift:
    -7.6 MHz
    -0.6 MHz
    +0.6 MHz
    +7.6 MHz
    custom

Range:
    10

Range unit:
    km
    miles

Comment:
    SR5WWL
```

Ergebnis:

```text
object name:
    438.462WX

comment:
    438.462MHz C127 -760 R10k SR5WWL
```

Der Generator soll dafür sorgen, dass die Frequenz sowohl im Objektnamen als auch im Kommentar sichtbar ist. Die Frequenz sollte nicht aus dem Namen entfernt werden, nur weil sie bereits im Kommentar erscheint.

Für ein permanentes Objekt, das an APRS-IS gesendet wird, lohnt es sich, eine Warnung anzuzeigen:

```text
Names of permanent objects should be as globally unique as possible.
The frequency + local suffix scheme is recommended for readability on APRS radios,
but it does not guarantee full uniqueness across the entire APRS-IS network.
```

## 15. Empfohlene Validierung

Empfohlene Validierungsregeln:

```text
object name:
    required
    recommended format for Repeater: frequency + local suffix
    example: 438.462WX
    warning if a permanent object is to be sent to APRS-IS
    and the name looks too generic or does not contain a suffix

frequency:
    required
    format xxx.xxx

consistency of name and comment:
    the frequency from the object name should match
    the frequency in the comment, if both are given

CTCSS:
    optional
    only popular CTCSS values or a 2-3 Ziffern-number

tone mode:
    t / T / c / C

shift:
    optional
    format +xxx or -xxx

range:
    optional
    format Rxxk or Rxxm

comment:
    optional
    short text without overloading the frame
```

Die Validierung soll dem Benutzer helfen, anstatt alle ungewöhnlichen Fälle zu blockieren. Für einen informierten Benutzer lohnt es sich, die Möglichkeit der manuellen Korrektur beizubehalten.

## 16. Beispiele für vorgefertigte Objekte

### UHF Repeater, Wide FM, CTCSS, Shift -7,6 MHz

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

### VHF Repeater, Wide FM, Ton am Eingang, Shift -600 kHz

```text
;145.600WA*111111z5215.00N/02055.00Er145.600MHz T103 -060 R25k SR5XXX
```

### VHF Repeater, Narrow FM, Ton am Ein- und Ausgang

```text
;145.775KR*111111z5215.00N/02055.00Er145.775MHz c088 -060 R15k SR5YYY
```

## 17. So lesen Sie die Objektdetails

Aus dem Beispielrahmen:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Sie können lesen:

```text
Object name: 438.462WX
Frequency from name: 438.462 MHz
Local suffix: WX
Position: 52°18.54'N, 21°13.09'E
Symbol: r
Frequency: 438.462 MHz
CTCSS: 127 Hz
FM width: wide
Tone mode: opens with tone and transmits tone
Shift: -7.6 MHz
Range: 10 km
Description: SR5WWL
```

## 18. Kurzreferenz

```text
;             start of object
438.462WX     object name: frequency + local suffix
*             active object
_             deleted or inactive object
111111z       fixed timestamp
/             symbol table
r             Repeater symbol
438.462MHz    frequency in comment
T127          wide FM, opens with 127 Hz tone
C127          wide FM, opens with 127 Hz tone and transmits tone
t127          narrow FM, opens with 127 Hz tone
c127          narrow FM, opens with 127 Hz tone and transmits tone
-760          shift -7.6 MHz
-060          shift -600 kHz
R10k          range 10 km
R15m          range 15 miles
```
