# Obowiązkowe reguły bezpieczeństwa APRS-IS → RF

Flow `APRS-IS -> RF` służy do kontrolowanego przekazania wybranych ramek z APRS-IS na fizyczny interfejs radiowy. Celem może być wyłącznie aktywny interfejs TNC z obsługą TX. Interfejs APRS-IS ani odbiornik RX-only nie mogą być celem.

## Wymagana kolejność

`Źródło APRS-IS -> Reguła bezpieczeństwa wejścia APRS-IS -> Reguła znaku i promienia APRS-IS -> Reguła bezpieczeństwa TX APRS-IS → RF -> TX RF`

Wszystkie cztery reguły są automatycznie dodawane dla `APRS-IS → RF`. Nie można ich usunąć, wyłączyć, ominąć, przestawić ani dodać drugi raz. Do tego restrykcyjnego flow nie można dodać żadnego opcjonalnego filtra. Backend i runtime wymuszają tę samą ochronę również dla ręcznie zmienionych danych.

## Reguła znaku i promienia APRS-IS

Filtr zawiera wyłącznie listę źródłowych znaków i promień. Oba warunki łączą się jako `AND`: źródło pakietu musi dokładnie odpowiadać jednemu z wpisanych znaków, a zdekodowana pozycja pakietu musi znajdować się w promieniu liczonym od współrzędnych skonfigurowanych w `My Station`.

Dopasowanie znaku jest ścisłe i obejmuje SSID. `SQ9MDD` pasuje wyłącznie do `SQ9MDD`, a `SQ9MDD-1` wyłącznie do `SQ9MDD-1`. Symbole wieloznaczne nie są obsługiwane. Każdy znak wpisz w osobnej linii.

Pusta konfiguracja jest poprawnym `default deny`. Odrzucane są również pakiety bez zdekodowanej pozycji oraz wszystkie pakiety, gdy `My Station` nie ma prawidłowych współrzędnych.

## Reguła bezpieczeństwa wejścia APRS-IS

Pierwszy Guard wykonuje walidację APRS i q-construct, ochronę pętli, blokady `NOGATE`, `RFONLY` i `TCPXX` oraz wstępną, znormalizowaną kontrolę duplikatów między RF i APRS-IS. Sam `TCPIP` nie jest automatycznie blokowany.

## Reguła bezpieczeństwa TX APRS-IS → RF

Końcowy Guard jest umieszczony bezpośrednio przed `TX RF`. Odpowiada za viscous delay, ponowną kontrolę duplikatów po opóźnieniu, limity token bucket per-flow i per-source, gotowość celu, third-party encapsulation oraz kontrolę długości AX.25. Internetowa ścieżka wejściowa jest usuwana przed TX.

Domyślne parametry to:

- viscous delay: `5 s`,
- per flow: `6 ramek/min`, burst `3`,
- per source callsign: `2 ramki/min`, burst `2`,
- okno duplikatów: `30 s`.

Podczas viscous delay ramka pozostaje wyłącznie w pamięci. Kopia odebrana lokalnie z RF anuluje oczekującą transmisję, a restart nie odtwarza pending.

## Transmisja i statystyki

Tekst z APRS-IS jest dekodowany jako Unicode, ale AX.25 APRS w RF używa 7-bitowego ASCII. Przed enkapsulacją typowe znaki są transliterowane (`°` na `deg`, `µ`/`μ` na `u`, typograficzne myślniki i cudzysłowy na ASCII), a nieobsługiwane znaki są zastępowane przez `?`. Kontrola rozmiaru i kodowanie KISS pracują dokładnie na tym samym, oczyszczonym payloadzie.

Internetowa ścieżka jest usuwana, a ramka otrzymuje poprawną enkapsulację APRS third-party. Używana jest ścieżka RF skonfigurowana w celu; pusta ścieżka oznacza transmisję direct. Zadanie trafia do istniejącej kolejki RF/KISS.

Ruch ma osobne liczniki `APRS-IS -> RF` i nie zwiększa statystyk DIGI ani fizycznego RX TNC.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
