# Obiekty przemiennikowe w APRS

Ten dokument opisuje praktyczny format obiektu przemiennika w APRS. Jest przeznaczony jako plik pomocy dla użytkownika tworzącego obiekty częstotliwościowe, szczególnie dla przemienników FM.

Celem jest przygotowanie ramki, która będzie czytelna dla operatorów, zgodna z praktyką APRS Frequency Objects i możliwie dobrze obsługiwana przez radia mobilne APRS.

## 1. Przykładowa ramka obiektu

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Ramka składa się z kilku logicznych części:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- komentarz, znak lub opis
|        | |      |        | |        | |          |    |    +------- zasięg przemiennika
|        | |      |        | |        | |          |    +------------ shift przemiennika
|        | |      |        | |        | |          +----------------- ton CTCSS i szerokość FM
|        | |      |        | |        +---------------------------- symbol
|        | |      |        | +------------------------------------- długość geograficzna
|        | |      |        +--------------------------------------- tabela symboli
|        | |      +------------------------------------------------ szerokość geograficzna
|        | +------------------------------------------------------- znacznik czasu
|        +--------------------------------------------------------- nazwa obiektu
+------------------------------------------------------------------ typ ramki: obiekt
```

## 2. Typ ramki: obiekt

Obiekt APRS zaczyna się od średnika:

```text
;
```

Po średniku występuje nazwa obiektu:

```text
;438.462WX
```

W przykładzie nazwa obiektu zawiera częstotliwość oraz lokalny wyróżnik:

```text
438.462WX
```

gdzie:

```text
438.462  - częstotliwość przemiennika widoczna jako nazwa obiektu
WX       - lokalny wyróżnik, w Polsce często oznaczenie powiatu
```

## 3. Nazwa obiektu: częstotliwość i lokalny wyróżnik

Dla obiektów przemiennikowych zaleca się, aby nazwa obiektu zaczynała się od częstotliwości:

```text
438.462WX
145.600WA
145.775KR
```

Taki zapis nie jest przypadkowy. W obiektach przemiennikowych i częstotliwościowych APRS częstotliwość w nazwie obiektu poprawia czytelność na radiach mobilnych APRS. Radio pokazuje nazwę obiektu na liście stacji, więc operator od razu widzi częstotliwość przemiennika bez konieczności wchodzenia w szczegóły obiektu.

Częstotliwość powinna być również powtórzona w komentarzu obiektu, na przykład:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Pierwsze wystąpienie częstotliwości, w nazwie obiektu, służy głównie czytelności na liście obiektów. Drugie wystąpienie, w komentarzu, jest częścią informacji częstotliwościowej i może być używane przez radia lub aplikacje do funkcji QSY/TUNE albo do prezentacji parametrów przemiennika.

Nie należy traktować częstotliwości w nazwie i częstotliwości w komentarzu jako błędnego duplikatu. To świadomy kompromis wynikający z kompatybilności i praktyki używania obiektów częstotliwościowych.

## 4. Unikalność nazwy obiektu

Nazwa obiektu APRS ma ograniczoną długość, dlatego zapis:

```text
częstotliwość + lokalny wyróżnik
```

jest kompromisem między czytelnością a unikalnością.

Przykład:

```text
438.462WX
```

oznacza obiekt dla częstotliwości `438.462 MHz` z lokalnym wyróżnikiem `WX`.

W Polsce jako wyróżnik często stosuje się oznaczenie powiatu. Pomaga to odróżnić obiekty przemienników pracujących na tej samej częstotliwości w różnych lokalizacjach.

Dla obiektów permanentnych trzeba jednak pamiętać, że obiekt może trafić do całej sieci APRS-IS. Lokalny wyróżnik, taki jak powiat, zmniejsza ryzyko kolizji lokalnej, ale nie daje pełnej gwarancji unikalności globalnej.

Praktyczna zasada:

```text
zalecany schemat:
    częstotliwość + lokalny wyróżnik
    przykład: 438.462WX

zalecenie:
    nazwa obiektu powinna zaczynać się od częstotliwości

ostrzeżenie:
    dla obiektów permanentnych wysyłanych do APRS-IS sprawdź,
    czy nazwa jest możliwie unikalna w skali globalnej
```

Jeśli przemiennik ma dobrze rozpoznawalny znak, nazwę lub identyfikator, można go umieścić w komentarzu końcowym, zamiast rezygnować z częstotliwości w nazwie obiektu.

## 5. Znak aktywności

Po nazwie obiektu występuje znak aktywności:

```text
*
```

Przykład:

```text
;438.462WX*
```

Znaczenie:

```text
*  - obiekt aktywny
_  - obiekt usunięty lub nieaktywny
```

Dla normalnego, działającego przemiennika używa się `*`.

## 6. Znacznik czasu

W przykładzie użyto:

```text
111111z
```

Pełny fragment:

```text
;438.462WX*111111z
```

Znacznik `111111z` jest często używany jako stały znacznik czasu dla obiektów stałych.

Praktyczna zasada:

```text
obiekt stały lub permanentny:
    111111z

obiekt tymczasowy:
    aktualny czas UTC generowany przy każdej wysyłce
```

Dla obiektu stałego ważniejsze jest regularne poprawne odświeżanie obiektu niż informowanie o dokładnym czasie jego wygenerowania.

## 7. Koordynaty i symbol

Przykład pozycji:

```text
5218.54N/02113.09Er
```

Rozbicie:

```text
5218.54N   szerokość geograficzna
/          tabela symboli
02113.09E  długość geograficzna
r          symbol
```

Dla obiektu przemiennika w przykładzie użyto symbolu `r`.

## 8. Częstotliwość przemiennika w komentarzu

Po pozycji podaje się częstotliwość pracy przemiennika:

```text
438.462MHz
```

Zalecany zapis:

```text
xxx.xxxMHz
```

Przykłady:

```text
145.600MHz
438.462MHz
439.000MHz
```

Częstotliwość w komentarzu powinna odpowiadać częstotliwości użytej w nazwie obiektu.

Przykład poprawny:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Przykład podejrzany:

```text
;438.462WX*111111z5218.54N/02113.09Er439.000MHz C127 -760 R10k SR5WWL
```

W drugim przykładzie nazwa obiektu sugeruje `438.462 MHz`, ale komentarz podaje `439.000 MHz`. Taki zapis może wprowadzać operatora w błąd.

## 9. CTCSS, ton i szerokość FM

W przykładzie:

```text
C127
```

Oznacza informację o tonie CTCSS i sposobie pracy przemiennika.

Znaczenie liter:

```text
t oraz c  - wąski FM
T oraz C  - szeroki FM

t oraz T  - przemiennik jest otwierany tonem
c oraz C  - przemiennik jest otwierany tonem i wysyła ton
```

Przykładowa interpretacja:

```text
T127  - szeroki FM, przemiennik otwierany tonem 127 Hz
C127  - szeroki FM, przemiennik otwierany tonem 127 Hz i wysyłający ton
t127  - wąski FM, przemiennik otwierany tonem 127 Hz
c127  - wąski FM, przemiennik otwierany tonem 127 Hz i wysyłający ton
```

Warto trzymać się zapisu trzycyfrowego, jeśli ton ma mniej niż trzy cyfry:

```text
T088
c088
```

## 10. Shift przemiennika

W przykładzie:

```text
-760
```

Oznacza shift `-7,6 MHz`.

Zasada zapisu:

```text
-760  -> shift -7,6 MHz
-060  -> shift -600 kHz
+760  -> shift +7,6 MHz
+060  -> shift +600 kHz
```

Czyli wartość wpisujemy jako przesunięcie bez przecinka.

Przykłady:

```text
145.600MHz -060
438.462MHz -760
439.000MHz +760
```

## 11. Zasięg przemiennika: Rxxk / Rxxm

Dla obiektów przemiennikowych zasięg można podać jako:

```text
Rxxk
Rxxm
```

Znaczenie:

```text
R10k  - zasięg około 10 km
R25k  - zasięg około 25 km
R15m  - zasięg około 15 mil
```

W przykładzie:

```text
R10k
```

czyli deklarowany zasięg przemiennika wynosi około 10 km.

Dla obiektów przemiennikowych preferowany jest zapis `Rxxk` albo `Rxxm`. Nie należy go mylić z klasycznym rozszerzeniem `RNGxxxx`, które jest innym mechanizmem opisu zasięgu radiowego.

## 12. Komentarz, znak lub opis

Na końcu można umieścić znak, nazwę przemiennika lub krótki opis:

```text
SR5WWL
```

Pełny końcowy fragment:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Komentarz powinien być krótki. Ramka APRS nie jest dobrym miejscem na długie opisy, adresy stron lub wielozdaniowe informacje.

## 13. Zalecana kolejność pól w komentarzu

Dla czytelności i kompatybilności warto trzymać stałą kolejność:

```text
częstotliwość tryb/CTCSS shift zasięg komentarz
```

Przykład:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Inne przykłady:

```text
145.600MHz T103 -060 R25k SR9ABC
439.000MHz C123 +760 R30k Local
145.775MHz c088 -060 R15k SR5YYY
```

## 14. Zalecane pola formularza lub generatora

Przy tworzeniu obiektu przemiennikowego pomocny jest prosty generator składający nazwę obiektu i komentarz z osobnych pól.

Proponowane pola:

```text
Nazwa obiektu:
    438.462WX

Tryb nazwy obiektu:
    częstotliwość + lokalny wyróżnik
    własna nazwa

Lokalny wyróżnik:
    WX

Częstotliwość:
    438.462

Ton CTCSS:
    127

Tryb tonu:
    otwierany tonem
    otwierany tonem i wysyła ton

Szerokość FM:
    wąski FM
    szeroki FM

Shift:
    -7.6 MHz
    -0.6 MHz
    +0.6 MHz
    +7.6 MHz
    własny

Zasięg:
    10

Jednostka zasięgu:
    km
    mile

Komentarz:
    SR5WWL
```

Wynik:

```text
nazwa obiektu:
    438.462WX

komentarz:
    438.462MHz C127 -760 R10k SR5WWL
```

Generator powinien pilnować, żeby częstotliwość była widoczna zarówno w nazwie obiektu, jak i w komentarzu. Nie należy usuwać częstotliwości z nazwy tylko dlatego, że występuje już w komentarzu.

Przy obiekcie permanentnym kierowanym do APRS-IS warto pokazać ostrzeżenie:

```text
Nazwy obiektów permanentnych powinny być możliwie unikalne globalnie.
Schemat częstotliwość + lokalny wyróżnik jest zalecany dla czytelności na radiach APRS,
ale nie gwarantuje pełnej unikalności w skali całej sieci APRS-IS.
```

## 15. Zalecana walidacja

Proponowane zasady walidacji:

```text
nazwa obiektu:
    wymagana
    zalecany format dla przemienników: częstotliwość + lokalny wyróżnik
    przykład: 438.462WX
    ostrzeżenie, jeśli obiekt permanentny ma trafić do APRS-IS
    i nazwa wygląda zbyt ogólnie albo nie zawiera wyróżnika

częstotliwość:
    wymagana
    format xxx.xxx

zgodność nazwy i komentarza:
    częstotliwość z nazwy obiektu powinna zgadzać się
    z częstotliwością w komentarzu, jeśli obie są podane

CTCSS:
    opcjonalny
    tylko popularne wartości CTCSS albo liczba 2-3 cyfrowa

tryb tonu:
    t / T / c / C

shift:
    opcjonalny
    format +xxx albo -xxx

zasięg:
    opcjonalny
    format Rxxk albo Rxxm

komentarz:
    opcjonalny
    krótki tekst bez przeładowywania ramki
```

Walidacja powinna pomagać użytkownikowi, a nie blokować wszystkie nietypowe przypadki. Dla świadomego użytkownika warto pozostawić możliwość ręcznej korekty.

## 16. Przykłady gotowych obiektów

### Przemiennik UHF, szeroki FM, CTCSS, shift -7,6 MHz

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

### Przemiennik VHF, szeroki FM, ton na wejściu, shift -600 kHz

```text
;145.600WA*111111z5215.00N/02055.00Er145.600MHz T103 -060 R25k SR5XXX
```

### Przemiennik VHF, wąski FM, ton na wejściu i wyjściu

```text
;145.775KR*111111z5215.00N/02055.00Er145.775MHz c088 -060 R15k SR5YYY
```

## 17. Jak czytać obiekt w szczegółach

Z przykładowej ramki:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

można odczytać:

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

## 18. Krótka ściąga

```text
;             początek obiektu
438.462WX     nazwa obiektu: częstotliwość + lokalny wyróżnik
*             obiekt aktywny
_             obiekt usunięty lub nieaktywny
111111z       stały znacznik czasu
/             tabela symboli
r             symbol przemiennika
438.462MHz    częstotliwość w komentarzu
T127          szeroki FM, otwierany tonem 127 Hz
C127          szeroki FM, otwierany tonem 127 Hz i wysyłający ton
t127          wąski FM, otwierany tonem 127 Hz
c127          wąski FM, otwierany tonem 127 Hz i wysyłający ton
-760          shift -7,6 MHz
-060          shift -600 kHz
R10k          zasięg 10 km
R15m          zasięg 15 mil
```
