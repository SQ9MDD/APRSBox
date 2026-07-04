# Reguły routingu pakietów

Ten ekran pokazuje reguły, przez które APRSBox kieruje pakiety pomiędzy wejściami i wyjściami. Reguła ma jedno źródło, opcjonalne filtry pośrodku oraz jeden cel.

Reguły są wykonywane od góry do dołu. Kolejność na liście ma znaczenie, dlatego aktywne reguły dla tego samego kierunku warto trzymać świadomie uporządkowane.

## Po co używa się reguł routingu

Reguły routingu służą do opisania, co ma się stać z pakietem APRS po odebraniu albo wygenerowaniu lokalnie przez APRSBox.

Typowe zastosowania:

- przekazanie ramek odebranych z RF do APRS-IS,
- digipeating z jednego portu RF na ten sam lub inny port RF,
- przekazanie lokalnie wygenerowanych ramek do APRS-IS,
- zapis wybranych ramek do logu bez dalszego nadawania,
- odrzucenie ramek, które nie powinny przejść dalej.

## Najczęstsze przypadki użycia

### `RF -> APRS-IS`

To najczęstszy wariant dla iGate. APRSBox odbiera pakiet z radia i po przejściu przez wymagany filtr systemowy przekazuje go do APRS-IS.

Tego wariantu używa się, gdy:

- chcesz publikować do APRS-IS lokalnie odebrane pakiety,
- chcesz odseparować różne porty RF i decydować, które z nich mają iść do Internetu,
- chcesz dodać własne warunki przyjęcia ramek już na wejściu RF przez odpowiedni dobór źródła.

### `RF -> RF`

To klasyczny przypadek digipeatera. Pakiet przychodzi z jednego portu RF i po przejściu przez zestaw filtrów jest nadawany ponownie przez RF.

Tego wariantu używa się, gdy:

- budujesz lokalny digi,
- chcesz robić cross-band albo port-to-port RF,
- chcesz powtarzać tylko wybrane typy ramek, znaki, obszary albo ścieżki.

W tym trybie kluczowy jest blok `Path rule and DIGI guard`, bo to on pilnuje ścieżki digi i podstawowych zasad powtarzania.

### `Local TX -> APRS-IS`

To wariant dla ramek generowanych przez sam APRSBox: beaconów, statusów, obiektów, itemów, biuletynów, wiadomości i pogody.

Tego wariantu używa się, gdy:

- chcesz, żeby lokalne emisje aplikacji trafiały do APRS-IS,
- chcesz uruchomić obiekty, biuletyny albo wiadomości bez bezpośredniego toru RF,
- chcesz rozdzielić logikę lokalnego nadawania od logiki ruchu przychodzącego z radia.

### `RF -> Black Hole` albo `Local TX -> Black Hole`

To wariant diagnostyczny i testowy. Pakiet przechodzi przez regułę, ale na końcu nie jest nadawany dalej.

Tego wariantu używa się, gdy:

- chcesz sprawdzić, czy filtr działa zgodnie z oczekiwaniem,
- chcesz przeanalizować przebieg pakietu bez emisji,
- chcesz tymczasowo obserwować ruch na danym wejściu.

## Źródła i cele

Źródło określa, skąd pakiet wchodzi do reguły.

- `Receiver RF` oznacza pakiety odebrane przez wybrany modem radiowy.
- `Local TX` oznacza ramki wygenerowane lokalnie przez APRSBox, na przykład beacon, status, pogodę, obiekty, itemy, biuletyny i wiadomości.

Cel określa, gdzie pakiet ma trafić na końcu reguły.

- `TX RF` nadaje pakiet przez wybrany modem radiowy.
- `TX APRS-IS` wysyła pakiet do APRS-IS.
- `Black Hole` zapisuje przebieg bez nadawania pakietu dalej.

`Local TX` może być kierowany tylko do APRS-IS albo do logu. Nie służy do ponownego wpuszczania lokalnych ramek na RF przez routing.

## Filtry i reguły pośrodku

Filtry działają kolejno. Jeżeli pakiet zostanie odrzucony przez filtr, dalsze kroki nie są wykonywane.

Najważniejsze typy:

- `Strict Filter` blokuje ramki z tokenami `TCPIP`, `TCPXX`, `NOGATE`, `RFONLY` oraz niepoprawne ramki third-party.
- `Path rule and DIGI guard` obsługuje ścieżkę digi i chroni przed powtarzaniem ramek, których ta stacja nie powinna powtarzać.
- `Duplicate Filter` działa jak viscous-delay: czeka krótko i odrzuca ramkę, jeżeli w tym czasie usłyszy jej powtórzenie.
- `Direct Only` przepuszcza tylko pakiety usłyszane bezpośrednio.
- `Callsign Filter`, `DIGI Filter`, `Packet Type Filter`, `Icon Filter` i `Distance Filter` zawężają ruch według źródła, użytego digi, typu pakietu, symbolu albo położenia.
- `Rate Limit Filter` ogranicza częstotliwość przepuszczania ramek dla znaków lub wzorców znaków.

Szczegółowy opis każdego bloku znajduje się w osobnym dokumencie:

[Szczegółowy opis bloków routingu](packet_routing_flow.pl.md)

## Ograniczenia systemowe

Reguły do `TX APRS-IS` są celowo uproszczone: aplikacja utrzymuje w nich obowiązkowy `Strict Filter`. To zabezpiecza przed wysłaniem do APRS-IS ramek, które powinny pozostać poza Internetem APRS.

Reguły do `TX RF` wymagają aktywnego kroku `Path rule and DIGI guard`. Dla takich reguł aplikacja porządkuje część kroków tak, aby najważniejsze zabezpieczenia RF znalazły się we właściwych miejscach.

Tylko jedna aktywna reguła może obsługiwać ten sam kierunek źródło-cel. Włączenie jednej reguły dla danej pary może wyłączyć inną aktywną regułę tej samej pary.

## Dobre praktyki

- Zacznij od prostej reguły i dopiero potem dodawaj filtry.
- Dla RF używaj rozsądnych ścieżek i unikaj niepotrzebnego powtarzania ramek.
- Dla APRS-IS nie obchodź filtrów chroniących przed `NOGATE`, `RFONLY` i niepoprawnym third-party.
- Testuj nowe reguły najpierw z celem `Black Hole`, jeżeli chcesz zobaczyć przebieg bez nadawania.
- Po zapisaniu reguły sprawdzaj log routingu w edytorze konkretnej reguły.
