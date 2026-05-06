# Changelog

## 1.7.46.dev - 06.05.2026

### Najważniejsze zmiany
- `Statystyki / zakresy`: utrzymano zakresy `1 dzień`, `7 dni`, `30 dni` (usunięto `rok` z selektora UI), z nawigacją okna `Wstecz/Dalej`.
- `Statystyki / agregacja`: dla `1 dzień` używany jest bucket `1h`, a dla dłuższych zakresów bucket `1d`; poprawiono wyliczanie granic bucketów dziennych (UTC), aby bieżący dzień był widoczny w widokach `7 dni` i `30 dni`.
- `Statystyki / TOP20 devices`: dodano numerację pozycji jako pierwszą kolumnę listy.
- `Statystyki / TOP20 devices`: poprawiono semantykę zliczania na `unikalne CALLSIGN-SSID per urządzenie` w wybranym oknie czasu (bez przypisywania stacji wyłącznie do jednego „dominującego” urządzenia), co eliminuje zaniżanie liczników dla urządzeń takich jak `TH-D75`.
- `Statystyki / TOP20 devices`: scalono duplikaty tego samego modelu wykryte przez różne identyfikatory (`TOCALL`/`Mic-E`) do jednej pozycji rankingu oraz ujednolicono `TOCALL APRS` jako `GENERIC APRS`, aby uniknąć równoległych pozycji `Unknown`/`Nieznany`.
- `Statystyki / TOP20 devices`: naprawiono podwójne zliczanie tej samej stacji w obrębie jednego modelu (np. kilka identyfikatorów `TH-D75` dla jednego `CALLSIGN-SSID`), więc licznik modelu odpowiada unikalnym stacjom.
- `Statystyki / TOP20 devices`: API zwraca teraz dodatkowe sumary (`unique_station_keys_total`, `unique_station_device_pairs_total`) do rozróżnienia „ile unikalnych stacji słyszano” vs „ile unikalnych wystąpień urządzeń (station-device) zliczono”.
- `Statystyki / TOP20 users`: dodano nowy blok `TOP20 users` pod `TOP20 devices` (lista bez wykresu kołowego), z rankingiem `CALLSIGN-SSID` liczonym po liczbie ramek RX (`ramki (procent)`), numeracją pozycji i kolorowymi markerami.
- `Statystyki / API`: dodano endpoint `GET /api/statistics/users` z obsługą `range` i `shift`, spójny z istniejącym mechanizmem odświeżania danych statystyk.
- `I18N`: dodano/uzupełniono klucze tłumaczeń statystyk (`Back`, `Forward`, `aggregation`, `TOP20 users`) w `en/pl/tlh`.
- `Testy`: rozszerzono testy regresyjne `statistics` o API `users`, nawigację `shift` oraz poprawność agregacji i mapowania danych.

## 1.7.44.dev - 06.05.2026

### Najważniejsze zmiany
- `TNC (SERIAL/SERIALL)`: wewnętrznie zastąpiono direct-serial lokalnym brokerem `KISS SERIAL <-> KISS TCP (127.0.0.1)`, bez zmian w konfiguracji użytkownika.
- `Runtime/lifecycle`: dla każdego aktywnego TNC serial działa osobny broker z kontrolowanym start/stop/reconnect i pełnym zamykaniem uchwytów przy disable/shutdown.

## 1.7.40.dev - 05.05.2026

### Najważniejsze zmiany
- `Statystyki / layout`: przebudowano układ strony `Statistics` do kolumn `2/3 + 1/3` (główne wykresy czasowe po lewej, panel podsumowań po prawej) z zachowaniem responsywności i istniejącego stylu kart.
- `Statystyki / TOP20 devices`: dodano kartę donut `TOP20 devices` opartą o istniejący `Chart.js`, wraz z listą pozycji (`count`, `%`) i markerami kolorów zgodnymi z segmentami wykresu.
- `Statystyki / metryka`: TOP20 liczy udział domyślnie po unikalnych `CALLSIGN-SSID` (nie po liczbie ramek), z obsługą kategorii `Unknown`, `Mixed / Unknown` i `Other`.
- `Statystyki / TOCALL`: identyfikacja urządzeń używa istniejącego mechanizmu `aprs-deviceid`; nieznane `destination/TOCALL` są mapowane do `Unknown` zamiast surowych, mylących etykiet.
- `Statystyki / zakres czasu`: usunięto lokalny przełącznik `Window` z karty TOP20; wykres i lista korzystają z tego samego głównego `Range` oraz nawigacji `Back/Forward` co pozostałe wykresy statystyk.
- `Statystyki / bufor danych`: dodano bufor godzinowy `traffic_device_station_device_hourly` aktualizowany przy RX `TNC2`, aby TOP20 dla dłuższych zakresów nie zależał wyłącznie od retencji `traffic_frames`.
- `Statystyki / stabilność danych`: API TOP20 porównuje wariant z bufora i wariant z bieżących `traffic_frames` dla tego samego okna i wybiera bogatszy zbiór podczas dogrzewania bufora po wdrożeniu/restarcie.
- `Statystyki / tooltipy`: dodano `TOCALL` w tooltipie donuta oraz w hover tooltipie pozycji listy.
- `Statystyki / kolory`: poprawiono paletę donuta do ciągłego gradientu ciepłe->zimne bez resetu po 16. elemencie; segment `Other` ma stały szary kolor.
- `Testy`: zaktualizowano testy API/statystyk urządzeń do nowego modelu zakresów i bufora godzinowego oraz dodano asercje dla pola `tocall`.

## 1.7.39.dev - 05.05.2026

### Najważniejsze zmiany
- `Statystyki / routing`: dodano osobną stronę `Statystyki` w menu bocznym (`/statistics`) wraz z endpointem `GET /api/statistics/traffic` zwracającym gotowe buckety czasowe do wykresów.
- `Statystyki / wykresy`: dodano trzy karty wykresów (`Typy ramek APRS`, `Słyszane bezpośrednio vs wszystko`, `Akcje APRSBox`) oparte o istniejący `Chart.js` i bieżącą paletę kolorów `Traffic Log`.
- `Statystyki / semantyka`: usunięto serię `duplicate ignored`; seria `filtered_dropped` została opisana jako `Filtered / dropped to APRS-IS`, a kolor `gated to APRS-IS` przepięto na `--traffic-color-proxy-tx`.
- `Statystyki / zakresy`: uproszczono zakresy do `1 dzień`, `7 dni`, `30 dni`; dodano nawigację okna `Wstecz/Dalej` przesuwającą wykresy o pełny wybrany zakres.
- `Statystyki / agregacja`: ustawiono bucket `1h` dla `1 dzień` oraz `1d` dla zakresów dłuższych; naprawiono wyliczanie granic bucketa dziennego (UTC epoch flooring), aby bieżący dzień nie znikał z wykresów `7 dni`.
- `Statystyki / TOP users`: dodano tabelę `TOP20 users` pod `TOP20 devices` (bez wykresu kołowego), z rankingiem `CALLSIGN-SSID` wg liczby ramek i udziałem procentowym w całym zakresie.
- `I18N`: dodano/uzupełniono klucze tłumaczeń dla statystyk (`1 day`, `7 days`, `30 days`, `Back`, `Forward`, `aggregation`, `TOP20 users`) w `en/pl/tlh`.
- `Testy`: rozszerzono testy regresyjne API statystyk o bucketowanie `1h/1d`, nawigację `shift` i poprawność mapowania danych w zakresie dziennym.

## 1.7.38 - 05.05.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- zmiany  od 1.7.29.dev do 1.7.37.dev

## 1.7.37.dev - 05.05.2026

### Najważniejsze zmiany
- `TNC RX / KISS parser`: naprawiono parsowanie ramek rozdzielanych `FEND`, aby poprawnie obsługiwać `back-to-back FEND` i nie gubić poprawnych ramek danych.
- `Arduino TNC compatibility`: pseudo-ramki `C0 0D 0A C0` (CR/LF po ramce) są ignorowane jako `unsupported/non-data`, więc nie spamują już głównego `Traffic Log` wpisami `KISS command 0xD len=1`.
- `Diagnostyka`: dodano liczniki ignorowanych ramek KISS (`ignored_kiss_non_data`, `ignored_kiss_garbage`) oraz rate-limited debug hex dump do potwierdzania sekwencji śmieciowych bez zalewania logów. (tnx SP5QWJ)

## 1.7.36.dev - 04.05.2026

### Najważniejsze zmiany
- `Dashboard / Activity Charts`: dodano trwałe zapamiętywanie `Range` i zoomu wykresów w `localStorage` (zoom per zakres: `1h..365d`), z odtwarzaniem po odświeżeniu.
- `Dashboard / Chart visibility`: w trybie jasnym domyślna linia wykresu (`All frames` / `RX`) ma kolor czarny dla lepszej czytelności; kolory serii pozostają spójne z paletą `Traffic Log`.
- `Dashboard / Theme switch`: po zmianie motywu/palety kolory wykresów odświeżają się bez przeładowania strony.
- `Map / Topbar`: usunięto widoczną etykietę `Mask opacity` i skompaktowano topbar (mniejsze odstępy, padding i kontrolki), zachowując `aria-label` dla dostępności.

## 1.7.35.dev - 04.05.2026

### Najważniejsze zmiany
- `Radio activity aggregation`: dodano trwałą warstwę bucketów `5m` (`radio_activity_5m`) oraz tabelę stanu workera (`radio_activity_aggregator_state`) do historycznej analityki bez zmiany semantyki `traffic_frames`.
- `Radio activity worker`: dodano okresowy worker działający poza ścieżką RX/TX, który agreguje tylko zamknięte buckety UTC z `safety delay`, wspiera catch-up po restarcie i zapisuje `last_error` bez wywracania runtime.
- `Dashboard API`: dodano endpoint `GET /api/dashboard/radio-activity` oparty o `radio_activity_5m` z zakresami `1h/3h/6h/12h/24h/7d/30d/365d`.
- `Long-range charts`: dla zakresów powyżej `7d` dodano adaptacyjny downsampling (agregacja odczytu z limitem punktów), aby nie przeciążać wykresów i przeglądarki.
- `Dashboard UI`: wykresy aktywności zostały przepięte na nowy endpoint, dodano selector zakresu (domyślnie `24h`) oraz zoom myszą (`drag` do przybliżenia, `double click` do resetu).
- `Chart palette`: kolory datasetów wykresów są teraz oparte o tę samą paletę co `Traffic Log` (wspólne zmienne CSS), co ujednolica znaczenie kolorów między widokami.
- `Testy`: dodano testy agregatora i API (tworzenie tabel, bucketing UTC, upsert, pomijanie otwartego bucketu, zakresy i downsampling) oraz utrzymano zgodność istniejących testów dashboard/traffic.

## 1.7.32.dev - 04.05.2026

### Najważniejsze zmiany
- `Settings -> Global Settings`: dodano dwie niezależne opcje przezroczystości kół zasięgu: `Coverage fill opacity` i `Coverage outline opacity`.
- `Coverage opacity`: zakres `Coverage fill opacity` ograniczono do `0-20%` z gradacją co `1%`; `Coverage outline opacity` pozostawiono w dotychczasowym zakresie.
- `Map rendering`: przezroczystość wypełnienia i obwiedni PHG jest stosowana dynamicznie podczas renderu i zapisywana lokalnie (`localStorage`) per przeglądarka.

## 1.7.30.dev - 01.05.2026

### Najważniejsze zmiany
- `Settings -> Configuration backup`: uzupełniono brakujące klucze i18n, dzięki czemu nagłówek sekcji, etykiety akcji i komunikaty modala importu przechodzą przez tłumaczenia tak jak pozostałe elementy `Settings`.
- `Configuration backup import`: dodano tłumaczenia komunikatów walidacji/wyjątków backupu (`empty/size/json/format/version/table payload/FK`), aby błędy z endpointu importu były prezentowane spójnie w wybranym języku GUI.

## 1.7.29 - 01.05.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- 1.7.15.dev
- 1.7.16.dev
- 1.7.20.dev
- 1.7.21.dev
- 1.7.24.dev
- 1.7.26.dev
- 1.7.27.dev

### Najważniejsze zmiany
- `Settings -> Configuration backup`: dodano eksport/import snapshotu konfiguracji GUI (`JSON`) wraz z walidacją formatu/wersji, limitem rozmiaru i atomowym restore w transakcji.
- `Configuration backup restore`: import odtwarza wyłącznie dane konfiguracyjne, weryfikuje relacje (`foreign_key_check`) i obsługuje przenoszenie konfiguracji między instancjami.
- `Traffic Monitor SSE`: przebudowano strumień na wspólnego producera/broadcastera (mniejsze obciążenie CPU przy wielu klientach), z heartbeatem, limitem klientów i parametrami `ENV`.
- `TNC/Outbound (SERIALL/KISS)`: ustabilizowano ścieżkę TX/RX dla trybów multi-interface; usunięto ryzykowny bypass TX i doprecyzowano diagnostykę/logowanie runtime.
- `Beacon/WX schedulers`: dodano odzyskiwanie zaległych jobów `processing` po restarcie `core`, aby nie blokować kolejnych wysyłek.
- `TX scope`: dodano tryb `Transmit on all active interfaces` dla beaconów stacji i `WX` (GUI + runtime + walidacja + testy).
- `UI/Theming`: dodano paletę `Red Tactic`; `Map mask opacity` i style wiadomości `TX` korzystają z tokenów motywu zamiast sztywnych kolorów.
- `WX`: ujednolicono `WX TX Log` i zmieniono interwał odświeżania/wysyłki na listę minut zależną od `path` (z walidacją backendową).
- `Testy`: rozszerzono testy regresyjne dla backupu konfiguracji, SSE, TNC/outbound, schedulerów beacon/WX i nowych akcji w `Settings`.

## 1.7.27.dev - 01.05.2026

### Najważniejsze zmiany
- `Settings -> Configuration backup`: dodano nową sekcję do eksportu i importu snapshotu konfiguracji GUI.
- `Export konfiguracji`: dodano endpoint `GET /settings/config/export`, który generuje plik JSON z konfiguracją (`station`, `TNC`, `APRS-IS`, `WX`, `DIGI flows`, `objects/items/bulletins`, źródła map i wybrane ustawienia globalne).
- `Import konfiguracji`: dodano endpoint `POST /settings/config/import` z walidacją formatu/wersji backupu, limitem rozmiaru pliku (`5 MB`) i atomowym restore w transakcji SQLite.
- `Import konfiguracji`: naprawiono restore między instancjami z danymi runtime (zachowana spójność FK podczas podmiany tabel konfiguracyjnych).
- `Plik backupu`: nazwa eksportowanego pliku zawiera teraz `CALLSIGN-SSID` z `My Settings` (gdy SSID jest ustawione).
- `UX importu`: komunikaty błędów importu są prezentowane dłużej w modalu `Settings`, aby łatwiej odczytać szczegóły.
- `Integralność danych`: import odtwarza tylko tabele konfiguracyjne i whitelistę kluczy `app_settings`, a następnie wykonuje kontrolę relacji (`foreign_key_check`) przed zatwierdzeniem.
- `Testy`: dodano testy regresyjne backupu (`tests/test_config_backup.py`) oraz testy obecności nowych akcji w `Settings` (`tests/test_settings_maintenance.py`).

## 1.7.26.dev - 01.05.2026

### Najważniejsze zmiany
- `Traffic Monitor SSE`: zastąpiono pętlę per-klient jednym wspólnym producerem/broadcasterem snapshotów na proces.
- `SSE wydajność`: `get_traffic_snapshot()` wykonywane jest maksymalnie raz na tick (domyślnie `1s`) niezależnie od liczby klientów.
- `SSE payload`: zachowano kompatybilny format `data: <json>`; pełny event nie jest wysyłany, gdy payload się nie zmienił.
- `SSE heartbeat`: dodano lekki keepalive `: ping` (domyślnie co `25s`) dla stabilności połączeń za proxy.
- `SSE stabilność`: dodano limit klientów (`APRSBOX_TRAFFIC_STREAM_MAX_CLIENTS`, domyślnie `20`) z czytelnym logiem przy przekroczeniu.
- `SSE/NGINX`: endpoint zwraca nagłówki `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no` oraz notatkę konfiguracyjną dot. `proxy_buffering/proxy_cache/proxy_read_timeout`.
- `Konfiguracja`: dodano parametry `APRSBOX_TRAFFIC_STREAM_TICK_SECONDS`, `APRSBOX_TRAFFIC_STREAM_HEARTBEAT_SECONDS`, `APRSBOX_TRAFFIC_STREAM_MAX_CLIENTS`.
- `Testy`: dodano testy jednostkowe broadcastera (fanout wielu klientów, brak emisji przy niezmienionym payloadzie, heartbeat, limit klientów, unsubscribe/cleanup).

## 1.7.24.dev - 01.05.2026

### Najważniejsze zmiany
- `TNC (SERIALL/KISS)`: usunięto ryzykowny bypass TX w trybie multi-interface; wysyłka serial przechodzi przez aktywny runtime monitora, co zapobiega kolizjom z pętlą RX.
- `Serial TX`: direct fallback przy aktywnym monitorze jest blokowany kontrolowanym błędem i czytelnym logiem (zamiast równoległego otwierania portu).
- `Serial port`: otwarcie używane przez direct TX nie czyści już bufora wejściowego (`flush_buffers=False`), aby TX nie kasował ramek RX.
- `Diagnostyka`: dodano logi start/stop readera RX, start/koniec TX z długością ramki oraz log błędu przetwarzania RX z wymuszonym reconnectem.
- `Testy`: rozszerzono testy regresyjne o KISS escape w TX, serializację równoległych TX, brak flush input buffer oraz scenariusz TX error -> reconnect -> dalszy RX.

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
