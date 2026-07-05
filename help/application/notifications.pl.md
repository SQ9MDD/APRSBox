# Powiadomienia

Ta zakładka służy do skonfigurowania zewnętrznych powiadomień wysyłanych przez APRSBox. Powiadomienia działają w dwóch krokach: najpierw definiujesz transport, a potem włączasz typy zdarzeń, które mają być wysyłane.

## Transporty

Transport określa, dokąd APRSBox wysyła zdarzenie.

- `Webhook` wysyła zdarzenie jako HTTP `POST` z JSON-em na podany URL.
- `Telegram` wysyła wiadomość przez bota Telegram do wskazanego `Chat ID`.
- Przy zwykłej wysyłce zdarzeń używane są tylko transporty z zaznaczonym `Enabled`.
- Przycisk testu wysyła zdarzenie `APRSBox notification test` i zapisuje wynik testu w konfiguracji transportu.

Dla webhooka możesz ustawić `Secret header name` i `Secret token`. Jeżeli oba pola są wypełnione, APRSBox doda taki nagłówek HTTP do żądania.

`Timeout` jest liczony w sekundach. Dozwolony zakres to od `1` do `60`, a domyślna wartość to `5`.

Przy edycji istniejącego transportu puste pole sekretu zostawia dotychczasowy sekret bez zmian.

## Ustawienia powiadomień

- `Enable APRS message notifications` włącza powiadomienia o przychodzących wiadomościach APRS.
- `Include message content` decyduje, czy treść wiadomości APRS ma być dołączona do powiadomienia.
- `Enable radar notifications` włącza reguły radaru stacji.
- `Ignored radar patterns` pozwala wykluczyć stacje z radaru. Wzorce można rozdzielać przecinkami albo nowymi liniami. Obsługiwany jest znak `*`.

Wyłączenie powiadomień radarowych czyści zapamiętany stan blokad powtórzeń oraz log zdarzeń radaru.

## Reguły radaru

Reguła radaru wykrywa stacje pasujące do wzorca znaku i opcjonalnego limitu odległości od `My Station`.

- `Radar rule` to znak lub wzorzec znaku, na przykład `SQ6ODL-*`, `SR*` albo `*`.
- `Distance (m)` to maksymalna odległość od współrzędnych lokalnej stacji.
- Wartość `0` oznacza brak limitu odległości.
- Jeżeli odległość jest większa niż `0`, stacja bez znanych współrzędnych nie spełni reguły.

Radar wysyła powiadomienie tylko wtedy, gdy stacja wchodzi w zakres reguły. Dopóki stacja pozostaje w zakresie, kolejne powiadomienia są blokowane. Blokada znika dopiero wtedy, gdy stacja wyjdzie z zakresu albo jej pozycja wygaśnie z widocznych danych.

Lokalna stacja oraz aktywna stacja pogodowa APRSBox są pomijane automatycznie.

## Log zdarzeń radaru

Log pokazuje ostatnie zmiany stanu radaru: wysłanie powiadomienia, założenie blokady powtórki oraz zdjęcie blokady po wyjściu stacji z zakresu.
