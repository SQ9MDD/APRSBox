# Ścieżki APRS w praktyce

Ten plik opisuje ścieżki APRS od strony protokołu: jak czytać zapis `WIDE2-1`, czym różni się ścieżka trasowana od nietrasowanej oraz jak realizowane są ścieżki jedno- i dwuczłonowe.

## 1. Czym jest ścieżka APRS

Ścieżka APRS to lista hopów lub aliasów, które określają, jak ramka ma być dalej powtarzana w sieci radiowej.

Przykłady:

```text
WIDE2-1
SP2-2
WIDE1-1,WIDE2-1
SP1-1,SP2-2
WIDE2-1,RFONLY
```

Najważniejsze zasady:

- kolejne elementy ścieżki są rozdzielane przecinkami,
- ścieżka jest realizowana od lewej strony,
- dopóki pierwszy jeszcze niezużyty element nie zostanie obsłużony, następne elementy nie są ruszane,
- `RFONLY` i `NOGATE` nie są hopami do powtarzania, tylko znacznikami ograniczającymi bramkowanie do APRS-IS.

W praktyce nadanie lokalne bez digipeaterów oznacza po prostu brak ścieżki. W wielu programach i urządzeniach spotyka się też wygodny skrót `DIRECT`, ale w sensie protokołu chodzi o emisję bez hopów digi.

## 2. Jak czytać zapis `N-N`

W ścieżkach typu `WIDEn-N` albo `SPn-N` liczba po lewej stronie opisuje rodzinę aliasu i jego początkowy zasięg, a liczba po prawej działa jak licznik pozostałych powtórzeń.

Przykład:

```text
WIDE2-2
```

oznacza, że ramka może zostać jeszcze dwa razy powtórzona przez kolejne digi. Po pierwszym powtórzeniu licznik maleje:

```text
WIDE2-2 -> WIDE2-1
```

Po drugim powtórzeniu ścieżka zostaje zużyta:

```text
WIDE2-1 -> WIDE2*
```

Gwiazda `*` oznacza, że dany element został już zrealizowany i nie powinien być dalej używany do kolejnych powtórzeń.

Analogicznie:

```text
SP2-2 -> SP2-1 -> SP2*
```

## 3. Ścieżki trasowane i nietrasowane

Najważniejsza różnica polega na tym, czy digi dopisuje swój znak do ścieżki.

### Ścieżka trasowana

W ścieżce trasowanej każde digi, które powtórzy ramkę, zostawia po sobie ślad. Dzięki temu można później zobaczyć, jaką drogę ramka przeszła w eterze.

Przykład ramki z trasowaniem:

```text
SP8XYZ-9>APRS,WIDE2-2:...
```

Po pierwszym digi:

```text
SP8XYZ-9>APRS,SR5AAA*,WIDE2-1:...
```

Po drugim digi:

```text
SP8XYZ-9>APRS,SR5AAA*,SR5BBB*:...
```

Zalety:

- łatwo prześledzić drogę pakietu,
- łatwiej diagnozować działanie sieci.

Wada:

- ramka rośnie przy każdym powtórzeniu, bo dochodzą kolejne znaki digi.

### Ścieżka nietrasowana

W ścieżce nietrasowanej digi nie dopisuje swojego znaku. Zmienia tylko sam licznik lub oznacza element jako zużyty.

Przykład:

```text
SP8XYZ-9>APRS,SP2-2:...
```

Po pierwszym digi:

```text
SP8XYZ-9>APRS,SP2-1:...
```

Po drugim digi:

```text
SP8XYZ-9>APRS,SP2*:...
```

Zalety:

- krótsza ramka,
- mniejsze narastanie długości pakietu przy kolejnych hopach.

Wada:

- nie widać, które konkretne digi przekazały ramkę.

W praktyce aliasy `WIDE` są zwykle trasowane, a aliasy krajowe lub regionalne, takie jak `SP` czy `WM`, bywają konfigurowane jako nietrasowane. To jednak nie jest magiczna cecha samego słowa, tylko wynik konfiguracji lokalnej sieci digi.

## 4. Ścieżka jednoczłonowa

Ścieżka jednoczłonowa ma jeden element, ale niekoniecznie oznacza tylko jedno powtórzenie.

Przykłady ścieżek jednoczłonowych:

```text
WIDE2-1
WIDE2-2
SP2-1
SP2-2
```

Interpretacja:

- `WIDE2-1` to jeden człon i jedno powtórzenie,
- `WIDE2-2` to jeden człon i dwa powtórzenia,
- `SP2-1` to jeden człon i jedno powtórzenie,
- `SP2-2` to jeden człon i dwa powtórzenia.

To częsta pułapka: liczba członów ścieżki i liczba powtórzeń to nie jest to samo.

Przykład ścieżki jednoczłonowej trasowanej:

```text
WIDE2-2
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Przykład ścieżki jednoczłonowej nietrasowanej:

```text
SP2-2
-> SP2-1
-> SP2*
```

## 5. Ścieżka dwuczłonowa

Ścieżka dwuczłonowa ma dwa elementy rozdzielone przecinkiem i zawsze jest realizowana od lewej do prawej.

Przykład:

```text
WIDE1-1,WIDE2-1
```

Najpierw musi zostać zużyty pierwszy człon:

```text
WIDE1-1,WIDE2-1
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Warto tu dopowiedzieć ważną rzecz praktyczną: pierwszy człon taki jak `WIDE1-1` albo `SP1-1` ma zwykle rolę specjalnego odcinka dla digi pomocniczych, czyli `fill-in digi`.

Taki digi co do zasady powinien obsłużyć tylko ten pierwszy człon i nie powinien rozwijać dalszej części ścieżki. W przypadku stacji ręcznej albo mobilnej `WIDE1-1` jest właśnie po to, żeby pobliskie stacje domowe lub inne lokalne digi pomocnicze mogły pomóc wyjść z lokalnej dziury zasięgowej, ale bez dalszego powielania całej ścieżki.

Drugi przykład:

```text
SP1-1,SP2-2
```

Realizacja:

```text
SP1-1,SP2-2
-> SP1*,SP2-2
-> SP1*,SP2-1
-> SP1*,SP2*
```

Najważniejsze wnioski:

- `WIDE1-1,WIDE2-1` to dwa człony i dwa powtórzenia łącznie,
- `WIDE1-1,WIDE2-2` to dwa człony, ale już trzy powtórzenia łącznie,
- `SP1-1,SP2-2` to także dwa człony i trzy powtórzenia łącznie.
- pierwszy człon `WIDE1-1` albo `SP1-1` ma zwykle sens jako odcinek dla digi pomocniczego, które kończy pracę po obsłużeniu tylko tego jednego hopu.

Ścieżka dwuczłonowa trasowana rośnie szybciej niż nietrasowana, bo każdy kolejny hop może dopisywać znak następnego digi.

## 6. `RFONLY` i `NOGATE`

Na końcu ścieżki można spotkać dodatkowe znaczniki:

```text
WIDE2-1,RFONLY
WIDE1-1,WIDE2-1,NOGATE
```

Ich znaczenie w praktyce jest podobne: są używane do zablokowania bramkowania ruchu z RF do APRS-IS.

Te elementy:

- nie dodają kolejnych hopów,
- nie wydłużają zasięgu radiowego,
- służą tylko do ograniczenia przejścia ruchu do internetu.

## 7. Praktyczne wnioski

- brak ścieżki oznacza emisję lokalną bez digi,
- ścieżka jednoczłonowa bywa wystarczająca tam, gdzie nie potrzeba wielu powtórzeń,
- ścieżka dwuczłonowa daje większy zasięg, ale szybko zwiększa liczbę kopii w kanale,
- ścieżka trasowana jest wygodniejsza diagnostycznie,
- ścieżka nietrasowana zwykle mniej rozpycha ramkę,
- układy z `WIDE1-1` na początku mają sens tylko wtedy, gdy są zgodne z lokalną praktyką i topologią sieci,
- zawsze warto trzymać się zaleceń obowiązujących w danym regionie, bo to lokalna sieć digi decyduje, które aliasy rzeczywiście działają i jak są realizowane.
