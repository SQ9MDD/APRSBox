# Packet Flow - szczegółowy opis reguły

Ten plik pomocy dotyczy edytora `Packet Flow`, otwieranego po wejściu w konkretną regułę z listy `Packet Routing`.

Zawiera dokładny opis budowy reguły, najczęstszych zastosowań, kolejności kroków, bloków filtrów, bloków docelowych oraz gotowych schematów do użycia.

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

Jak działa dla ramek z `Odbiornik RF`:

- sprawdza całą zewnętrzną ścieżkę,
- odrzuca pakiet, jeśli gdziekolwiek w path występuje `TCPIP`, `TCPXX`, `NOGATE` albo `RFONLY`,
- jeśli ramka jest third-party, najpierw sprawdza poprawność enkapsulacji,
- dla poprawnej third-party sprawdza także ścieżkę wewnętrzną i tam również blokuje `TCPIP`, `TCPXX`, `NOGATE` oraz `RFONLY`.

Jak działa dla `Local TX`:

- wymaga, aby ramka była oznaczona w metadanych jako ruch lokalnie wygenerowany przez APRSBox,
- odrzuca każdą ramkę third-party,
- odrzuca ramkę, jeśli w path znajduje się konstrukcja `q..`, na przykład `qAO`,
- nadal blokuje `TCPIP`, `TCPXX`, `NOGATE` i `RFONLY`.

Najważniejsze uwagi:

- przy `TX APRS-IS` ten filtr jest obowiązkowy,
- to nie jest filtr do sterowania digipeaterem RF,
- jeśli parser TNC2 nie rozpozna ramki, filtr ją odrzuca.

Typowe use case'y:

- `Odbiornik RF -> Filtr ścisły -> TX APRS-IS`,
- `Local TX -> Filtr ścisły -> TX APRS-IS`.

### `Reguła ścieżki i ochrona DIGI`

To najważniejszy blok dla ścieżek `... -> TX RF`. Ten krok robi dwie rzeczy naraz: najpierw wykonuje ochronę DIGI, a dopiero potem obsługuje pierwszy jeszcze niezużyty element ścieżki.

Najpierw część ochronna odrzuca:

- ramki third-party,
- wiadomości APRS do lokalnej `My station`,
- query APRS do lokalnej `My station`,
- wiadomości APRS do lokalnej stacji `WX`,
- query APRS do lokalnej stacji `WX`,
- pakiety, w których lokalny znak jest już w path jako hop zużyty, na przykład `MYCALL-SSID*`.

Dopiero potem analizowany jest path:

- jeżeli ścieżka jest pusta, pakiet odpada,
- jeżeli wszystkie hop-y są już zużyte, pakiet odpada,
- sprawdzany jest tylko pierwszy element bez `*`,
- dalsze elementy nie są analizowane, dopóki pierwszy nie zostanie obsłużony.

Pola konfiguracyjne:

- `Paths (TRACE / traced)`:
  Jeśli pierwszy niezużyty hop pasuje do tej listy, APRSBox zużywa go i wstawia własny znak z `My settings` jako hop powtórzony przez lokalne digi.
- `Paths (NO TRACE / not traced)`:
  Jeśli pierwszy niezużyty hop pasuje do tej listy, hop zostaje tylko oznaczony jako zużyty, bez dopisywania lokalnego znaku do ścieżki.

Co dokładnie można wpisać:

- pełny hop, na przykład `WIDE1-1`, `WIDE2-1`, `WIDE2-2`, `SP2-2`,
- sam alias rodziny, na przykład `WIDE`; wtedy pasują ścieżki z tej rodziny typu `WIDE1-1` albo `WIDE2-2`.

Przekształcenie ścieżki w praktyce:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `WIDE2-2` -> `WIDE2-2*,WIDE2-1`,
- NO TRACE `SP2-2` -> `SP2-2*,SP2-1`,
- jeśli hop nie ma postaci `N-N`, NO TRACE po prostu dopisuje `*`.

Typowe wpisy startowe:

- `TRACE`: `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: własny `CALLSIGN-SSID` z `My settings` oraz lokalne wyjątki zgodne z polityką sieci.

Dlaczego własny znak warto dodać do `NO TRACE`:

- jeżeli chcesz zużywać pakiety kierowane bezpośrednio do Twojego znaku bez ponownego dopisywania go do ścieżki,
- jeżeli w lokalnej sieci używasz własnego znaku jako jawnego hopu bez śladu TRACE.

Najważniejsze uwagi:

- jeżeli TRACE zadziała, a lokalny znak nie jest skonfigurowany, pakiet zostanie odrzucony,
- jeżeli pierwszy niezużyty hop nie pasuje ani do TRACE, ani do NO TRACE, pakiet zostanie odrzucony,
- to właśnie ten blok pilnuje sensownego użycia ścieżki w eterze.

Typowy schemat:

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

### `Filtr duplikatów (viscous-delay)`

Ten blok nie przepuszcza pakietu od razu. Pierwsza ramka z danym fingerprintem zostaje najpierw wstrzymana na czas okna nasłuchu.

Jak działa naprawdę:

- fingerprint budowany jest z `source callsign + info field`,
- ścieżka nie bierze udziału w porównaniu duplikatów,
- pierwsza ramka z danym fingerprintem czeka do końca okna,
- jeśli w tym czasie pojawi się druga ramka z tym samym fingerprintem, obie są odrzucane,
- jeżeli do końca okna nie pojawi się duplikat, pierwsza ramka rusza dalej dopiero po wygaśnięciu timera.

Konsekwencje praktyczne:

- dwa pakiety od tej samej stacji z tym samym payloadem, ale z inną ścieżką, nadal liczą się jako duplikat,
- filtr działa jak viscous-delay: najpierw czeka, potem dopiero decyduje,
- może wystąpić tylko raz i powinien być pierwszym filtrem w ścieżce RF.

Kiedy używać:

- gdy kilka digi może słyszeć tę samą stację,
- gdy chcesz ograniczyć zbędne powtórzenia bez natychmiastowego TX.

### `Tylko direct`

Ten filtr przepuszcza tylko pakiety usłyszane bezpośrednio.

Jak działa naprawdę:

- sprawdza wyłącznie, czy w path istnieje jakikolwiek już zużyty hop oznaczony `*`,
- nie interesują go hop-y jeszcze niezużyte, na przykład `WIDE1-1`,
- pakiet `...,WIDE1-1:` przejdzie,
- pakiet `...,SR5ABC*,WIDE1-1:` zostanie odrzucony.

Kiedy używać:

- gdy chcesz reagować tylko na stacje słyszane lokalnie,
- gdy nie chcesz dalej obrabiać ramek już powtórzonych przez inne digi,
- gdy budujesz testy typu "co słyszę bezpośrednio".

### `Filtr DIGI`

Ten filtr nie patrzy na cały path i nie sprawdza hop-ów jeszcze niezużytych. Analizuje wyłącznie listę hop-ów już oznaczonych `*`, po zdjęciu tej gwiazdki.

Jak działa naprawdę:

- z path `SR5BCD-2*,WIDE1-1` widzi tylko `SR5BCD-2`,
- z path `WIDE1-1` nie widzi nic, bo nie ma jeszcze żadnego zużytego hopu,
- wzorce są porównywane do zużytych hop-ów; wildcard `*` może być użyty w dowolnym miejscu,
- tryb `allow` przepuszcza pakiet tylko wtedy, gdy co najmniej jeden zużyty hop pasuje do listy,
- tryb `deny` odrzuca pakiet tylko wtedy, gdy co najmniej jeden zużyty hop pasuje do listy.

Konsekwencje praktyczne:

- pusta lista `allow` odrzuca wszystko,
- pusta lista `deny` przepuszcza wszystko,
- wpis `*` w `deny` blokuje wszystkie pakiety już kiedyś digipeatowane,
- wpis `*` w `deny` nie blokuje ramek direct, bo direct nie ma żadnego zużytego hopu do dopasowania.

Przykłady:

- path `SR5BCD-2*,WIDE1-1` + wzorzec `SR5BCD*` -> match,
- path `SR5ABC*,WIDE1-1` + `deny: *` -> drop,
- path `WIDE1-1` + `deny: *` -> pass.

Kiedy używać:

- gdy chcesz przepuszczać ruch tylko po wybranych digi,
- gdy chcesz wyciąć ruch, który przyszedł już przez określone stacje pośrednie.

### `Filtr znaków`

Ten filtr sprawdza wyłącznie znak źródłowy nadawcy pakietu. Nie analizuje ścieżki, hop-ów digi ani celu pakietu.

Jak działa:

- bez wildcard `*` dopasowanie jest dokładne,
- `SQ9MDD` nie pasuje do `SQ9MDD-4`,
- wildcard `*` może być użyty w dowolnym miejscu,
- `allow` działa jak whitelist,
- `deny` działa jak blacklist.

Konsekwencje praktyczne:

- pusta lista `allow` odrzuca wszystko,
- pusta lista `deny` przepuszcza wszystko.

Przykłady:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Kiedy używać:

- do rozdzielenia ruchu klubowego, testowego albo technicznego,
- do blokowania znanych źródeł zakłócających ruch.

### `Filtr typu pakietu`

Ten filtr działa na tym, co parser APRSBox zdekoduje jako typ lub grupę pakietu APRS.

Najczęściej używane selektory:

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
- `weather` dotyczy tylko ramek weather-only,
- pozycja z danymi pogody nadal liczy się jako `position`,
- dla zgodności wstecznej działają też stare kody typu, na przykład `M`, `S`, `O`, `W`, oraz inne surowe kody zwracane przez parser.

Jak działa:

- w trybie `allow` pakiet przechodzi tylko wtedy, gdy zdekodowany typ lub grupa pasuje do listy,
- w trybie `deny` pakiet odpada tylko wtedy, gdy pasuje do listy,
- jeśli parser nie potrafi określić grupy/typu, `allow` odrzuca, a `deny` przepuszcza.

Kiedy używać:

- gdy chcesz osobno traktować wiadomości, obiekty, pozycje albo pogodę,
- gdy jedna ścieżka ma dotyczyć tylko jednego rodzaju ruchu.

### `Filtr ikon`

Ten filtr działa na symbolu APRS zapisanym dokładnie w postaci `table+code`.

Jak działa:

- dopasowanie jest dokładne, bez wildcardów,
- filtr porównuje dokładnie taki symbol, jaki zwrócił parser APRSBox,
- w trybie `allow` brak dopasowania oznacza odrzucenie,
- w trybie `deny` brak dopasowania oznacza przepuszczenie,
- jeśli symbolu nie da się zdekodować, `allow` odrzuca, a `deny` przepuszcza.

Przykłady wpisów:

- `/>`,
- `\\l`.

Kiedy używać:

- gdy chcesz osobno obsłużyć określone klasy obiektów albo stacji,
- gdy symbol ma być ważniejszy niż sam typ pakietu.

### `Filtr odległości`

Ten filtr przepuszcza pakiet tylko wtedy, gdy jego zdekodowana pozycja mieści się w co najmniej jednej z zadanych stref.

Jak działa:

- można ustawić od 1 do 3 stref,
- każda strefa ma środek i promień,
- strefy działają w logice OR,
- jeśli nie zdefiniowano żadnej poprawnej strefy, filtr jest pomijany,
- jeśli pakiet nie ma dekodowalnej pozycji, filtr jest pomijany,
- dopiero pakiet z pozycją poza wszystkimi strefami zostaje odrzucony.

Kiedy używać:

- gdy chcesz ograniczyć ruch do wybranego obszaru,
- gdy chcesz zrobić lokalne reguły tylko dla określonej okolicy.

### `Filtr limitu tempa`

Ten filtr nie liczy "pakietów na minutę". To prosty limiter czasu od ostatnio przepuszczonej ramki dla znaku źródłowego.

Format reguły:

```text
CALL_OR_PATTERN - LIMIT
```

Przykłady:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

Jak działa:

- filtr działa wyłącznie na źródłowym callsignie pakietu,
- pierwsza pasująca ramka zawsze przechodzi,
- kolejna ramka od tego samego źródła i dla tego samego dopasowanego wzorca zostanie zablokowana, jeśli przyjdzie przed upływem limitu,
- licznik aktualizuje się tylko po ramce przepuszczonej,
- jeśli żadna reguła nie pasuje do źródła, filtr nic nie blokuje i przepuszcza pakiet dalej.

Jak dopasowywane są wzorce:

- `SQ9MDD-7` bez wildcardu pasuje tylko do dokładnie tego SSID,
- `SQ9MDD` bez wildcardu, ale też bez SSID, pasuje do tego callsignu z dowolnym SSID,
- `SQ*` działa jako wildcard,
- gdy pasuje kilka reguł naraz, runtime wybiera najbardziej szczegółową; przy remisie wygrywa wcześniejsza linia.

Ograniczenia formatu:

- `LIMIT` można zapisać jako `30`, `30s` albo `30S`,
- dozwolony zakres to od 5 do 300 sekund,
- krok wynosi 5 sekund.

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
