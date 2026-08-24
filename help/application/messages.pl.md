# Wiadomości APRS

Ta zakładka służy do rozmów APRS zapisanych lokalnie w bazie SQLite. Lista po lewej pokazuje rozmówców, a panel po prawej pokazuje wybrany wątek i formularz wysyłki.

## Rozmowy

- `Start new conversation` przyjmuje znak APRS w formie `CALL` albo `CALL-SSID`.
- Dozwolony jest znak do 6 znaków bazowych i opcjonalny SSID `0-15`, na przykład `SP9XYZ-7`.
- Obsługiwane są też wybrane destynacje usługowe APRS, takie jak `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` czy `CQ`.
- Otwarcie rozmowy oznacza przychodzące wiadomości z tego wątku jako przeczytane.
- Ikona `Messages` w menu bocznym zmienia się, gdy są nieprzeczytane wiadomości.

Wiersz rozmowy pokazuje także, czy stacja była ostatnio słyszana. Zielony stan oznacza świeży odbiór, ostrzegawczy starszy odbiór, a brak wpisu oznacza brak niedawnej ramki w lokalnej historii ruchu.

## Ustawienia wiadomości

Blok `Ustawienia wiadomości` znajduje się pod panelem rozmów:

- `Domyślna ścieżka` jest używana dla nowych rozmów, wiadomości grupowych i automatycznych odpowiedzi APRS.
- `Odbieraj wiadomości dla każdego SSID mojego znaku` pozwala wyświetlać wiadomości skierowane do innych SSID tego samego znaku bazowego. Tylko dokładny skonfigurowany `CALL-SSID` otrzymuje `ACK` lub automatyczną odpowiedź.
- `Grupy RF` określają wspólne adresy wiadomości odbierane z interfejsów radiowych.
- `Grupy APRS-IS` określają wspólne adresy wiadomości odbierane z APRS-IS. APRSBox automatycznie dopisuje je do filtra połączenia `g/...`, razem z włączonymi grupami alarmowymi.

Przy pierwszym użyciu obie listy są identyczne i zawierają `ALL`, `QST` i `CQ`. W istniejącej instalacji bez osobnego ustawienia APRS-IS jego lista jest kopiowana z zapisanej listy RF. Po zapisaniu obie listy można zmieniać niezależnie; zapisane puste pole pozostaje puste.

Grupy wpisuje się w jednym polu, oddzielając je przecinkami, na przykład `CQ, QST, ALL, WAW, BEM`. Spacje wokół nazw są usuwane, litery zamieniane na wielkie, a duplikaty pomijane. Każda nazwa musi zawierać od `1` do `9` znaków `A-Z` lub `0-9`. Puste pozycje, znaki specjalne, wewnętrzne spacje oraz adresy zaczynające się od `BLN` są odrzucane.

## Rozmowy grupowe

- Rozmowa grupowa powstaje wyłącznie dla adresata znajdującego się na liście odpowiadającej źródłu ramki: `Grupy RF` albo `Grupy APRS-IS`.
- Wiadomość do niezdefiniowanej grupy, na przykład `BEM`, jest ignorowana: nie tworzy rozmowy, wpisu w historii, stanu nieprzeczytanego, powiadomienia ani `ACK`.
- Kluczem rozmowy jest adres grupy, na przykład `WAW`, a nie znak nadawcy. Wiadomości od wielu stacji trafiają do jednego chronologicznego wątku `WAW`.
- Nad każdym dymkiem grupowym widoczny jest rzeczywisty nadawca, na przykład `SQ5WLA-9`. Własna wiadomość jest podpisana `Ty · CALL-SSID`.
- Wiadomość wysłana przez APRSBox do grupy jest nadawana jeden raz, bez numeru wiadomości, bez oczekiwania na `ACK` i bez automatycznych ponowień.
- APRSBox nigdy nie potwierdza wiadomości grupowej, nawet gdy urządzenie nadawcze dołączyło do niej numer wiadomości.
- Usunięcie grupy z ustawień zatrzymuje odbiór nowych wiadomości do tej grupy, ale nie usuwa istniejącej historii rozmowy.

Grupa nie jest stacją, dlatego wątek grupowy nie pokazuje stanu „ostatnio słyszana”. Adresy biuletynów `BLN...` są obsługiwane oddzielnie i nie mogą być dodawane jako zwykłe grupy wiadomości.

## Wysyłanie

- Treść wiadomości APRS ma limit `67` drukowalnych znaków ASCII.
- Znaki narodowe i znaki sterujące są blokowane, bo klasyczny format wiadomości APRS jest krótkim polem ASCII.
- Pole `Path` ustawia ścieżkę radiową dla wysyłki. Jeżeli pole pozostaje puste, używana jest ścieżka z pola `Domyślna ścieżka` w ustawieniach wiadomości.
- Ścieżka jest zapamiętywana dla rozmowy i może być użyta także przez automatyczne ACK.

Zwykła wiadomość w rozmowie bezpośredniej dostaje numer wiadomości APRS i oczekuje na `ACK` albo `REJ` od stacji zdalnej. Wiadomości grupowe używają opisanych wyżej zasad bez ACK i retry.

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

Przychodzące numerowane wiadomości i zapytania są automatycznie potwierdzane ramką `ack` tylko wtedy, gdy są skierowane dokładnie do skonfigurowanego lokalnego `CALL-SSID`. Wiadomości grupowe i wiadomości do innych SSID lokalnego znaku nie są potwierdzane ani obsługiwane przez automatyczne odpowiedzi.
