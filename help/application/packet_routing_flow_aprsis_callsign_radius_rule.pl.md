# Reguła znaku i promienia APRS-IS

Ta obowiązkowa reguła systemowa jest jawną listą zezwoleń dla ruchu innego niż wiadomości w restrykcyjnym flow `APRS-IS → RF`. Działa jako default deny: pakiet przechodzi dalej tylko wtedy, gdy zarówno jego dokładny znak źródłowy, jak i zdekodowana pozycja pasują do konfiguracji. Wiadomości skierowane do lokalnych stacji i zatwierdzone przez wcześniejszą Regułę dostarczania wiadomości omijają tę regułę.

## Warunki

Warunki łączą się przez `AND`:

1. Źródło pakietu dokładnie odpowiada jednemu znakowi wpisanemu na listę.
2. Pozycja pakietu znajduje się w ustawionym promieniu liczonym od współrzędnych w `My Station`.

Pasujący znak bez pasującej pozycji zostanie odrzucony. Tak samo zostanie odrzucona pozycja znajdująca się w promieniu, jeśli znak źródłowy nie występuje na liście.

## Znaki źródłowe

- Wpisz jeden znak w każdym wierszu.
- Wielkość liter nie ma znaczenia, ale poza tym dopasowanie jest ścisłe i obejmuje SSID.
- `SQ9MDD` pasuje tylko do `SQ9MDD`.
- `SQ9MDD-1` pasuje tylko do `SQ9MDD-1`.
- Symbole wieloznaczne nie są obsługiwane.
- Znak musi być prawidłowym adresem AX.25: od 1 do 6 liter lub cyfr z opcjonalnym SSID od `0` do `15`.
- Można skonfigurować maksymalnie 50 znaków.

## Promień

GUI przyjmuje promień od `0,1` do `1000 km` z krokiem `0,1 km`. Odległość jest liczona od współrzędnych stacji skonfigurowanych w `My Station`, a nie od modemu odbiorczego ani pozycji innego pakietu.

Pakiet zostanie odrzucony, gdy:

- nie można zdekodować jego pozycji APRS,
- `My Station` nie ma prawidłowych współrzędnych,
- pozycja znajduje się poza promieniem.

## Pusta i niepełna konfiguracja

Lista znaków i promień muszą być wypełnione razem albo oba pola muszą pozostać puste. Nie można zapisać konfiguracji z wypełnionym tylko jednym z tych pól.

Pozostawienie obu pól pustych jest prawidłowe i celowo odrzuca wszystkie pakiety. Dzięki temu nieskonfigurowana reguła pozostaje bezpieczna.

## Położenie w flow

Reguła jest automatycznie wstawiana i zarządzana za `Regułą dostarczania wiadomości APRS-IS`, a przed `Regułą bezpieczeństwa TX APRS-IS → RF`. Nie można jej usunąć, wyłączyć, powielić ani przesunąć. Do tego flow nie można również dodawać opcjonalnych filtrów.

## Nawigacja

[Obowiązkowe reguły bezpieczeństwa APRS-IS → RF](packet_routing_flow_rf_guard.pl.md)

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
