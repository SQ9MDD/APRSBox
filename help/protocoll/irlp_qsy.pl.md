# Obiekty IRLP w APRS

Ten dokument jest plikiem pomocy dla użytkownika tworzącego obiekty częstotliwościowe APRS.

Celem takich obiektów jest pokazanie lokalnych zasobów radiowych w sposób czytelny dla operatorów mobilnych oraz możliwie zgodny z praktyką APRS Frequency Objects. Obiekt powinien pomagać odpowiedzieć na proste pytania:

- gdzie znajduje się zasób,
- na jakiej częstotliwości pracuje,
- jakich parametrów dostępowych wymaga,
- jaki jest jego status lub krótki opis.

Obiekty tego typu powinny mieć znaczenie lokalne. Nie należy nadawać ich daleko poza obszar, w którym dany zasób jest realnie użyteczny.

## 1. Kiedy używać takiego obiektu

Obiekt IRLP służy do opisania lokalnego węzła IRLP oraz częstotliwości, na której operator może z niego skorzystać. Dla użytkownika mobilnego najważniejsze są:

- numer węzła IRLP,
- częstotliwość pracy,
- ton CTCSS, DCS lub inna informacja o dostępie,
- status węzła,
- znak lub krótki opis.

## 2. Przykładowa ramka obiektu

Przykład schematyczny:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
```

Ramka składa się z kilku części:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- znak lub opis
|        | |      |        | |        | |          |    |    +------- status
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- ton / dostęp
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- długość geograficzna
|        | |      |        +--------------------------------------- tabela symboli IRLP
|        | |      +------------------------------------------------ szerokość geograficzna
|        | +------------------------------------------------------- znacznik czasu
|        +--------------------------------------------------------- nazwa obiektu
+------------------------------------------------------------------ typ ramki: obiekt
```

## 3. Nazwa obiektu

Dla obiektów IRLP zalecane są nazwy:

```text
IRLP-1234
IRLP12345
```

Pierwszy wariant jest typowy dla czterocyfrowych numerów węzłów. Drugi może być użyty, jeśli numer ma pięć cyfr.

Przykłady:

```text
IRLP-1234
IRLP-5678
IRLP12345
```

Numer węzła powinien być widoczny w nazwie obiektu, ponieważ operator mobilny potrzebuje go do skorzystania z linku.

## 4. Znak aktywności i czas

Dla aktywnego obiektu używa się:

```text
*
```

Dla obiektu stałego często stosuje się:

```text
111111z
```

Przykład:

```text
;IRLP-1234*111111z
```

## 5. Koordynaty i symbol

W formacie IRLP stosuje się tabelę symboli `I` oraz symbol `0`:

```text
5215.00NI02055.00E0
```

Rozbicie:

```text
5215.00N   szerokość geograficzna
I          tabela symboli IRLP
02055.00E  długość geograficzna
0          symbol
```

Jeśli dokładna lokalizacja nie powinna być publikowana, można użyć położenia przybliżonego, ale nadal związanego z lokalnym obszarem pracy węzła.

## 6. Częstotliwość

Częstotliwość podaje się w komentarzu:

```text
438.700MHz
```

Zalecany format:

```text
xxx.xxxMHz
```

## 7. Ton, DCS i shift

Po częstotliwości można podać ton, DCS i shift.

Przykłady:

```text
T103       ton CTCSS 103 Hz
C127       CTCSS 127 Hz, otwieranie i wysyłanie tonu
D023       DCS 023
-760       shift -7,6 MHz
-060       shift -600 kHz
+760       shift +7,6 MHz
```

## 8. Status węzła

Status powinien być krótki i czytelny.

Przykłady:

```text
IDLE    wolny
BUSY    zajęty
OFF_    niedostępny
```

## 9. Zalecana kolejność pól

Dla czytelności warto trzymać kolejność:

```text
częstotliwość ton/DCS shift status znak-lub-opis
```

Przykład:

```text
438.700MHz T103 -760 IDLE SR5ABC
```

Inne przykłady:

```text
145.575MHz T088 -060 IDLE IRLP
439.000MHz D023 -760 BUSY SR9XYZ
438.700MHz Toff -760 OFF_ Local
```

## 10. Dobre praktyki

- W nazwie obiektu umieść numer węzła IRLP.
- W komentarzu podaj częstotliwość w formacie `xxx.xxxMHz`.
- Dodaj ton, DCS lub shift, jeśli są potrzebne do użycia węzła.
- Status powinien być krótki.
- Nie używaj długiego opisu. Operator mobilny powinien odczytać najważniejsze dane bez przewijania.
- Obiekt powinien być nadawany lokalnie, w obszarze, gdzie węzeł jest faktycznie użyteczny.

## 11. Krótka ściąga

```text
;             początek obiektu
IRLP-1234     nazwa obiektu z numerem węzła IRLP
IRLP12345     wariant dla pięciocyfrowego numeru
*             obiekt aktywny
111111z       stały znacznik czasu
I             tabela symboli IRLP
0             symbol IRLP
438.700MHz    częstotliwość
T103          ton CTCSS 103 Hz
D023          DCS 023
-760          shift -7,6 MHz
IDLE          przykładowy status
SR5ABC        znak lub krótki opis
```
