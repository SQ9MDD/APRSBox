# Obiekty Winlink w APRS

Ten dokument jest plikiem pomocy dla użytkownika tworzącego obiekty częstotliwościowe APRS.

Celem takich obiektów jest pokazanie lokalnych zasobów radiowych w sposób czytelny dla operatorów mobilnych oraz możliwie zgodny z praktyką APRS Frequency Objects. Obiekt powinien pomagać odpowiedzieć na proste pytania:

- gdzie znajduje się zasób,
- na jakiej częstotliwości pracuje,
- jakich parametrów dostępowych wymaga,
- jaki jest jego status lub krótki opis.

Obiekty tego typu powinny mieć znaczenie lokalne. Nie należy nadawać ich daleko poza obszar, w którym dany zasób jest realnie użyteczny.

## 1. Kiedy używać takiego obiektu

Obiekt Winlink służy do opisania lokalnego radiowego punktu dostępu do Winlink, na przykład bramki packet. Nie jest to typowy obiekt przemiennika głosowego. Jego celem jest pokazanie operatorowi, gdzie znajduje się lokalny zasób Winlink i jakimi parametrami można się z nim połączyć.

Najważniejsze informacje:

- znak lub identyfikator bramki,
- częstotliwość pracy,
- prędkość packet,
- ewentualny offset lub uwagi lokalne,
- krótki komentarz.

## 2. Przykładowa ramka obiektu

Przykład schematyczny:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
```

Ramka składa się z kilku części:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- krótki opis
|        | |      |        | |        | |          |    +------- offset / dodatkowa informacja
|        | |      |        | |        | |          +------------ prędkość packet
|        | |      |        | |        +----------------------- symbol
|        | |      |        | +-------------------------------- długość geograficzna
|        | |      |        +---------------------------------- tabela symboli Winlink
|        | |      +------------------------------------------- szerokość geograficzna
|        | +-------------------------------------------------- znacznik czasu
|        +---------------------------------------------------- nazwa obiektu
+------------------------------------------------------------- typ ramki: obiekt
```

## 3. Nazwa obiektu

Dla obiektów Winlink stosuje się nazwy:

```text
WL-CALL
W1-CALL
W2-CALL
...
W9-CALL
```

Przykłady:

```text
WL-SR5ABC
W1-SR5ABC
W2-SP9XYZ
```

`WL-` oznacza podstawowy obiekt Winlink. Warianty `W1-` do `W9-` mogą być użyte, gdy istnieje kilka obiektów związanych z tym samym znakiem lub lokalizacją.

Nazwa powinna być krótka i czytelna, ponieważ jest wyświetlana na liście obiektów.

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
;WL-SR5ABC*111111z
```

## 5. Koordynaty i symbol

W formacie Winlink stosuje się tabelę symboli `W` oraz symbol `a`:

```text
5215.00NW02055.00Ea
```

Rozbicie:

```text
5215.00N   szerokość geograficzna
W          tabela symboli Winlink
02055.00E  długość geograficzna
a          symbol
```

Jeśli dokładne położenie bramki nie powinno być publikowane, można użyć pozycji przybliżonej w obszarze, gdzie zasób jest użyteczny.

## 6. Częstotliwość

Częstotliwość podaje się w komentarzu:

```text
144.950MHz
```

Zalecany format:

```text
xxx.xxxMHz
```

Przykłady:

```text
144.950MHz
145.050MHz
430.525MHz
```

## 7. Prędkość packet

W obiekcie Winlink w miejscu, gdzie dla przemienników głosowych zwykle pojawia się ton, podaje się prędkość packet.

Przykłady:

```text
1200
9600
```

Przykład komentarza:

```text
144.950MHz 1200 -000 Winlink
```

## 8. Offset i komentarz

Po prędkości można podać offset lub krótką informację dodatkową.

Przykłady:

```text
-000    bez offsetu, simplex
+060    offset +600 kHz
-060    offset -600 kHz
```

Komentarz końcowy powinien być krótki:

```text
Winlink
RMS
Packet
SR5ABC
```

## 9. Zalecana kolejność pól

Dla czytelności warto trzymać kolejność:

```text
częstotliwość prędkość offset/opis krótki-komentarz
```

Przykład:

```text
144.950MHz 1200 -000 Winlink
```

Inne przykłady:

```text
145.050MHz 1200 -000 RMS
430.525MHz 9600 -000 Winlink
144.950MHz 1200 Packet SR5ABC
```

## 10. Dobre praktyki

- Pamiętaj, że Winlink to zasób packet/data, nie przemiennik głosowy.
- W nazwie użyj `WL-` albo `W1-` do `W9-` oraz znak lub krótki identyfikator.
- W komentarzu podaj częstotliwość w formacie `xxx.xxxMHz`.
- Podaj prędkość packet, na przykład `1200` albo `9600`.
- Nie wpisuj tonu CTCSS zamiast prędkości packet, jeśli obiekt opisuje typowy punkt Winlink packet.
- Opis końcowy powinien być krótki.

## 11. Krótka ściąga

```text
;             początek obiektu
WL-SR5ABC     podstawowa nazwa obiektu Winlink
W1-SR5ABC     wariant dodatkowy
*             obiekt aktywny
111111z       stały znacznik czasu
W             tabela symboli Winlink
a             symbol Winlink
144.950MHz    częstotliwość
1200          prędkość packet
9600          prędkość packet
-000          simplex / brak offsetu
Winlink       krótki opis
```
