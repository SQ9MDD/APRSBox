# Źródła map

Ten panel zarządza źródłami kafelków używanymi przez mapy APRSBox, ich kolejnością, źródłem domyślnym i opcjonalnym lokalnym cache.

## Lista źródeł

- Strzałki zmieniają kolejność źródeł w selektorze mapy.
- Gwiazdka ustawia włączone źródło jako domyślne.
- Ołówek otwiera źródło do edycji.
- Kosz usuwa źródło. Nie można usunąć jedynego źródła ani źródła domyślnego.
- Miotła czyści lokalnie zapisane kafelki bez usuwania konfiguracji źródła.

## Pola źródła

- `Nazwa` jest etykietą widoczną w selektorze mapy.
- `Szablon URL` musi być standardowym adresem kafelków Leaflet ze znacznikami `{z}`, `{x}` i `{y}`, na przykład `https://server/{z}/{x}/{y}.png`.
- `Atrybucja` zawiera wymagane oznaczenie dostawcy mapy.
- `Min. zoom` i `Maks. zoom` ograniczają dostępny zakres przybliżenia.
- `Notatki` są zapisywane przy źródle dla administratorów.
- `Włączone` udostępnia źródło na mapach.
- `Włącz lokalny cache/proxy` kieruje zapytania o kafelki przez APRSBox i zapisuje pobrane kafelki lokalnie.
- `Ustaw jako domyślne` wybiera to źródło, gdy mapa nie ma innego zapisanego wyboru.

Panel obsługuje tylko standardowe rastrowe źródła kafelków Leaflet. Przed włączeniem sprawdź limity, zasady atrybucji i zgodę na cache/proxy. Punktem startowym może być [lista dostawców Switch2OSM](https://switch2osm.org/providers/#Allows-free-usage).
