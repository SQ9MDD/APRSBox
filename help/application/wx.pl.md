# WX

Zakładka WX konfiguruje lokalną stację pogodową APRSBox. Dane są pobierane ze źródeł HTTP, normalizowane do formatu APRS complete WX i wysyłane jako lokalna ramka pogodowa.

## Kolejność konfiguracji

- Ustaw znak stacji w `My Settings`.
- Wybierz osobny `WX SSID` dla stacji pogodowej.
- Dodaj źródło danych w `WX data sources`.
- Przetestuj źródło albo uruchom `Discover source`.
- Przypisz źródła i identyfikatory w `WX data mapping`.
- Wykonaj test odczytu dla wymaganych parametrów.
- Włącz `Enable WX`, zapisz konfigurację i sprawdź `WX TX Log`.

## Global WX configuration

- `Callsign` jest pobierany z `My Settings` i nie jest edytowany w tej zakładce.
- `WX SSID` tworzy znak stacji pogodowej, na przykład `SQ9XYZ-13`. SSID używany przez główną stację nie jest dostępny dla WX.
- `Interface` wybiera TNC, przez który APRSBox nada ramkę, albo opcję wysyłki przez wszystkie aktywne interfejsy.
- `Path` ustawia ścieżkę APRS dla ramki WX. Puste pole albo `RFONLY` traktowane jest jak emisja bez digipeaterów.
- Dla pustej ścieżki i `RFONLY` dostępne są krótsze interwały. Dla ścieżki routowanej, na przykład `WIDE2-2`, lista interwałów jest ograniczona do dłuższych wartości.
- `Latitude` i `Longitude` określają położenie stacji pogodowej. Przycisk `Get location` pozwala wskazać punkt na mapie.
- `Refresh / TX interval` określa cykl odczytu danych i planowania ramki WX.
- `Allow cached values on failure` pozwala użyć ostatniej poprawnej wartości, gdy źródło chwilowo nie odpowiada.
- `Default max cache age (s)` określa, jak długo wartość z cache może być uznana za użyteczną.

`Refresh now` odczytuje skonfigurowane mapowania i odświeża cache. `Send now` zapisuje konfigurację z formularza, robi ręczny refresh i dopiero potem kolejkuje ramkę WX do nadania.

## WX data mapping

Mapowanie łączy parametr APRS WX ze źródłem danych i identyfikatorem w tym źródle.

Parametry wymagane do podstawowej ramki WX to:

- `Wind direction` w stopniach,
- `Wind speed` w mph,
- `Temperature` w stopniach Fahrenheita.

Parametry opcjonalne obejmują poryw wiatru, opad z ostatniej godziny, opad z 24 godzin, opad od północy, wilgotność, ciśnienie, śnieg, nasłonecznienie, licznik deszczu, poziom wody, napięcie baterii i promieniowanie.

W kolumnach `Raw value` i `Normalized` widać wartość odczytaną ze źródła oraz wartość po przeliczeniu do jednostki APRS. Status `LIVE` oznacza świeży odczyt, `CACHED` oznacza użycie ostatniej poprawnej wartości, a `MISSING`, `STALE` albo `ERROR` wymagają sprawdzenia źródła, identyfikatora albo jednostki.

## WX data sources

- `Home Assistant` używa adresu API Home Assistant i wymaga `Bearer token`.
- `Domoticz` używa API Domoticz i obsługuje brak autoryzacji albo `Basic auth`.
- `Base URL` powinien wskazywać główny adres systemu, na przykład `http://127.0.0.1:8123`.
- `Timeout (s)` ogranicza czas oczekiwania na odpowiedź źródła.
- `Verify TLS certificate` powinno pozostać włączone dla prawidłowych certyfikatów HTTPS.
- `Enable source` decyduje, czy źródło może być używane w odczytach.

Ikona testu sprawdza połączenie ze źródłem. Ikona discovery pobiera listę wykrytych encji albo urządzeń, co ułatwia wpisanie poprawnego `Identifier` w mapowaniu.

## WX TX Log

Log pokazuje ostatnie zadania WX: czas, typ, status, interfejs, liczbę prób, błąd oraz podgląd ramki TNC2. Jeżeli ramka nie wychodzi, najpierw sprawdź wymagane mapowania, położenie, włączony WX, aktywny TNC i komunikat błędu w logu.
