# Wiadomości APRS

Ta zakładka służy do rozmów APRS zapisanych lokalnie w bazie SQLite. Lista po lewej pokazuje rozmówców, a panel po prawej pokazuje wybrany wątek i formularz wysyłki.

## Rozmowy

- `Start new conversation` przyjmuje znak APRS w formie `CALL` albo `CALL-SSID`.
- Dozwolony jest znak do 6 znaków bazowych i opcjonalny SSID `0-15`, na przykład `SP9XYZ-7`.
- Obsługiwane są też wybrane destynacje usługowe APRS, takie jak `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` czy `CQ`.
- Otwarcie rozmowy oznacza przychodzące wiadomości z tego wątku jako przeczytane.
- Ikona `Messages` w menu bocznym zmienia się, gdy są nieprzeczytane wiadomości.

Wiersz rozmowy pokazuje także, czy stacja była ostatnio słyszana. Zielony stan oznacza świeży odbiór, ostrzegawczy starszy odbiór, a brak wpisu oznacza brak niedawnej ramki w lokalnej historii ruchu.

## Wysyłanie

- Treść wiadomości APRS ma limit `67` drukowalnych znaków ASCII.
- Znaki narodowe i znaki sterujące są blokowane, bo klasyczny format wiadomości APRS jest krótkim polem ASCII.
- Pole `Path` ustawia ścieżkę radiową dla wysyłki. Jeżeli pole pozostaje puste, używana jest domyślna ścieżka stacji z ustawień beaconu.
- Ścieżka jest zapamiętywana dla rozmowy i może być użyta także przez automatyczne ACK.

Zwykła wiadomość dostaje numer wiadomości APRS i oczekuje na `ACK` albo `REJ` od stacji zdalnej.

## Statusy

- `Queued` oznacza, że wiadomość czeka w kolejce outbound.
- `Sent` oznacza, że ramka została nadana.
- `Sent X/Y` pokazuje numer próby i limit prób dla numerowanej wiadomości.
- `ACK` oznacza potwierdzenie odbioru przez stację zdalną.
- `Rejected (REJ)` oznacza odrzucenie przez stację zdalną.
- `No ACK` oznacza, że po oknie ponowień nie odebrano potwierdzenia.

Dla zwykłych wiadomości APRSBox planuje automatyczne ponowienia po kolejnych próbach. Po wyczerpaniu prób nieudana wiadomość może zostać wysłana ponownie ręcznie przyciskiem `No ACK`.

## Zapytania APRS

Jeżeli tekst zaczyna się od `?`, wiadomość jest traktowana jako zapytanie APRS. Takie ramki są wysyłane bez numeru wiadomości i nie używają automatycznego okna ACK/retry jak zwykłe wiadomości.

APRSBox rozpoznaje i automatycznie odpowiada na przychodzące zapytania:

- `?APRS`,
- `?APRSP`,
- `?APRSS`,
- `?APRSD`,
- `?DX`,
- `?APRSV`,
- `?VER`.

Przychodzące numerowane wiadomości i zapytania są automatycznie potwierdzane ramką `ack`.
