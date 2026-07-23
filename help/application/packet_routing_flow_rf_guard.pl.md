# APRS-IS jako źródło — dwa Guardy

Flow `APRS-IS -> RF` służy do kontrolowanego przekazania wybranych ramek z APRS-IS na fizyczny interfejs radiowy. Celem może być wyłącznie aktywny interfejs TNC z obsługą TX. Interfejs APRS-IS ani odbiornik RX-only nie mogą być celem.

## Wymagana kolejność

`APRS-IS source -> APRS-IS Input Guard -> filtr default deny: znak + promień -> RF TX Guard -> TX RF`

Oba Guardy są automatycznie dodawane dla `APRS-IS -> RF`. Nie można ich usunąć, wyłączyć, ominąć, przestawić ani dodać drugi raz. Backend i runtime wymuszają tę samą ochronę również dla ręcznie zmienionych danych.

## Filtr znaku i promienia z domyślnym odrzucaniem

Filtr zawiera wyłącznie listę źródłowych znaków i promień. Oba warunki łączą się jako `AND`: źródło pakietu musi dokładnie odpowiadać jednemu z wpisanych znaków, a zdekodowana pozycja pakietu musi znajdować się w promieniu liczonym od współrzędnych skonfigurowanych w `My Station`.

Dopasowanie znaku jest ścisłe i obejmuje SSID. `SQ9MDD` pasuje wyłącznie do `SQ9MDD`, a `SQ9MDD-1` wyłącznie do `SQ9MDD-1`. Symbole wieloznaczne nie są obsługiwane. Każdy znak wpisz w osobnej linii.

Pusta konfiguracja jest poprawnym `default deny`. Odrzucane są również pakiety bez zdekodowanej pozycji oraz wszystkie pakiety, gdy `My Station` nie ma prawidłowych współrzędnych.

## APRS-IS Input Guard

Pierwszy Guard wykonuje walidację APRS i q-construct, ochronę pętli, blokady `NOGATE`, `RFONLY` i `TCPXX` oraz wstępną, znormalizowaną kontrolę duplikatów między RF i APRS-IS. Sam `TCPIP` nie jest automatycznie blokowany.

## RF TX Guard

Końcowy Guard jest umieszczony bezpośrednio przed `TX RF`. Odpowiada za viscous delay, ponowną kontrolę duplikatów po opóźnieniu, limity token bucket per-flow i per-source, gotowość celu, third-party encapsulation oraz kontrolę długości AX.25. Internetowa ścieżka wejściowa jest usuwana przed TX.

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
