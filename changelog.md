# Changelog

## 1.4.72.DEV - 15.04.2026

### Added
- W formularzach `Objects` i `Bulletins / Announcements` dodano pole `Valid until (UTC)` jako date picker z przyciskiem czyszczenia daty.
- Dodano nowe pole danych `valid_until_utc` w tabelach `aprs_objects` i `bulletins` (schema + migracja dla istniejących instalacji).
- Dodano walidację backendu dla daty ważności w formacie `YYYY-MM-DD`.

### Changed
- Scheduler obiektów i biuletynów sprawdza teraz `valid_until_utc` w UTC i automatycznie wyłącza rekord (`is_enabled = 0`) po przekroczeniu daty.
- Runtime outbound przed wysyłką dodatkowo sprawdza datę ważności dla już zakolejkowanych zadań (`object`/`bulletin`) i pomija wysyłkę, jeżeli rekord wygasł.
- Gdy `valid_until_utc` jest puste, działanie pozostaje bez zmian (dotychczasowy tryb pracy bez ograniczenia datą).
- W głównym widoku `Logs` ukryto wpisy kategorii `digi_flow_runtime` na poziomie `INFO`, aby odseparować techniczny szum ruchowy od zdarzeń administracyjnych i konfiguracyjnych.

### Fixed
- Zabezpieczono przypadek opóźnionej wysyłki: rekord może zostać wyłączony również na etapie worker-a TX, nie tylko na etapie harmonogramu.
- Uzupełniono tłumaczenia (`en`/`pl`/`tlh`) dla nowych etykiet i komunikatów związanych z datą ważności.
- Ujednolicono logowanie nieudanych prób logowania: do `event_logs` trafiają teraz również próby z pustym loginem i/lub hasłem.
- Dodano test regresyjny potwierdzający, że główny `Logs` pomija `digi_flow_runtime INFO`, ale nadal pokazuje wpisy ostrzegawcze (`WARNING`) i zdarzenia `auth`.

### Removed
- Brak zmian.

## 1.4.71.DEV - 14.04.2026

### Added
- W `Settings` dodano nowy panel `Map sources` do konfiguracji klasycznych źródeł kafelków Leaflet.
- Dodano model danych `map_sources` (DB) z polami: `name`, `url_template`, `attribution`, `min_zoom`, `max_zoom`, `subdomains`, `api_key`, `enabled`, `is_default`, `sort_order`, `notes`.
- Dodano operacje konfiguracji źródeł mapy: dodawanie, edycja, usuwanie, ustawianie źródła domyślnego i zmianę kolejności.
- Dodano walidacje backendowe i frontendowe dla konfiguracji map (`Name`, `URL template`, tokeny `{z}/{x}/{y}`, zoomy, reguły default/enabled).
- Dodano testy regresyjne dla nowego modelu map sources i deterministycznego budowania URL kafelków.

### Changed
- Bazowa warstwa mapy (`tile layer`) jest teraz pobierana z konfiguracji zapisanej w DB, zamiast z hardcodowanych wartości runtime.
- Konfiguracja aktywnego źródła mapy jest używana spójnie w widokach `Map`, `Station detail` oraz pickerach lokalizacji (`Station`, `WX`, `Objects/Items`).
- Rozszerzono payload mapy o `tile_min_zoom`, `tile_max_zoom` i `tile_subdomains`; frontend Leaflet używa tych wartości przy tworzeniu warstwy kafelków.
- Górny blok podsumowania domyślnego źródła w panelu `Map sources` został usunięty, a sam panel skompaktowany wizualnie.
- W tabeli `Map sources` usunięto kolumnę `URL template` dla bardziej zwartego widoku listy.
- Formularz `Map sources` został uproszczony do pól: `Name`, `URL template`, `Attribution`, `Min zoom`, `Max zoom`, `Notes`, `Enabled`, `Set as default`.
- Usunięto z formularza pola `Subdomains`, `API key` i ręczny `Sort order`; kolejność źródeł jest teraz zmieniana strzałkami `góra/dół` w tabeli.
- Nowe rekordy źródeł map są dopisywane na końcu listy.

### Fixed
- Zabezpieczono migrację `map_sources`, aby po aktualizacji zawsze istniało dokładnie jedno aktywne źródło domyślne.
- Zachowano ciągłość działania mapy po wdrożeniu: dotychczasowa konfiguracja kafelków jest automatycznie przenoszona jako pierwszy wpis domyślny.
- Utrzymano deterministyczne URL kafelków (bez cache-bustingu), dzięki czemu wykorzystywana jest standardowa pamięć podręczna HTTP przeglądarki.
- Edycja przez uproszczony formularz nie nadpisuje istniejących wartości technicznych `subdomains`, `api_key` i `sort_order` w DB.

### Removed
- Brak zmian.

## 1.4.70.DEV - 14.04.2026

### Added
- W widoku `Map` dodano osobny widget overlay `Latest packet` w prawym górnym rogu mapy.
- W toolbarze mapy dodano przełącznik widoczności widgetu (`Show/Hide latest packet widget`) z zapisem stanu w `localStorage`.
- Widget pokazuje skrócone dane ostatnio odebranego pakietu: `Callsign`, `QSY`, `Distance and azimuth`, `Comment` (komentarz jako ostatni wiersz).
- Do payloadu `/api/map/stations` dodano pola `qsy_frequency_mhz`, `qsy_tone`, `qsy_offset_khz`, `qsy_callsign`.
- Dodano nowe tłumaczenia UI (`en`/`pl`) dla etykiet i komunikatów widgetu.

### Changed
- Overlay działa jako osobny moduł frontendowy (`map-latest-overlay.js`) i nie wykonuje dodatkowych requestów.
- Dane widgetu są aktualizowane z istniejącego odświeżenia mapy przez event `aprsbox:map-stations-refreshed`.
- Ustabilizowano layout widgetu: stała szerokość panelu (z limitem na małych ekranach) oraz zawijanie długich wartości bez zmiany szerokości.
- Zwiększono typografię i wyróżnienie wartości `Callsign` i `QSY` (większa czcionka + pogrubienie).

### Fixed
- Dodano testy regresyjne dla integracji widgetu mapy (template + JS event + toggle).
- Dodano test backendowy, który weryfikuje ekspozycję pól `QSY` w payloadzie mapy.

### Removed
- Brak zmian.

## 1.4.69 - 14.04.2026

### Stable release
- Wersja została wydana do linii stable jako milestone zbierający wcześniejsze iteracje rozwojowe.

### Included development snapshots
- 1.4.67.DEV
- 1.4.68.DEV

### Highlights
- Rozbudowano `Station Readiness` (m.in. `WX callsign`, `Active interfaces`, `Enabled services`) oraz ujednolicono statusy i badge.
- Dodano stronę `Changelog` w GUI oraz pozycję `Changelog` w sidebarze.
- Usprawniono konfigurację routingu pakietów (numeracja reguł, zmiana kolejności, dopracowanie widoku tabeli).
- Uzupełniono obsługę i prezentację statusu `REJ` dla wiadomości APRS.
- Poprawiono przekazywanie wybranego kanału aktualizacji do `update.sh` (`--git-branch`).

## 1.4.68.DEV - 14.04.2026

### Added
- W `Station Readiness` dodano pozycję `WX callsign`.
- W `Station Readiness` dodano listę `Active interfaces` z per‑interfejsowym statusem (`Enabled` / `Disabled` / `Connecting` / `Error` / `Unknown`).
- W `Station Readiness` dodano sekcję `Enabled services` ze statusami (`Enabled` / `Disabled`) dla: `Beacon enabled`, `Status enabled`, `WX enabled`, `Digi routine`, `iGate enabled`.
- Dodano nowe tłumaczenia UI dla etykiet dashboardu związanych z nową checklistą.
- Dodano przełączanie zegara w sidebarze między `UTC` i `LT` po kliknięciu (oraz klawiszami `Enter`/`Space`) z zapamiętaniem trybu w `localStorage`.
- Dla przełączanego zegara w sidebarze dodano semantykę kontrolki klikalnej (`role="button"`, `tabindex="0"`) oraz obsługę focus/hover.

### Changed
- Dashboard został skompaktowany wizualnie (mniejsze odstępy, paddingi i wysokości kart), aby więcej treści było widoczne bez przewijania.
- W pierwszym bloczku statusu pozostawiono tylko podsumowanie stacji (usunięto skróty `Interface` i `Last traffic`).
- W `Station Readiness` `Callsign` zastąpiono polem `Main callsign` z dołączanym `SSID` (gdy ustawiony).
- W listach `Active interfaces` i `Enabled services` wprowadzono kolorowe badge statusów.
- W `Enabled services` pozycję `Digi routine` umieszczono przed `iGate enabled`.
- Ujednolicono opisy statusów w checklistach do wspólnego formatu (`Enabled` / `Disabled` / `Connecting` / `Error` / `Unknown`).
- Wysokość panelu `Band Condition` została wyrównana do wysokości panelu po lewej stronie w górnym rzędzie dashboardu.
- Skompaktowano bloczek zegara w sidebarze i przeniesiono etykietę `UTC` do tej samej linii co data.
- W zakładce `Settings` panele `Global Settings` i `Application update` ustawiono obok siebie w układzie 2‑kolumnowym (z responsywnym przejściem do 1 kolumny na mniejszych ekranach).
- W zakładce `Settings` sekcję `Danger zone` przeniesiono na sam dół strony.

### Fixed
- Zaktualizowano testy dashboardu do nowego kontraktu danych checklisty (`entries` dla list statusów i nowe etykiety pól).
- Poprawiono wybór kanału aktualizacji aplikacji z GUI: `update.sh` otrzymuje teraz jawnie wybrany kanał jako argument `--git-branch`, co eliminuje sporadyczny fallback do `main` przy uruchomieniu przez `sudo`/`doas` bez przekazanego środowiska.
- Poprawiono logikę statusu `Digi routine`: jest `Enabled` tylko gdy istnieje co najmniej jeden aktywny flow `receiver_rf -> tx_rf`; flow `Black Hole` (`action_log`) nie wpływają na ten status i nie mieszają się z `iGate enabled`.

### Removed
- Z `Station Readiness` usunięto: `Beacon interface`, `TX Block`, `TX Enabled`, `APRS Status enabled`, `Last station TX`, `Traffic Monitor`.

## 1.4.67.DEV - 14.04.2026

### Added
- W tabeli `Configured Packet Routing Flows` dodano numerację reguł.
- W `Actions` dodano przyciski do zmiany kolejności reguł (góra/dół) z zapisem kolejności w bazie danych.
- W widoku wiadomości dodano jednoznaczne oznaczenie statusu `Rejected (REJ)`.
- W formularzu `Add/Edit TNC` dodano przykład formatu przy polu `Path / Address` (`192.168.0.1:8002`).
- W sidebarze dodano pozycję `Changelog` jako ostatni element menu.
- Dodano stronę `Changelog` z prostym renderowaniem `changelog.md` (Markdown) po stronie JS.

### Changed
- W kolumnach `Source` i `Target` dla reguł routingu wyświetlana jest teraz sama nazwa endpointu, bez prefiksu typu (np. bez `receiver_rf:`).
- Dodano pełną obsługę protokołową `REJ` dla wiadomości APRS: `REJ` kończy proces wysyłki tak jak `ACK` (bez dalszych retry).
- W `Configured Packet Routing Flows` zmniejszono szerokości kolumn `Rule`, `Source`, `Target` i `Status`.
- Przy zmianie kolejności reguł routingu usunięto zielony komunikat potwierdzenia `Packet Routing flow order updated.`.
- W `Global WX Configuration` ukryto pole i opis `Resulting callsign`.

### Fixed
- Poprawiono rozróżnienie w GUI między brakiem `ACK` a odrzuceniem wiadomości przez `REJ`.
- W `Edit TNC` zapis (`Save`) nie opuszcza już trybu edycji; wyjście z edycji następuje przez `Cancel`.

### Removed
- Brak zmian.

## 1.4.66 - 12.04.2025

### Added
- Dodano cardioide.

### Changed
- Brak zmian.

### Fixed
- Poprawki na mapie.

### Removed
- Brak zmian.
