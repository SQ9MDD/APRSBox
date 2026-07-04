# Reguły routingu pakietów

To jest pełny plik pomocy dla zakładek `Packet Routing` oraz `Packet Flow`. Zawiera opis całego ekranu, najczęstszych zastosowań, kolejności kroków, bloków filtrujących i docelowych oraz praktycznych schematów reguł.

## Co robi ten ekran

Reguła routingu opisuje, co APRSBox ma zrobić z pakietem po jego odebraniu albo wygenerowaniu lokalnie.

Każda reguła ma:

- jedno źródło,
- zero lub więcej bloków filtrów i reguł pośrodku,
- jeden cel końcowy.

Pakiet zawsze idzie od góry do dołu. Jeżeli którykolwiek blok go odrzuci, kolejne kroki nie są już wykonywane.

## Jak czytać i budować regułę

Najprostszy sposób myślenia o regule jest taki:

1. Skąd pakiet wchodzi.
2. Jakie warunki ma spełnić.
3. Dokąd ma trafić na końcu.

Typowa kolejność budowy:

1. Wybierz źródło.
2. Wybierz cel.
3. Dodaj tylko te filtry, które naprawdę są potrzebne.
4. Zapisz i sprawdź log wykonania reguły.

## Najczęstsze use case'y

### `Odbiornik RF -> TX APRS-IS`

To klasyczny wariant iGate.

Schemat minimalny:

```text
Odbiornik RF -> Filtr ścisły -> TX APRS-IS
```

Używaj tego, gdy:

- lokalnie odebrane pakiety mają trafić do APRS-IS,
- różne porty RF mają mieć różne zasady wejścia do Internetu APRS,
- chcesz oddzielić ruch radiowy od ruchu lokalnie generowanego.

Najważniejsze uwagi:

- `Filtr ścisły` jest obowiązkowy,
- nie każda ramka odebrana z RF powinna wejść do APRS-IS,
- to jest ścieżka bardziej "iGate" niż "digi".

### `Odbiornik RF -> TX RF`

To klasyczny wariant digipeatera.

Schemat minimalny:

```text
Odbiornik RF -> Reguła ścieżki i ochrona DIGI -> TX RF
```

Schemat częstszy w praktyce:

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

Używaj tego, gdy:

- chcesz powtarzać ruch APRS w eterze,
- budujesz lokalny digi,
- robisz cross-band albo port-to-port RF,
- chcesz powtarzać tylko określony typ ruchu po dodatkowych filtrach.

Najważniejsze uwagi:

- `Reguła ścieżki i ochrona DIGI` jest wymagana,
- `Filtr duplikatów` zwykle warto dodać na początku,
- to tutaj najłatwiej niechcący przeciążyć kanał RF, więc ostrożność ma znaczenie.

### `Local TX -> TX APRS-IS`

To ścieżka dla ramek generowanych przez sam APRSBox.

Schemat:

```text
Local TX -> Filtr ścisły -> TX APRS-IS
```

Używaj tego, gdy:

- beacony, statusy, pogoda, obiekty, biuletyny albo wiadomości mają trafiać do APRS-IS,
- chcesz wypchnąć lokalnie generowany ruch bez osobnej reguły RF.

Najważniejsze uwagi:

- `Local TX` nie oznacza ramek odebranych z eteru,
- to osobny strumień, tworzony wewnątrz APRSBox,
- `Filtr ścisły` także tutaj pozostaje obowiązkowy.

### `Odbiornik RF -> Black Hole`

To ścieżka testowa i diagnostyczna.

Schemat:

```text
Odbiornik RF -> Black Hole
```

albo bardziej użytecznie:

```text
Odbiornik RF -> Tylko direct -> Black Hole
```

Używaj tego, gdy:

- chcesz sprawdzić działanie filtrów bez nadawania dalej,
- chcesz obserwować ruch z konkretnego portu,
- chcesz przygotować regułę "na sucho" przed włączeniem TX RF albo TX APRS-IS.

### `Local TX -> Black Hole`

To wariant pomocniczy do testów lokalnego nadawania aplikacji.

Używaj tego, gdy:

- chcesz zobaczyć, co generuje APRSBox,
- chcesz sprawdzić obiekty, statusy albo biuletyny bez emisji dalej.

## Bloki źródłowe

### `Odbiornik RF`

To źródło dla pakietów odebranych przez konkretny modem radiowy.

Kiedy używać:

- gdy reguła ma reagować na ruch przychodzący z eteru,
- gdy chcesz rozdzielić kilka odbiorników RF na osobne reguły.

W praktyce:

- każda reguła `Odbiornik RF -> ...` zaczyna się właśnie tym blokiem,
- wybór modemu w źródle decyduje, z którego wejścia w ogóle pakiet trafi do tej reguły.

### `Local TX`

To źródło dla ramek wygenerowanych lokalnie przez APRSBox.

Obejmuje między innymi:

- beacony,
- status,
- pogodę,
- obiekty,
- itemy,
- biuletyny,
- wiadomości.

Nie obejmuje:

- ramek odebranych z RF,
- ramek już digipeatowanych,
- zwykłego ruchu wejściowego z TNC.

W praktyce:

- to osobna ścieżka dla ruchu "wewnętrznego",
- `Local TX` może prowadzić tylko do `TX APRS-IS` albo `Black Hole`.

## Bloki filtrów i reguł

### `Filtr ścisły`

To systemowy filtr bezpieczeństwa dla ścieżek kończących się na `TX APRS-IS`.

Co robi:

- odrzuca pakiety z `TCPIP` albo `TCPXX`,
- odrzuca pakiety z `NOGATE` albo `RFONLY`,
- sprawdza poprawność ramek third-party,
- sprawdza ścieżkę zewnętrzną i wewnętrzną w third-party,
- pilnuje, żeby do APRS-IS nie trafił ruch, który nie powinien tam wejść.

Kiedy używać:

- zawsze przy `TX APRS-IS`,
- nigdy jako zamiennik dla reguł digipeatera RF.

Typowe use case'y:

- `Odbiornik RF -> Filtr ścisły -> TX APRS-IS`,
- `Local TX -> Filtr ścisły -> TX APRS-IS`.

### `Reguła ścieżki i ochrona DIGI`

To najważniejszy blok dla ścieżek `... -> TX RF`.

Co robi:

- analizuje digi path,
- sprawdza, czy lokalna stacja powinna jeszcze powtórzyć pakiet,
- blokuje wiadomości i zapytania adresowane lokalnie,
- blokuje third-party, które nie powinno być powtarzane,
- blokuje pakiet już wcześniej powtórzony przez tę samą stację.

Dlaczego ten blok jest obowiązkowy:

- bez niego reguła RF nie ma podstawowej ochrony logicznej digi,
- to właśnie ten blok pilnuje sensownego użycia ścieżki w eterze.

Pola konfiguracyjne:

- `Paths (TRACE / traced)`:
  To aliasy albo konkretne hop-y, które mają zostać zużyte z dodaniem lokalnego znaku digi do ścieżki.
- `Paths (NO TRACE / not traced)`:
  To aliasy albo hop-y, które mają zostać zużyte bez dopisywania lokalnego znaku do ścieżki.

Praktyka:

- `WIDE1-1` bywa używany jako traced,
- lista NO TRACE zależy od lokalnej polityki sieci i konkretnej instalacji,
- ten blok zwykle jest jednym z ostatnich przed `TX RF`.

Typowy schemat:

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

### `Filtr duplikatów (viscous-delay)`

Ten blok otwiera krótkie okno nasłuchu po wejściu pakietu.

Co robi:

- czeka przez ustalone okno czasu,
- sprawdza, czy w tym czasie ten sam pakiet został już powtórzony przez inne digi,
- jeśli tak, odrzuca pakiet,
- jeśli nie, przepuszcza go dalej po końcu okna.

Najważniejsze cechy:

- może wystąpić tylko raz,
- powinien być pierwszym filtrem w ścieżce RF,
- najczęściej używa się go właśnie w klasycznych regułach digi.

Kiedy używać:

- gdy chcesz ograniczyć zbędne powtórzenia,
- gdy kilka digi może słyszeć tę samą stację.

### `Tylko direct`

Ten filtr przepuszcza tylko pakiety usłyszane bezpośrednio.

Co to znaczy:

- ścieżka nie może zawierać żadnego już zużytego hopu digi,
- jeśli w path są zużyte elementy oznaczone `*`, pakiet zostanie odrzucony.

Kiedy używać:

- gdy chcesz reagować tylko na stacje słyszane lokalnie,
- gdy nie chcesz dalej obrabiać ramek już powtórzonych przez inne digi,
- gdy budujesz testy typu "co słyszę bezpośrednio".

### `Filtr DIGI`

Ten filtr analizuje zużyte hop-y digi w ścieżce.

Jak działa:

- sprawdza tylko hop-y już oznaczone jako zużyte,
- wzorce mogą używać `*`,
- tryb `allow` przepuszcza tylko pasujące pakiety,
- tryb `deny` odrzuca pasujące pakiety.

Przykłady wzorców:

- `SR5ABC`,
- `SR5*`,
- `*`.

Kiedy używać:

- gdy chcesz przepuszczać ruch po wybranych digi,
- gdy chcesz wyciąć ruch przychodzący z określonej części sieci.

### `Filtr znaków`

Ten filtr sprawdza znak źródłowy nadawcy pakietu.

Jak działa:

- działa na callsignie źródłowym,
- wspiera wildcard `*`,
- tryb `allow` działa jak whitelist,
- tryb `deny` działa jak blacklist.

Przykłady:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Kiedy używać:

- do rozdzielenia ruchu klubowego, testowego albo technicznego,
- do blokowania znanych źródeł zakłócających ruch.

### `Filtr typu pakietu`

Ten filtr działa na grupie pakietu APRS.

Do wpisania używa się dokładnie takich wartości:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Znaczenie praktyczne:

- `message` obejmuje także ACK/REJ, bulletin i announcement,
- `weather` dotyczy ramek weather-only,
- pozycja z danymi pogody nadal liczy się jako `position`.

Kiedy używać:

- gdy chcesz osobno traktować wiadomości, obiekty, pozycje albo pogodę,
- gdy jedna ścieżka ma dotyczyć tylko jednego rodzaju ruchu.

### `Filtr ikon`

Ten filtr działa na symbolu APRS zapisanym w postaci `table+code`.

Przykłady wpisów:

- `/>`,
- `\\l`.

Kiedy używać:

- gdy chcesz osobno obsłużyć określone klasy obiektów albo stacji,
- gdy symbol ma być ważniejszy niż sam typ pakietu.

### `Filtr odległości`

Ten filtr przepuszcza pakiet tylko wtedy, gdy jego pozycja mieści się w jednej z zadanych stref.

Jak działa:

- można ustawić od 1 do 3 stref,
- każda strefa ma środek i promień,
- strefy działają w logice OR,
- pakiety bez dekodowalnej pozycji nie są przez ten filtr automatycznie odrzucane.

Kiedy używać:

- gdy chcesz ograniczyć ruch do wybranego obszaru,
- gdy chcesz zrobić lokalne reguły tylko dla określonej okolicy.

### `Filtr limitu tempa`

Ten filtr ogranicza częstotliwość przepuszczania ramek od konkretnego znaku albo wzorca.

Format reguły:

```text
CALL_OR_PATTERN - LIMIT
```

Przykłady:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
* - 20s
```

Jak działa:

- dla każdego dopasowania liczony jest czas od ostatnio przepuszczonej ramki,
- kolejna ramka przed upływem limitu zostanie zablokowana.

Kiedy używać:

- gdy bardzo aktywne stacje generują zbyt dużo ruchu,
- gdy chcesz ochronić ścieżkę RF bez całkowitego blokowania źródła.

## Bloki docelowe

### `TX RF`

To cel nadający pakiet przez wskazany modem radiowy.

Używaj go:

- dla digi,
- dla cross-band,
- dla przekazywania między portami RF.

Typowy schemat:

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

### `TX APRS-IS`

To cel wysyłający pakiet do APRS-IS.

Używaj go:

- dla iGate,
- dla lokalnie generowanych ramek APRSBox kierowanych do Internetu APRS.

Najważniejsze ograniczenie:

- ten cel zawsze utrzymuje obowiązkowy `Filtr ścisły`.

### `Black Hole`

To cel diagnostyczny. Pakiet kończy na nim przebieg, ale nie jest nadawany dalej.

Używaj go:

- do testów,
- do obserwacji ruchu,
- do sprawdzania działania filtrów przed uruchomieniem emisji.

## Ograniczenia edytora

- Reguła ma zawsze jedno źródło i jeden cel.
- `Local TX` może prowadzić tylko do `TX APRS-IS` albo `Black Hole`.
- `TX APRS-IS` utrzymuje obowiązkowy `Filtr ścisły`.
- `TX RF` wymaga aktywnej `Reguły ścieżki i ochrony DIGI`.
- `Filtr duplikatów` może wystąpić tylko raz.
- `Filtr odległości` może wystąpić tylko raz.
- `Filtr limitu tempa` jest przeznaczony dla ścieżek kończących się na `TX RF`.

## Gotowe szkice reguł

### Prosty iGate RF

```text
Odbiornik RF -> Filtr ścisły -> TX APRS-IS
```

### Klasyczny digi RF

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

### Digi tylko dla stacji direct

```text
Odbiornik RF -> Tylko direct -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

### Ruch lokalnie generowany do APRS-IS

```text
Local TX -> Filtr ścisły -> TX APRS-IS
```

### Diagnostyka bez nadawania

```text
Odbiornik RF -> Black Hole
```

## Dobre praktyki

- Najpierw wybierz źródło i cel, dopiero potem buduj warunki.
- Przy `TX RF` myśl najpierw o ochronie kanału, dopiero potem o zasięgu.
- Przy `TX APRS-IS` pilnuj, żeby do Internetu wchodził tylko sensowny ruch.
- Na etapie testów zaczynaj od `Black Hole`.
- Po zapisaniu patrz w log wykonania reguły, bo pokazuje dokładnie, który krok przepuścił albo odrzucił pakiet.
