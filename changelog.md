# Changelog

## 1.7.21.dev - 30.04.2026

### Najważniejsze zmiany
- `WX TX Log`: ujednolicono widok z logiem TX stacji (status, błędy i podgląd ramki).
- `WX`: interwał odświeżania/wysyłki zmieniono na listę minut zależną od `path` (z walidacją po stronie backendu).

## 1.7.20.dev - 30.04.2026

### Najważniejsze zmiany
- Naprawiono problem, w którym po restarcie `core` beacony mogły przestać się planować z powodu zaległego joba `processing`.
- Dodano bezpieczne odblokowanie takiego joba przy starcie oraz log ostrzegawczy, że beacon nie został nadany.
- Zastosowano analogiczne zabezpieczenie dla `WX` (odzyskanie zaległego `processing` po restarcie i ostrzeżenie, że ramka nie została nadana).
- Uzupełniono diagnostykę `WX scheduler`, aby w logu było widać, który zaległy job blokuje kolejne enqueue.

## 1.7.16.dev - 28.04.2026

### Najważniejsze zmiany
- `My Settings` i `WX`: lista interfejsów nadajnika pokazuje tylko aktywne TNC i zawiera nową opcję `Transmit on all active interfaces`.
- Dodano tryb TX `single/all_active` dla konfiguracji stacji i WX (z migracją bazy: `station_settings.beacon_tx_scope`, `wx_config.beacon_tx_scope`).
- Outbound dla `beacon/status/object/message/WX` obsługuje `all_active` przez kolejkowanie osobnego joba na każdy aktywny interfejs.
- Schedulery `object` i `bulletin` uwzględniają nowy tryb targetu TX; dodano testy regresyjne dla trybu `all_active`.

## 1.7.15.dev - 27.04.2026

### Najważniejsze zmiany
- `Settings -> Global Settings`: dodano globalną paletę kolorów `Red Tactic` (obok istniejących motywów dzień/noc).
- `Messages`: styl bąbli wiadomości wychodzących (`TX`) został przepięty na tokeny motywu (bez sztywnego, lokalnie osadzonego zielonego RGBA).
- `Map` i `Station detail map`: sterowanie `Mask opacity` działa teraz przez nakładkę tintowaną kolorem aktywnego tematu/palety, zamiast globalnego przygaszania warstw kafli.

## 1.7.12 - 23.04.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- 1.7.1.dev
- 1.7.2.dev
- 1.7.4.dev
- 1.7.5.dev
- 1.7.7.dev
- 1.7.8.dev
- 1.7.11.dev

### Najważniejsze zmiany
- `WX / Domoticz`: poprawiono kompatybilność API, obsługę `base_url` (`z/bez /json.htm`), komunikaty błędów testu połączenia oraz stabilność testu/discovery/odczytu.
- `WX UI`: dopracowano przywracanie pozycji przewijania (`Edit`, `Save`, reload), uproszczono tabelę mapowania i ujednolicono szerokości kolumn `Required/Optional`.
- `Messages`: uszczelniono obsługę zapytań numerowanych i deduplikację `ACK`, utrzymując poprawne mapowanie numerów (`{1 -> ack1`).
- `TNC`: dodano `TX Min Gap` per interfejs oraz watchdog RX timeout dla `SERIALL` (z walidacją i wsparciem runtime).
- `My Settings`: dodano ręczny `Send status` wraz z endpointem i testami.
- `Map sources`: uproszczono widok listy źródeł i dopracowano kompaktowy układ tabel.
- Rozszerzono testy regresyjne dla obszarów `WX`, `Messages`, `TNC` i UI.

## 1.7.11.dev - 23.04.2026

### Najważniejsze zmiany
- `WX / Domoticz`: poprawiono kompatybilność API (`type=devices` dla testu połączenia, discovery i odczytu `rid`) oraz obsługę `base_url` z/bez końcówki `/json.htm`.
- `WX`: test połączenia zwraca teraz bardziej precyzyjny komunikat błędu z odpowiedzi źródła (zamiast wyłącznie ogólnego `Connection test failed.`).
- `WX`: dopracowano przywracanie pozycji przewijania dla `Edit source`, `Save source` i zwykłego reloadu strony (bez skoku na początek).
- `WX data mapping`: uproszczono widok tabeli (ukryto kolumny `Selector` i `Unit override` przy zachowaniu ich wartości w zapisie).
- `WX data mapping`: `Required parameters` i `Optional parameters` mają teraz identyczne szerokości kolumn dla spójnego, kompaktowego układu.
- Rozszerzono testy regresyjne `WX` o scenariusze integracji Domoticz (test połączenia, `base_url` z `/json.htm`, odczyt wartości).

## 1.7.8.dev - 20.04.2026

### Najważniejsze zmiany
- `Messages`: automatyczne `ACK` zachowuje teraz dokładny numer z odebranej ramki (`{1 -> ack1`, bez wymuszania `ack01`).
- Znormalizowany numer (`NN`) pozostaje używany wewnętrznie do deduplikacji i dopasowania historii wiadomości.
- Rozszerzono testy regresyjne dla przypadków jednocyfrowego numeru w `message/query` i generowania `ACK`.

## 1.7.7.dev - 20.04.2026

### Najważniejsze zmiany
- `TNC`: dodano per‑interfejs parametr `TX Min Gap (s)` (`0.2-1.2`, domyślnie `0.35`) w formularzu add/edit.
- Outbound respektuje `TX Min Gap` konkretnego TNC, co ogranicza kolizje ramek przy burstach (np. `ACK` vs `DIGI`).
- `Settings -> TNC`: usunięto pole `Notes`; dodano migrację i walidację `modems.tx_min_gap_seconds` oraz testy regresyjne.

## 1.7.5.dev - 19.04.2026

### Najważniejsze zmiany
- `Messages`: uszczelniono obsługę numerowanych zapytań APRS (w tym `?VER`) przy równoległym ruchu digi.
- Ograniczono lawinę `ack-duplicate` dla tej samej pary `sender + query_number` w krótkim oknie czasowym, aby nie przeciążać wspólnego kanału TX.
- Odpowiedź query (`query-version`) nie jest dublowana; pozostaje pojedyncza nawet przy wielu kopiach tej samej ramki po digi.
- Dodano test regresyjny dla burstu duplikatów query słyszanych przez różne zużyte hop-y (`*`) w path.

## 1.7.4.dev - 19.04.2026

### Najważniejsze zmiany
- `My Settings`: dodano ręczny przycisk `Send status` obok `Send beacon`.
- Dodano endpoint `POST /station/send-status` z analogicznym przepływem zapisu formularza i kolejkowania outbound (`status`).
- Uzupełniono tłumaczenia etykiety `Send status` (`en/pl/tlh`) oraz test szablonu `station`.
- `Settings -> Map sources`: usunięto kolumnę `Enabled` z listy źródeł.
- `Map sources`: dopracowano kompaktowy layout tabeli (szerokości kolumn, ikony akcji, spacing), żeby ograniczyć poziomy scroll.

## 1.7.2.dev - 19.04.2026

### Najważniejsze zmiany
- `TNC (SERIALL)`: dodano per‑interfejs ustawienie timeoutu watchdog RX (`0-600s`, krok `30s`).
- Wartość `0` wyłącza wymuszony reconnect po ciszy RX.
- Timeout jest stosowany przez runtime per TNC i respektowany po zmianie konfiguracji.

## 1.7.1.dev - 18.04.2026

### Najważniejsze zmiany
- `Messages`: opóźniony `ACK` (`ackNN`) może domknąć outbound oznaczony wcześniej jako `failed`.
- Po takim `ACK` status przechodzi na `acked`, ustawiany jest `acked_at`, a pola błędu są czyszczone.
- Dodano test regresyjny dla scenariusza późnego `ACK`.

## 1.7.0 - 18.04.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- 1.6.1.dev
- 1.6.2.dev
- 1.6.5.dev
- 1.6.6.dev

### Najważniejsze zmiany
- Dodano lokalny proxy/cache kafelków map (endpoint backendowy, przełącznik per źródło, statystyki i `Clear cache`).
- Rozszerzono parser APRS o pozycje `compressed` z `symbol overlay` oraz render overlayu w mapie i tabeli `Stations`.
- Wdrożono `Distance filter` w `DIGI Flow` (GUI + backend + runtime) wraz z walidacją i testami.

## 1.6.6.dev - 18.04.2026

### Najważniejsze zmiany
- Dodano `Distance filter` do `DIGI Flow` jako krok pipeline (1-3 strefy, logika OR).
- Wzmocniono walidację: poprawne zakresy `latitude/longitude`, `radius_km > 0`, pełne dane stref; filtr może wystąpić w flow tylko raz.
- Pakiety bez pozycji są traktowane jako `skipped/pass`.
- Dodano logi runtime i testy regresyjne; naprawiono `Add zone` w edytorze flow.

## 1.6.5.dev - 18.04.2026

### Najważniejsze zmiany
- Dodano pełną obsługę `symbol overlay` (`None`, `0-9`, `A-Z`) dla `Objects/Items` i `My Settings` (GUI, walidacja, zapis/odczyt, edycja, generowanie ramek).
- Overlay działa tylko dla tablicy `Alternate (\)`; dla `Primary (/)` jest automatycznie czyszczony.

## 1.6.2.dev - 17.04.2026

### Najważniejsze zmiany
- Parser APRS: obsługa `compressed` z overlayem (`0-9`, `A-Z`) oraz legacy `a-j -> 0-9`.
- Dodano defensyjną walidację `c/s/T` i doprecyzowano detekcję przypadków niejednoznacznych.
- Dodano render overlayu ikon APRS (mapa, szczegóły stacji, tabela `Stations`).
- Naprawiono odrzucanie legalnych ramek `compressed` z overlayem; dodano testy regresyjne.

## 1.6.1.dev - 17.04.2026

### Najważniejsze zmiany
- Dodano lokalny proxy/cache kafelków map z endpointem `GET /api/map/tiles/{source_id}/{z}/{x}/{y}`.
- `Settings -> Map sources`: przełącznik cache/proxy, statystyki per źródło i akcja `Clear cache`.
- Rozszerzono `map_sources` o pola cache oraz dodano migrację.
- Uporządkowano obsługę `root_path` dla widoków mapowych i pickerów.
- Wzmocniono bezpieczeństwo (upstream tylko z konfiguracji źródła) i wydajność statystyk (bez skanowania całego cache przy każdym renderze).
- Dodano testy regresyjne proxy/cache.

## 1.6.0 - 17.04.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- 1.5.1.dev
- 1.5.3.dev
- 1.5.4.dev
- 1.5.7.dev
- 1.5.8.dev

### Najważniejsze zmiany
- `Messages`: dopracowano obsługę `ACK/REJ` i ścieżek (`conversation path` / fallback `beacon_path`).
- Wzmocniono niezawodność runtime TNC (autorecovery, lepsza obsługa wyjątków, reconnect po błędach TX).
- `Stations`: dodano filtry, licznik stacji pogodowych i sortowanie.
- Dodano usprawnienia UX (m.in. przywracanie pozycji przewijania w `WX`) i rozszerzono testy regresyjne.

## 1.5.8.dev - 17.04.2026

### Najważniejsze zmiany
- Automatyczne `ACK` używa teraz ścieżki kontekstowo: ścieżka rozmowy, a gdy jej brak, fallback do `beacon_path`.
- `enqueue_ack_job` przyjmuje jawnie ścieżkę `ACK`.
- Naprawiono nadpisywanie ręcznie ustawionej ścieżki rozmowy przez ruch przychodzący i odpowiedzi automatyczne.
- Rozszerzono testy regresyjne dla wyboru ścieżki `ACK`.

## 1.5.7.dev - 17.04.2026

### Najważniejsze zmiany
- `Stations`: dodano kafelki filtrów (`All`, `Fixed`, `Mobile`, `Objects`, `Weather`) i licznik `Weather stations`.
- Dodano sortowanie tabeli (`Callsign`, `Last activity`, `Distance`) i domyślne sortowanie po najnowszej aktywności.
- Uporządkowano układ i responsywność panelu filtrów oraz zachowanie filtrów po odświeżeniu danych.
- Poprawiono klasyfikację stacji pogodowych w parserze APRS; dodano testy regresyjne UI/parsera.

## 1.5.4.dev - 16.04.2026

### Najważniejsze zmiany
- `WX`: automatyczne przywracanie pozycji przewijania po operacjach `POST`.
- `Messages`: doprecyzowano logowanie wadliwych ramek APRS (powód, `source`, fragment ramki).
- Wzmocniono odporność na błędy SQLite i defensywne logowanie, aby uniknąć `500` przy renderowaniu widoków.
- Naprawiono scenariusze z błędnym `source` powodujące wyjątki w runtime lub `Internal Server Error`.

## 1.5.3.dev - 16.04.2026

### Najważniejsze zmiany
- Dodano autorecovery runtime TNC po nieoczekiwanym zakończeniu tasku.
- Wzmocniono obsługę wyjątków i retry po `reconnect_delay`.
- Uporządkowano `stop/cleanup`, także po wcześniejszym wyjątku.
- Naprawiono przypadek błędu TX bez reconnectu; runtime zamyka teraz writer/FD, czyści bufory KISS i wymusza zdrowe odtworzenie połączenia.

## 1.5.1.dev - 16.04.2026

### Najważniejsze zmiany
- `Messages`: przychodzące APRS bez numeru (`{NN}`) są zapisywane i widoczne w rozmowach.
- Dla nienumerowanych wiadomości nie jest wysyłany `ACK` (zgodnie z protokołem).
- Dodano test regresyjny dla tego scenariusza.

## 1.5.0 - 16.04.2026

### Stable release
- Wydanie stabilne podsumowujące zmiany z gałęzi `dev`.

### Included development snapshots
- 1.4.70.DEV
- 1.4.71.DEV
- 1.4.72.DEV
- 1.4.73.DEV

### Najważniejsze zmiany
- Rozszerzono konfigurację map (`map_sources` w `Settings`, warstwa bazowa z DB).
- Dodano `Valid until (UTC)` dla obiektów i biuletynów z automatycznym wyłączaniem po wygaśnięciu.
- Wzmocniono niezawodność TNC serial (watchdog ciszy RX, `SERIAL/SERIALL`, fallback TX).
- Uporządkowano logowanie i czytelność GUI (`Logs`, dashboard `Gotowość stacji`, tytuły kart przeglądarki).

## 1.4.73.DEV - 16.04.2026

### Najważniejsze zmiany
- Dodano watchdog RX (150s ciszy) dla interfejsów serial TNC z wymuszonym reconnectem.
- Krytyczne zdarzenia TNC trafiają do głównego logu `system`.
- Rozszerzono kompatybilność typów modemu o `SERIAL` i `SERIALL` (runtime + GUI) oraz znormalizowano stare rekordy migracją.
- Usprawniono fallback TX i logowanie błędów wysyłki.
- Ujednolicono tytuły kart (`APRSBox: ZNAK-SSID`) i skompaktowano wybrane elementy dashboardu.

## 1.4.72.DEV - 15.04.2026

### Najważniejsze zmiany
- Dodano `Valid until (UTC)` dla `Objects` i `Bulletins/Announcements` (GUI + walidacja backendu + migracja `valid_until_utc`).
- Scheduler i runtime outbound respektują datę ważności i automatycznie wyłączają/pomijają rekordy po wygaśnięciu.
- Dodano sekcje `TX Log` dla obiektów i biuletynów.
- Główny widok `Logs` filtruje techniczne kategorie ruchu radiowego, pozostawiając log operacyjno-administracyjny.
- Uzupełniono tłumaczenia i testy regresyjne (log filtering).

## 1.4.71.DEV - 14.04.2026

### Najważniejsze zmiany
- `Settings`: dodano panel `Map sources` z modelem DB i operacjami CRUD + ustawianie domyślnego źródła i kolejności.
- Bazowa warstwa mapy jest pobierana z konfiguracji DB i używana spójnie w `Map`, `Station detail` i pickerach lokalizacji.
- Rozszerzono payload mapy o parametry zoom/subdomains.
- Uproszczono UI panelu `Map sources` i mechanikę kolejności źródeł.
- Zabezpieczono migrację do stanu z dokładnie jednym aktywnym źródłem domyślnym.

## 1.4.70.DEV - 14.04.2026

### Najważniejsze zmiany
- `Map`: dodano widget `Latest packet` z przełącznikiem `Show/Hide` i zapisem stanu w `localStorage`.
- Widget korzysta z istniejącego odświeżania mapy (bez dodatkowych requestów).
- Rozszerzono payload `/api/map/stations` o pola `QSY`.
- Ustabilizowano layout widgetu i dodano testy regresyjne (frontend + backend).

## 1.4.69 - 14.04.2026

### Stable release
- Wydanie stabilne zbierające wcześniejsze iteracje rozwojowe.

### Included development snapshots
- 1.4.67.DEV
- 1.4.68.DEV

### Najważniejsze zmiany
- Rozbudowano `Station Readiness` i ujednolicono statusy/badge.
- Dodano stronę `Changelog` i pozycję menu w sidebarze.
- Usprawniono konfigurację routingu pakietów (numeracja, kolejność, widok tabeli).
- Uzupełniono obsługę `REJ` w wiadomościach APRS.
- Poprawiono przekazywanie wybranego kanału aktualizacji do `update.sh` (`--git-branch`).

## 1.4.68.DEV - 14.04.2026

### Najważniejsze zmiany
- `Station Readiness`: dodano `WX callsign`, listę `Active interfaces` i sekcję `Enabled services` ze statusami.
- Dashboard i sidebar zostały skompaktowane; dodano przełączanie zegara `UTC/LT` z zapamiętaniem w `localStorage`.
- Uporządkowano etykiety i kolejność pozycji w checklistach statusowych.
- `Settings`: `Global Settings` i `Application update` w układzie 2-kolumnowym; `Danger zone` przeniesiono na dół.
- Zaktualizowano testy dashboardu i poprawiono przekazywanie kanału aktualizacji do `update.sh`.

## 1.4.67.DEV - 14.04.2026

### Najważniejsze zmiany
- `Packet Routing Flows`: dodano numerację reguł i zmianę kolejności (`góra/dół`) z zapisem do DB.
- Dodano pełną obsługę statusu `REJ` dla wiadomości APRS (`REJ` kończy proces wysyłki jak `ACK`).
- Dodano stronę `Changelog` i pozycję `Changelog` w sidebarze.
- Uproszczono widok tabeli routingu i poprawiono kilka zachowań UI (`Edit TNC`, `Global WX Configuration`).

## 1.4.66 - 12.04.2025

### Najważniejsze zmiany
- Dodano cardioide.
- Wprowadzono poprawki mapy.
