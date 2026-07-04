# Szczegółowy opis bloków routingu

Ten dokument opisuje bloki dostępne w edytorze pojedynczej reguły routingu. Każda reguła składa się z jednego źródła, zero lub więcej filtrów pośrodku oraz jednego celu.

## Jak czytać regułę

Pakiet przechodzi przez regułę od góry do dołu.

1. Wchodzi ze źródła.
2. Przechodzi przez każdy kolejny blok filtra albo reguły.
3. Jeżeli którykolwiek blok odrzuci pakiet, dalsze kroki nie są wykonywane.
4. Jeżeli pakiet przejdzie całą ścieżkę, trafia do celu.

## Bloki źródłowe

### `Receiver RF`

To wejście dla pakietów odebranych z konkretnego modemu radiowego.

Używaj tego bloku, gdy reguła ma obsługiwać ruch przychodzący z eteru.

### `Local TX`

To wejście dla ramek tworzonych lokalnie przez APRSBox.

Obejmuje między innymi:

- beacony,
- status,
- pogodę,
- obiekty,
- itemy,
- biuletyny,
- wiadomości.

Ten blok nie obejmuje ramek odebranych z RF ani już digipeatowanych.

## Bloki filtrów i reguł

### `Strict Filter`

To systemowy filtr bezpieczeństwa dla ścieżki do APRS-IS.

Zadania tego bloku:

- odrzuca ramki zawierające `TCPIP` albo `TCPXX`,
- odrzuca ramki oznaczone `NOGATE` albo `RFONLY`,
- sprawdza poprawność ramek third-party,
- blokuje niepoprawne ścieżki wewnętrzne i zewnętrzne.

Użycie:

- obowiązkowy przy `TX APRS-IS`,
- nie jest przeznaczony do zwykłych reguł `RF -> RF`,
- ma chronić zgodność z zasadami ruchu do APRS-IS.

### `Path rule and DIGI guard`

To podstawowy blok dla reguł `RF -> RF`.

Zadania tego bloku:

- analizuje ścieżkę digi w pakiecie,
- decyduje, czy lokalna stacja powinna jeszcze powtórzyć pakiet,
- blokuje wiadomości i zapytania adresowane lokalnie,
- blokuje third-party tam, gdzie nie powinny być powtarzane,
- blokuje pakiety już powtórzone przez tę samą stację.

Użycie:

- wymagany przy `TX RF`,
- powinien znajdować się blisko końca części filtrującej,
- jest kluczowy dla bezpiecznego zachowania digi w eterze.

### `Duplicate Filter (viscous-delay)`

Ten blok otwiera krótkie okno nasłuchu. W tym czasie APRSBox sprawdza, czy identyczna ramka została już powtórzona przez inny digi.

Jeżeli tak:

- pakiet zostaje odrzucony.

Jeżeli nie:

- pakiet idzie dalej po upływie okna.

Użycie:

- przy digipeaterze RF, gdy chcesz zmniejszyć liczbę zbędnych powtórzeń,
- jako pierwszy blok filtra w regule RF.

### `Direct Only`

Ten filtr przepuszcza tylko pakiety odebrane bezpośrednio, bez żadnego już zużytego hopu digi.

Użycie:

- gdy chcesz reagować wyłącznie na stacje słyszane lokalnie,
- gdy reguła ma ignorować ramki już powtarzane przez inne digi.

### `DIGI Filter`

Ten filtr sprawdza, jakie digi już pojawiły się w zużytej ścieżce pakietu.

Tryby:

- `allow` przepuszcza tylko pakiety pasujące do listy,
- `deny` odrzuca pakiety pasujące do listy.

Użycie:

- do akceptowania tylko ruchu po wybranych digi,
- do wycinania ramek pochodzących z konkretnych ścieżek powtórzeń.

### `Callsign Filter`

Ten filtr sprawdza znak źródłowy nadawcy pakietu.

Tryby:

- `allow` przepuszcza tylko dopasowane znaki,
- `deny` odrzuca dopasowane znaki.

Użycie:

- do tworzenia whitelisty albo blacklisty nadawców,
- do rozdzielenia ruchu klubowego, testowego albo serwisowego.

### `Packet Type Filter`

Ten filtr działa na głównych grupach pakietów APRS.

Obsługiwane grupy:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Użycie:

- gdy chcesz osobno traktować pozycje, wiadomości, pogodę albo obiekty,
- gdy jedna reguła ma obsługiwać tylko wybraną klasę ruchu.

### `Icon Filter`

Ten filtr działa na symbolu APRS.

Użycie:

- do przepuszczania albo blokowania konkretnych ikon,
- do tworzenia osobnych tras na przykład dla stacji mobilnych, pogodowych albo obiektów specjalnych.

### `Distance Filter`

Ten filtr przepuszcza pakiet tylko wtedy, gdy jego pozycja mieści się w jednej z zadanych stref.

Właściwości:

- można zdefiniować od 1 do 3 stref,
- każda strefa ma środek i promień,
- pakiet bez dekodowalnej pozycji nie jest przez ten filtr odrzucany automatycznie.

Użycie:

- do ograniczania ruchu do wybranego obszaru,
- do tworzenia lokalnych stref digi albo bramkowania.

### `Rate Limit Filter`

Ten filtr ogranicza, jak często pakiety od danego znaku albo wzorca znaku mogą przejść dalej.

Zasada działania:

- dla każdej reguły zliczany jest czas od ostatnio przepuszczonego pakietu,
- kolejny pakiet z tego samego dopasowania przed upływem limitu zostaje zablokowany.

Użycie:

- do uspokajania bardzo aktywnych stacji,
- do ochrony kanału RF przed nadmiarem powtarzanych ramek,
- do łagodnego ograniczania ruchu bez całkowitego odcinania źródła.

## Bloki docelowe

### `TX RF`

Cel nadający pakiet przez wskazany modem radiowy.

Użycie:

- lokalny digi,
- cross-band,
- przekazywanie między portami RF.

### `TX APRS-IS`

Cel wysyłający pakiet do APRS-IS.

Użycie:

- iGate,
- przekazanie lokalnych ramek aplikacji do Internetu APRS.

Ten cel jest ograniczony systemowo do obowiązkowego `Strict Filter`.

### `Black Hole`

Cel zapisujący przebieg bez nadawania pakietu dalej.

Użycie:

- diagnostyka,
- testy,
- obserwacja działania filtrów.

### `Action Drop`

Cel kończący regułę odrzuceniem pakietu.

Użycie:

- świadome blokowanie ruchu,
- czytelne rozdzielenie scenariuszy akceptacji i odrzucenia.

## Ograniczenia edytora

- Reguła ma zawsze jedno źródło i jeden cel.
- `Local TX` może prowadzić tylko do `TX APRS-IS` albo `Black Hole`.
- `TX APRS-IS` utrzymuje obowiązkowy `Strict Filter`.
- `TX RF` wymaga aktywnego `Path rule and DIGI guard`.
- `Duplicate Filter` może wystąpić tylko raz.
- `Distance Filter` może wystąpić tylko raz.
- `Rate Limit Filter` jest przeznaczony dla ścieżek kończących się na `TX RF`.

## Dobre praktyki budowy reguł

- Najpierw ustal źródło i cel, dopiero potem dodawaj filtry.
- Dla `RF -> RF` myśl najpierw o ochronie kanału, a dopiero potem o zasięgu.
- Dla `RF -> APRS-IS` pilnuj, żeby do Internetu trafiał tylko ruch, który rzeczywiście powinien tam wejść.
- Przy testach zaczynaj od `Black Hole`, aby zobaczyć przebieg bez emisji.
- Po zapisaniu sprawdzaj log wykonania reguły, bo pokazuje dokładnie, na którym kroku pakiet został przepuszczony albo odrzucony.
