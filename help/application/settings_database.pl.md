# Konserwacja bazy danych

Ten panel pokazuje stan pamięci SQLite i udostępnia ręczne akcje porządkowe. Logi zdarzeń są przycinane automatycznie po północy; `VACUUM` i reset historii runtime pozostają ręczne.

## Diagnostyka

- Rozmiary pliku, WAL i SHM pokazują fizyczną przestrzeń używaną przez SQLite.
- `Przydzielony rozmiar bazy`, `Miejsce do odzyskania` i `Geometria stron` są obliczane ze stron SQLite.
- `Kontrola integralności` jest wynikiem `PRAGMA quick_check`. Każdy wynik inny niż `ok` trzeba wyjaśnić przed konserwacją.
- `Zalecenie VACUUM` porównuje wolne miejsce z progiem pokazanym w panelu.
- Lista tabel runtime i suma wierszy pokazują dokładny bieżący zakres resetu.

## Uruchom VACUUM

`VACUUM` przebudowuje plik SQLite, aby nieużywane strony mogły wrócić do systemu plików. Operacja może potrwać i tymczasowo zablokować bazę. Przed uruchomieniem wszystkie interfejsy TNC muszą być wyłączone.

## Reset logów/danych runtime

Reset czyści historię operacyjną, między innymi logi zdarzeń, odebrany ruch, stan runtime routingu, statystyki APRS-IS, cache runtime WX, stan radaru i agregaty warunków pasmowych.

Nie usuwa konfiguracji TNC ani routingu, ustawień stacji i WX, treści APRS, źródeł map, użytkowników ani historii wiadomości APRS. Przed resetem wszystkie interfejsy TNC muszą być wyłączone.
