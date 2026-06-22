# Obiekty EchoLink w APRS

Celem takich obiektów jest pokazanie lokalnych zasobów radiowych w sposób czytelny dla operatorów mobilnych oraz możliwie zgodny z praktyką APRS Frequency Objects. Obiekt powinien pomagać odpowiedzieć na proste pytania:

- gdzie znajduje się zasób,
- na jakiej częstotliwości pracuje,
- jakich parametrów dostępowych wymaga,
- jaki jest jego status lub krótki opis.

Obiekty tego typu powinny mieć znaczenie lokalne. Nie należy nadawać ich daleko poza obszar, w którym dany zasób jest realnie użyteczny.

## 1. Kiedy używać takiego obiektu

Obiekt EchoLink służy do opisania lokalnego węzła EchoLink oraz częstotliwości, na której można z niego skorzystać. Dla operatora mobilnego najważniejsze są zwykle:

- numer węzła EchoLink,
- częstotliwość pracy,
- ton CTCSS lub DCS, jeśli jest wymagany,
- status węzła,
- znak lub krótki opis.

## 2. Przykładowa ramka obiektu

Przykład schematyczny:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
```

W praktyce współrzędne i opis należy zastąpić własnymi danymi.

Ramka składa się z kilku części:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- znak lub krótki opis
|        | |      |        | |        | |          |    +------- status węzła
|        | |      |        | |        | |          +------------ ton / dostęp
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- długość geograficzna
|        | |      |        +---------------------------------- tabela symboli EchoLink
|        | |      +------------------------------------------- szerokość geograficzna
|        | +-------------------------------------------------- znacznik czasu
|        +---------------------------------------------------- nazwa obiektu
+------------------------------------------------------------- typ ramki: obiekt
```

## 3. Nazwa obiektu

Dla obiektów EchoLink zalecana jest nazwa:

```text
EL-123456
```

gdzie `123456` oznacza numer węzła EchoLink.

To ważne, ponieważ operator mobilny często potrzebuje właśnie numeru węzła, a nie tylko znaku stacji. Umieszczenie numeru w nazwie obiektu sprawia, że jest on widoczny na liście stacji lub obiektów w radiu APRS.

Przykłady:

```text
EL-123456
EL-045678
EL-987654
```

## 4. Znak aktywności i czas

Dla aktywnego obiektu używa się znaku:

```text
*
```

Dla obiektu stałego często używa się znacznika:

```text
111111z
```

Przykład:

```text
;EL-123456*111111z
```

## 5. Koordynaty i symbol

W formacie EchoLink stosuje się tabelę symboli `E` oraz symbol `0`:

```text
5215.00NE02055.00E0
```

Rozbicie:

```text
5215.00N   szerokość geograficzna
E          tabela symboli EchoLink
02055.00E  długość geograficzna
0          symbol
```

W niektórych przykładach spotyka się pozycję z celowo zmniejszoną dokładnością. Jeśli nie chcesz pokazywać dokładnej lokalizacji węzła, użyj położenia przybliżonego, ale nadal sensownego dla lokalnego użytkownika.

## 6. Częstotliwość

Częstotliwość podaje się w komentarzu:

```text
438.700MHz
```

Zalecany format:

```text
xxx.xxxMHz
```

Przykłady:

```text
145.550MHz
438.700MHz
439.000MHz
```

## 7. Ton, DCS i dostęp

Po częstotliwości można podać ton CTCSS, DCS albo informację o braku tonu.

Przykłady:

```text
T103    ton CTCSS 103 Hz
C127    CTCSS 127 Hz, otwieranie i wysyłanie tonu
D023    DCS 023
Toff    brak tonu
```

## 8. Status węzła

W obiektach EchoLink można dodać krótki status. Powinien być bardzo krótki, najlepiej 4 znaki.

Przykłady:

```text
IDLE    wolny
BUSY    zajęty
CONF    konferencja
OFF_    niedostępny
```

Jeśli status nie jest znany, lepiej użyć krótkiego opisu lub pominąć to pole, zamiast wpisywać długi tekst.

## 9. Zalecana kolejność pól

Dla czytelności warto trzymać kolejność:

```text
częstotliwość ton/DCS status znak-lub-opis
```

Przykład:

```text
438.700MHz T103 IDLE SR5ABC
```

Inne przykłady:

```text
145.550MHz T088 IDLE SR9XYZ
439.000MHz D023 BUSY EchoLink
438.700MHz Toff OFF_ SR5ABC
```

## 10. Dobre praktyki

- W nazwie obiektu umieść numer węzła jako `EL-xxxxxx`.
- W komentarzu podaj częstotliwość w formacie `xxx.xxxMHz`.
- Dodaj ton lub DCS, jeśli jest wymagany do dostępu.
- Status powinien być krótki, najlepiej 4 znaki.
- Nie opisuj całej konfiguracji EchoLink w komentarzu. Ramka ma być czytelna na radiu.
- Obiekt powinien być nadawany lokalnie, tam gdzie węzeł jest rzeczywiście użyteczny.

## 11. Krótka ściąga

```text
;             początek obiektu
EL-123456     nazwa obiektu z numerem węzła EchoLink
*             obiekt aktywny
111111z       stały znacznik czasu
E             tabela symboli EchoLink
0             symbol EchoLink
438.700MHz    częstotliwość
T103          ton CTCSS 103 Hz
D023          DCS 023
IDLE          przykładowy status
SR5ABC        znak lub krótki opis
```
