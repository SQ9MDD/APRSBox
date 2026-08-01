# Identyfikacja urządzeń APRS

APRSBox używa tej bazy do rozpoznawania oprogramowania i sprzętu APRS na podstawie wartości docelowych `TOCALL` oraz identyfikatorów Mic-E. Wynik pojawia się w szczegółach stacji i statystykach urządzeń.

## Aktywne źródło danych

APRSBox preferuje poprawny lokalny cache. Jeżeli go nie ma, używa migawki dołączonej do aplikacji.

- `Status` informuje, czy działa cache, czy dołączona migawka zapasowa.
- `Aktywne źródło` pokazuje dane aktualnie używane do wyszukiwania.
- `Czas wygenerowania` pochodzi z zestawu danych identyfikacyjnych.
- `Ostatnia udana aktualizacja` zapisuje czas ostatniego zakończonego pobrania.
- `Lokalny cache` i `Aktualizacja lokalnego cache` opisują pobrany plik.
- `Ostatni błąd aktualizacji` pozostaje widoczny po nieudanej próbie.

## Aktualizacja

`Aktualizuj teraz` pobiera nowy zestaw, sprawdza jego strukturę i zastępuje lokalny cache dopiero po udanej walidacji. Błąd pobierania nie usuwa użytecznej migawki dołączonej ani wcześniejszego poprawnego cache.

Aktualizacja wymaga dostępu do sieci i może ją uruchomić tylko administrator albo operator.
