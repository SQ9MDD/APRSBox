# Reguły routingu pakietów

Ten ekran pokazuje reguły, przez które APRSBox kieruje pakiety pomiędzy wejściami i wyjściami. Reguła ma jedno źródło, opcjonalne filtry pośrodku oraz jeden cel.

Reguły są wykonywane od góry do dołu. Kolejność na liście ma znaczenie, dlatego aktywne reguły dla tego samego kierunku warto trzymać świadomie uporządkowane.

## Kiedy używać reguł routingu

Reguły routingu służą do opisania, co ma się stać z pakietem APRS po odebraniu albo wygenerowaniu lokalnie przez APRSBox.

Typowe zastosowania:

- przekazanie ramek odebranych z RF do APRS-IS,
- digipeating z jednego portu RF na ten sam lub inny port RF,
- przekazanie lokalnie wygenerowanych ramek do APRS-IS,
- zapis wybranych ramek do logu bez dalszego nadawania,
- odrzucenie ramek, które nie powinny przejść dalej.

## Źródła i cele

Źródło określa, skąd pakiet wchodzi do reguły.

- `Receiver RF` oznacza pakiety odebrane przez wybrany modem radiowy.
- `Local TX` oznacza ramki wygenerowane lokalnie przez APRSBox, na przykład beacon, status, pogodę, obiekty, itemy, biuletyny i wiadomości.

Cel określa, gdzie pakiet ma trafić na końcu reguły.

- `TX RF` nadaje pakiet przez wybrany modem radiowy.
- `TX APRS-IS` wysyła pakiet do APRS-IS.
- `Black Hole` zapisuje przebieg bez nadawania pakietu dalej.
- `Action Drop` kończy regułę odrzuceniem pakietu.

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
