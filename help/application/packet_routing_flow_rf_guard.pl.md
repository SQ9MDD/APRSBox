# APRS-IS jako źródło i RF Guard

Flow `APRS-IS -> RF` służy do kontrolowanego przekazania wybranych ramek z APRS-IS na fizyczny interfejs radiowy. Celem może być wyłącznie aktywny interfejs TNC z obsługą TX. Interfejs APRS-IS ani odbiornik RX-only nie mogą być celem.

## Wymagana kolejność

`APRS-IS source -> RF Guard -> jawne reguły przepuszczające -> TX RF`

`RF Guard` jest automatycznie dodawany po wyborze źródła APRS-IS. Nie można go usunąć, wyłączyć, ominąć ani dodać drugi raz. Backend i runtime wymuszają ochronę również dla ręcznie zmienionych danych.

## Jawne reguły przepuszczające

Wszystkie reguły są inkluzywne. Warunki w jednej regule łączą się jako `AND`, a osobne reguły jako `OR`. Dostępne warunki wykorzystują dane już dekodowane przez istniejący parser i filtry: typ pakietu, znak źródłowy, destination, adresat wiadomości, nazwa obiektu, symbol oraz obszar odległości.

Brak reguł jest poprawną konfiguracją i oznacza `default deny`: flow można zapisać i aktywować, ale nie przekaże żadnej ramki.

## Ochrona RF

Guard zawsze wykonuje walidację APRS i q-construct, ochronę pętli, blokady `NOGATE`, `RFONLY` i `TCPXX`, normalizację duplikatów między RF i APRS-IS, viscous delay, ponowną kontrolę po opóźnieniu, limity tempa, third-party encapsulation i kontrolę długości AX.25. Sam `TCPIP` nie jest automatycznie blokowany — internetowa ścieżka wejściowa jest usuwana przed TX.

Domyślne parametry to:

- viscous delay: `5 s`,
- per flow: `6 ramek/min`, burst `3`,
- per source callsign: `2 ramki/min`, burst `2`,
- okno duplikatów: `30 s`.

Podczas viscous delay ramka pozostaje wyłącznie w pamięci. Kopia odebrana lokalnie z RF anuluje oczekującą transmisję, a restart nie odtwarza pending.

## Transmisja i statystyki

Po przejściu kontroli oryginalny payload zostaje zachowany, internetowa ścieżka usunięta, a ramka otrzymuje poprawne APRS third-party encapsulation. Używana jest ścieżka RF skonfigurowana w celu; pusta ścieżka oznacza transmisję direct. Zadanie trafia do istniejącej kolejki RF/KISS.

Ruch ma osobne liczniki `APRS-IS -> RF` i nie zwiększa statystyk DIGI ani fizycznego RX TNC.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
