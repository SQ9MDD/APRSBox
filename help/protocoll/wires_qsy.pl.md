# Obiekty WiRES / WiRES-X w APRS

Ten dokument jest plikiem pomocy dla użytkownika tworzącego obiekty częstotliwościowe APRS.

Celem takich obiektów jest pokazanie lokalnych zasobów radiowych w sposób czytelny dla operatorów mobilnych oraz możliwie zgodny z praktyką APRS Frequency Objects. Obiekt powinien pomagać odpowiedzieć na proste pytania:

- gdzie znajduje się zasób,
- na jakiej częstotliwości pracuje,
- jakich parametrów dostępowych wymaga,
- jaki jest jego status lub krótki opis.

Obiekty tego typu powinny mieć znaczenie lokalne. Nie należy nadawać ich daleko poza obszar, w którym dany zasób jest realnie użyteczny.

## 1. Kiedy używać takiego obiektu

Obiekt WiRES lub WiRES-X służy do opisania lokalnego węzła albo przemiennika związanego z siecią Yaesu WiRES / WiRES-X. Taki obiekt może być przydatny dla operatora mobilnego, który widzi na radiu APRS informację o lokalnym zasobie i może szybko przejść na właściwą częstotliwość.

Typowe zastosowania:

- lokalny przemiennik z dostępem do WiRES-X,
- lokalny węzeł WiRES,
- informacja o częstotliwości, DCS/CTCSS, shifcie i zasięgu,
- krótki opis lub znak przemiennika.

## 2. Przykładowa ramka obiektu

Przykład praktyczny:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
```

Ramka składa się z kilku części:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- znak lub krótki opis
|        | |      |        | |        | |          |    |    +------- zasięg
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- DCS / SQL / ton
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- długość geograficzna
|        | |      |        +--------------------------------------- tabela symboli
|        | |      +------------------------------------------------ szerokość geograficzna
|        | +------------------------------------------------------- znacznik czasu
|        +--------------------------------------------------------- nazwa obiektu
+------------------------------------------------------------------ typ ramki: obiekt
```

## 3. Nazwa obiektu

Dla obiektów WiRES zalecana jest nazwa zaczynająca się od:

```text
WIR-
```

Przykłady:

```text
WIR-17967
WIR-1101D
```

Nazwa ma pokazać numer lub identyfikator węzła WiRES, ponieważ to właśnie ten numer jest ważny dla operatora, który widzi obiekt na liście stacji.

W obiekcie WiRES-X powiązanym z przemiennikiem warto trzymać nazwę w formie `WIR-xxxxx`, a częstotliwość, shift i parametry dostępu podać w komentarzu.

## 4. Znak aktywności i czas

Po nazwie obiektu występuje znak aktywności:

```text
*
```

Znaczenie:

```text
*  - obiekt aktywny
_  - obiekt usunięty lub nieaktywny
```

Dla obiektu stałego często stosuje się znacznik:

```text
111111z
```

Przykład:

```text
;WIR-17967*111111z
```

## 5. Koordynaty i symbol

W przykładzie użyto klasycznego symbolu przemiennika:

```text
5356.33N/02150.80Er
```

Rozbicie:

```text
5356.33N   szerokość geograficzna
/          tabela symboli
02150.80E  długość geograficzna
r          symbol przemiennika
```

W specyfikacji APRS Frequency Objects dla WiRES spotyka się także zapis z tabelą symboli `W` i symbolem `0`, przeznaczony do oznaczania węzła WiRES. W praktyce, jeśli obiekt opisuje przemiennik z WiRES-X, symbol przemiennika `r` bywa czytelniejszy dla użytkownika.

## 6. Częstotliwość

Częstotliwość podaje się w komentarzu:

```text
438.525MHz
```

Zalecany format:

```text
xxx.xxxMHz
```

Przykłady:

```text
438.525MHz
439.000MHz
145.600MHz
```

## 7. DCS, CTCSS, SQL i dostęp

W przykładzie:

```text
DOFF
```

oznacza informację dotyczącą DCS lub squelcha. W obiektach WiRES / WiRES-X można spotkać różne praktyki lokalne, dlatego najważniejsze jest, aby zapis był krótki i jednoznaczny dla operatorów w danym regionie.

Przykłady pól dostępu:

```text
D023    DCS 023
D754    DCS 754
DOFF    DCS wyłączony lub brak DCS, zgodnie z lokalną praktyką opisu
T103    ton CTCSS 103 Hz
C127    CTCSS 127 Hz, przemiennik otwierany tonem i wysyłający ton
```

## 8. Shift

Shift podaje się jako przesunięcie bez przecinka:

```text
-760
```

Znaczenie:

```text
-760  - shift -7,6 MHz
-060  - shift -600 kHz
+760  - shift +7,6 MHz
+060  - shift +600 kHz
```

## 9. Zasięg

Zasięg można podać jako:

```text
Rxxk
Rxxm
```

Przykłady:

```text
R99k  - zasięg około 99 km
R25k  - zasięg około 25 km
R15m  - zasięg około 15 mil
```

## 10. Zalecana kolejność pól

Dla czytelności warto trzymać stałą kolejność:

```text
częstotliwość DCS/CTCSS shift zasięg opis
```

Przykład:

```text
438.525MHz DOFF -760 R99k SR4MIT
```

Inne przykłady:

```text
438.525MHz D023 -760 R50k Wires node
439.000MHz T103 -760 R30k Local Wires
145.600MHz C127 -060 R25k WIRES-X
```

## 11. Dobre praktyki

- Używaj nazwy `WIR-xxxxx`, jeśli znasz numer węzła.
- W komentarzu podaj częstotliwość w formacie `xxx.xxxMHz`.
- Dodaj shift, jeśli zasób pracuje przez przemiennik.
- Dodaj DCS, CTCSS lub krótką informację o dostępie, jeśli jest potrzebna.
- Dodaj zasięg tylko wtedy, gdy masz sensowną wartość orientacyjną.
- Komentarz końcowy powinien być krótki, na przykład znak przemiennika albo lokalna nazwa.

## 12. Krótka ściąga

```text
;             początek obiektu
WIR-17967     nazwa obiektu z numerem węzła WiRES
*             obiekt aktywny
111111z       stały znacznik czasu
r             symbol przemiennika, praktyczny dla obiektu przemiennikowego
438.525MHz    częstotliwość
D023          DCS 023
DOFF          brak DCS lub DCS wyłączony, według lokalnej praktyki
T103          ton CTCSS 103 Hz
-760          shift -7,6 MHz
R99k          zasięg około 99 km
SR4MIT        znak lub krótki opis
```
