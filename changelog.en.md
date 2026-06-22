# Changelog

## 1.8.45.dev - 2026-06-22
- `My Station / Beacon`: limited the station callsign in the beacon form to at most 6 printable ASCII characters, with backend validation as well.
- `My Station / Beacon`: the `callsign` and `Beacon Path` fields are now normalized to uppercase both in the form and on save.
- `My Station / Location`: blocked manual editing of `latitude` and `longitude`; coordinates are now set only through the `Get location` button.
- `Settings / Global settings`: moved the `Save Global Settings` button to the bottom of the block, and `Coverage fill opacity` now defaults to `10%` unless the user already saved a custom value.
- `Settings / Global settings / I18N`: added missing translations for the `Icon set` field, its option list, and the helper text below the select.

## 1.8.44 - 2026-06-22

### Stable release
- Stable promotion from the `dev` branch to `main`.

### Included development snapshots
- changes from `1.8.25.dev` to `1.8.43.dev`

### Highlights
- `Map / UX / diagnostics`: reworked the map and situational monitoring stack with a better viewport layout, the `Latest packet` / last digi scroller, per-TNC visibility filters, tooltip cleanup, and refined APRS icon rendering.
- `Routing / TX / APRS-IS`: added the logical `Local TX` source, the neutral `Internal TX` mode, hard guards for APRS-IS uplink and locally generated frames, and per-TNC pacing for TX queues.
- `DIGI / flow engine`: expanded `Path rule and DIGI guard`, activated the `Rate limit filter`, enforced a safe RF step order, and propagated TNC rename operations into flow references.
- `Objects / Bulletins / content`: added scheduled and recurring object transmission, minute-precision `Valid until`, object timestamp generation at real TX time, manual `Send now`, hidden `killed` objects, and local Markdown help for `Objects` and `Bulletins`.
- `Integrations / RX / parser`: added `OpenWebRX MQTT (RX only)` with `APRS/SONDE/ADSB` support, local deduplication, extended diagnostics, and improved Mic-E decoding and presentation.
- `Maintenance / GUI / I18N`: added Spanish and multilingual changelogs (`PL/EN/ES/DE`), Docker mode guards for host actions, SQLite runtime diagnostics with safe reset, Telegram/webhook notifications, the new sidebar logo, and local help files.

## 1.8.43.dev - 2026-06-21
- `Traffic Monitor / KISS RX`: empty KISS data frames (`0x00` with no payload) from TCP/IP TNCs are now ignored, so Traffic Monitor no longer shows `AX.25 decode failed (payload too short (0B))` noise between valid packets.
- `Changelog / I18N`: added a German changelog file and `DE` content selection based on the current GUI language.

## 1.8.42.dev - 2026-06-21
- `GUI / sidebar / branding`: replaced the old sidebar branding (icon + `APRSBox` + `Native APRS console`) with the new APRSBox logo rendered as inline SVG.
- `GUI / sidebar / logo`: wired logo colors into the existing theme and palette system through CSS variables, so the branding updates automatically when the user switches the GUI theme.
- `GUI / sidebar / layout`: kept the logo responsive inside the current sidebar width, without widening the sidebar or disturbing the menu layout.

## 1.8.41.dev - 2026-06-20
- `Help / Objects / Bulletins`: added local Markdown help files for the `Objects` and `Bulletins / Announcements` tabs in `PL/EN/ES`, together with basic document navigation and GUI form integration.

## 1.8.40.dev.mice - 2026-06-17
- `Mic-E / Station Details`: expanded Mic-E diagnostics directly inside station details, without a separate section or empty labels; also fixed `message capable` priority so the raw type byte wins over device metadata.

## 1.8.39.dev - 2026-06-15
- `Map / modern icons`: centered the overlay on the icons and added a stronger shadow for readability.

## 1.8.38.dev - 2026-06-14
- `DIGI / Rate limit filter`: activated the existing `Rate limit filter` block for flows with `TX = tnc radio`; the filter keeps the last passed frame per instance, drops subsequent frames until the configured 5-60 s limit expires, and logs the block together with the active limit.
- `DIGI / Rate limit filter`: added a source-callsign mask with `*` wildcard support; the limit now applies to matching callsigns, and `*` covers all sources.
- `DIGI / Path rule`: for RF flows, the forced order remains in place so `Rate limit filter` is always placed directly before `Path rule and DIGI guard`.

## 1.8.37.dev - 2026-06-11
- `Objects / timestamp`: temporary objects now compute the APRS timestamp only at the moment of a real frame transmission (`DDHHMMz`), while permanent objects still use the fixed `111111z`.
- `DIGI / Path rule`: the `Paths (TRACE / traced)` field description now includes example paths `WIDE1-1`, `WIDE2-1` and `WIDE2-2`, and for flows with `TX = tnc radio` the order is enforced strictly: `Duplicate Filter (viscous-delay)` is always first and `Path rule and DIGI guard` is always last.
- `Map / scroller / objects`: fixed object rendering in the right map scroller so it uses the correct `display_callsign`.

## 1.8.36.dev - 2026-06-11
- `Outbound/TX queue`: fixed local-generated pacing so delayed frames are eventually transmitted instead of being rescheduled indefinitely.
- `DIGI / TNC rename`: renaming a TNC now propagates to DIGI flow source/target references and RF step configs, so routing keeps pointing at the same interface.

## 1.8.35.dev - 2026-06-11
- `Outbound/TX queue`: added per-TNC pacing for locally generated APRSBox frames so objects, bulletins, beacons, WX, status and manual TX are spaced out before physical transmission instead of being sent back-to-back.

## 1.8.34.dev - 2026-06-09
- `Objects / inbound-outbound`: killed objects no longer appear in the visible list/map, while outbound frames still use `_` for killed object packets.
- `Objects / manual TX`: added a `Send now` button in object edit mode to force a manual object transmission.
- `GUI / icons`: added a global APRS icon set selector (`legacy` / `modern`) and wired the local PNG symbol directory into the whole GUI.

## 1.8.33.dev - 2026-06-05
- `Map / station list`: fixed icon and color mixing in the right map scroller by removing base-callsign lookup; entries now use the exact `display_callsign`.

## 1.8.32.dev - 2026-06-03
- `Notifications / Telegram / webhooks`: implemented Telegram webhook notifications for messages and station radar.

## 1.8.30.dev - 2026-06-01

### Highlights
- `My Station / TX target`: added a new `Internal TX` option as a neutral mode without a physical RF transmitter.
- `Changelog / I18N`: added multilingual changelog files (`PL/EN/ES`) with automatic content selection based on the current GUI language.
- `UX / availability`: the `Internal TX` option is always visible in the transmitter interface list, regardless of flow configuration.
- `UX / messaging`: added a contextual message in `My Station` for `Internal TX` with active `Local TX -> APRS-IS` flow (frames may be forwarded to APRS-IS).
- `UX / messaging`: added a contextual message in `My Station` for `Internal TX` without an active flow (`Internal TX` behaves locally like a `black hole`).
- `Outbound/runtime`: for `Internal TX`, jobs are marked as `internal_tx_only`; they do not perform RF/TCP/serial transport, but still build a frame and pass it to the `Local TX` pipeline (routing decides what happens next, e.g. APRS-IS).
- `Logs and preview`: `Station TX Log` entries for this mode now show `Internal TX` instead of `Unknown interface`.
- `Tests`: added regressions for `Internal TX` without active APRS-IS flow, queueing without `interface_id`, and runtime path without RF transport attempts.

### Notes
- Older entries are still in Polish. They are included below until full translation is completed.

## 1.8.31.dev - 2026-06-02
- `Objects / Items`: added scheduled and recurring object transmission (`issue #31`, SQ2FRG).
- `I18N`: added Polish translations.

## 1.8.26.dev - 26.05.2026

### Najważniejsze zmiany
- `Map / layout`: usunięto stałe wyliczanie wysokości mapy (`clamp(...100vh...)`) i przełączono kartę mapy na układ flex-fill, żeby mapa wypełniała dostępne miejsce do dołu viewportu bez dokładania drugiego scrolla strony (desktop).
- `Map / kontenery`: dodano łańcuch `min-height: 0` dla `content -> map-panel -> panel-body -> map-page -> map-stage`, przy zachowaniu naturalnej wysokości toolbara oraz `height: 100%` dla elementu Leaflet względem wrappera.
- `Map / resize`: dodano obserwację rozmiaru kontenera mapy (`ResizeObserver`) i zdławione wywołanie `map.invalidateSize()`, bez zmian logiki APRS, warstw, tooltipów i SSE.
- `Map / scroller`: dodano widżet pod `Latest packet` (układ `ikonka | znak | ostatni digi`) z aktualizacją na żywo z tego samego strumienia ruchu (`/api/traffic/stream`) oraz przełącznikiem `show/hide` na toolbarze mapy.
- `Map / scroller / APRS`: kolumna `digi` pokazuje ostatni rzeczywisty digi, który powtórzył ramkę (z pominięciem aliasów typu `WIDE*/TRACE*` i `q*`) z obsługą monitorów oznaczających `*` tylko na ostatnim hopie; zachowano pełny znak digi z SSID (normalizacja tylko `-0`).
- `Map / scroller / oznaczenia`: przy znaku stacji dodano znaczniki `*` (direct RF), `#` (third-party iGate->RF), `@` (powtórzone przez lokalną stację); własne ramki lokalnej stacji są widoczne także dla `TX`.
- `Map / scroller / kolor`: kolor znaku stacji skaluje się wg odległości i bieżącej skali mapy (`czerwony -> żółty -> zielony`), a dla stacji bez pozycji używany jest kolor czarny.
- `Map / viewport`: domknięto desktopowy layout mapy do wysokości viewportu (bez wyciekania mapy pod dolną krawędź strony) oraz ukryto wizualny pasek scrolla sidebara na zakładce Map.

## 1.8.25.dev - 24.05.2026

### Najważniejsze zmiany
- `Docker mode / detekcja`: dodano centralną flagę `is_container_mode` opartą o `APRSBOX_CONTAINER=1`.
- `Settings -> Application update`: w trybie Docker ukryto akcję `Update application` i pozostawiono `Check version` wyłącznie jako operację informacyjną (bez sugerowania aktualizacji przez GUI).
- `Settings -> Danger zone`: w trybie Docker sekcję akcji systemowych zastąpiono komunikatem o wyłączeniu akcji hosta oraz instrukcją użycia komend Docker.
- `Backend/API / hard guard`: endpointy `POST /settings/update-application`, `POST /settings/restart-services`, `POST /settings/reboot-host` i `POST /settings/poweroff-host` odmawiają działania w Docker mode (`HTTP 409`, kontrolowany JSON, bez 500/tracebacków).
- `System scripts`: w Docker mode nie są uruchamiane skrypty `update.sh`, `restart-services.sh`, `reboot-host.sh`, `poweroff-host.sh`.
- `Settings -> Configuration backup`: backup/restore konfiguracji pozostają aktywne w Docker mode; komunikat po imporcie wskazuje restart/recreate kontenera komendami Docker.
- `Docker docs`: doprecyzowano `README` — aktualizacja kontenera przez pull nowego obrazu i recreate kontenera z tymi samymi wolumenami.
- `Testy`: rozszerzono testy regresyjne `Settings` o guardy Docker mode (UI + router) oraz asercję braku uruchamiania skryptów systemowych.

## 1.8.24 - 24.05.2026

### Stable release
- Migracja wydania z gałęzi `dev` do `main`.

### Included development snapshots
- zmiany od `1.8.21.dev` do `1.8.23.dev`

### Najważniejsze zmiany
- `I18N / języki GUI`: dodano pełne wsparcie języka hiszpańskiego (`es`) i rejestrację w `SUPPORTED_LANGUAGES`.
- `Mapa / tooltip stacji`: uproszczono tooltip (usunięto `Destination` i `Packet type`), dodano sekcję zdekodowanych danych w formie badge'y oraz poprawiono czytelność odstępami.
- `Mapa / filtry interfejsów`: dodano filtrowanie widoku mapy per interfejs TNC (`show/hide`) dla markerów stacji, pokrycia PHG i śladów oraz przeniesiono przełączniki do górnej belki mapy.
- `API mapy`: rozszerzono payload `/api/map/stations` o `stations[*].interface_id`, `mobile_tracks[*].points[*].interface_id` i listę `interfaces` dla filtrowania frontend.

## 1.8.23.dev - 24.05.2026

### Najważniejsze zmiany
- `Mapa / filtry interfejsów`: dodano filtrowanie widoku mapy per interfejs TNC (`show/hide`) dla markerów stacji, pokrycia PHG i śladów.
- `Mapa / toolbar`: przełączniki interfejsów przeniesiono do górnej belki z ikonami mapy (bez osobnego wiersza pod paskiem narzędzi).
- `API mapy`: payload `/api/map/stations` rozszerzono o `stations[*].interface_id`, `mobile_tracks[*].points[*].interface_id` oraz listę `interfaces` używaną przez filtr frontend.

## 1.8.22.dev - 23.05.2026

### Najważniejsze zmiany
- `Mapa / tooltip stacji`: usunięto z tooltipa pola `Destination` i `Packet type`.
- `Mapa / tooltip stacji`: dodano na końcu sekcję zdekodowanych danych w formie badge'y, analogicznie do kolumny `Data` w zakładce `Stacje`.
- `Mapa / tooltip stacji`: usunięto duplikację `Prędkość` i `Kurs` w części tekstowej tooltipa (pozostają wyłącznie w badge'ach danych).
- `UX`: dodano dodatkowy odstęp między podstawowymi polami tooltipa a sekcją zdekodowanych badge'y dla lepszej czytelności.

## 1.8.21.dev - 21.05.2026

### Najważniejsze zmiany
- `I18N / języki GUI`: dodano nową paczkę językową `es` (`Español`) i rejestrację języka w `SUPPORTED_LANGUAGES`, dzięki czemu hiszpański jest dostępny do wyboru w `Settings -> Global Settings`.
- `I18N / katalog tłumaczeń`: dodano pełny katalog `app/languages/es.json` (spójny kluczami z `en.json`) dla tłumaczeń interfejsu.
- `APRS/AX.25 terminology (ES)`: w tłumaczeniach hiszpańskich doprecyzowano słownictwo operatorskie (m.in. `baliza`, `trama`, `trayectoria`, `salto`, `indicativo`, `digipeater`/`digirrepetidor`, `APRS-IS`, `iGate`) dla lepszego odwzorowania realnych pojęć w pracy APRS.
- `Testy I18N`: rozszerzono testy o walidację zgodności kluczy katalogu `es` względem `en` oraz zaktualizowano asercję listy obsługiwanych języków.

## 1.8.20 - 21.05.2026

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- zmiany od 1.8.1.dev do 1.8.19.dev

### Najważniejsze zmiany
- `OpenWebRX MQTT (RX only)`: dodano nowy interfejs RX z obsługą `APRS/SONDE/ADSB`, lokalną deduplikacją i rozszerzoną diagnostyką runtime.
- `Routing / APRS-IS`: dodano źródło `Local TX` z bezpiecznym routowaniem wyłącznie do `APRS-IS uplink` lub `Black Hole` oraz twardymi guardami strict-filter.
- `APRS parser`: rozszerzono obsługę pogodową o `Xxxx` (promieniowanie) oraz naprawiono dekodowanie Mic-E z ambiguity (`K/L/Z`) wraz z metadanymi niejednoznaczności pozycji.
- `Beacon / valid-until`: dodano tryb `Proportional Path` dla beaconu pozycji oraz rozszerzono `Ważne do (UTC)` dla obiektów/biuletynów o dokładność do minuty (`YYYY-MM-DD HH:MM`).
- `Traffic / Messages`: dodano lokalne filtry per interfejs TNC w `Traffic Monitor`, nowe zapytania `?APRSD` i `?DX` oraz guardy DIGI dla ramek `message/query`, `third-party` i już powtórzonych lokalnie.
- `Runtime / maintenance`: wzmocniono niezawodność warstwy `TNC SERIAL` (I/O, timeouty, init/close) oraz dodano diagnostykę konserwacji SQLite i bezpieczny reset danych runtime.

## 1.8.19.dev - 19.05.2026

### Najważniejsze zmiany
- `Objects / Bulletins`: pole `Ważne do (UTC)` obsługuje teraz datę i godzinę (`HH:MM`) w formularzu (`datetime-local`), zamiast samej daty.
- `Walidacja`: backend akceptuje formaty `YYYY-MM-DD` oraz `YYYY-MM-DD HH:MM` (także `YYYY-MM-DDTHH:MM` z formularza) i normalizuje zapis.
- `Wygaszanie`: schedulery i runtime wygaszają aktywność obiektu/biuletynu z dokładnością do minuty UTC; dla starych rekordów z samą datą zachowano kompatybilność (ważność do końca dnia UTC).
- `Testy`: zaktualizowano testy sekcji i flow outbound dla scenariuszy `valid_until_utc` z godziną.

## 1.8.18.dev - 17.05.2026

### Najważniejsze zmiany
- `Settings -> Database maintenance`: rozszerzono panel o diagnostykę kondycji SQLite (`DB/WAL/SHM size`, `page_count`, `freelist_count`, `quick_check`) oraz czytelną rekomendację, czy `VACUUM` jest potrzebny.
- `VACUUM / bezpieczeństwo`: rekomendacja `VACUUM` opiera się na odzyskiwalnej przestrzeni (próg rozmiaru + udział wolnych stron), a uruchomienie pozostaje blokowane, gdy jakikolwiek interfejs `TNC` jest aktywny.
- `Runtime maintenance`: dodano bezpieczną akcję `Reset runtime logs/data`, która czyści wyłącznie tabele operacyjne (logi/ramki/statystyki runtime) bez modyfikacji tabel konfiguracyjnych (`TNC`, `DIGI flows`, ustawienia stacji/WX, users itp.).
- `I18N (PL)`: uzupełniono tłumaczenia sekcji konserwacji bazy dla nowych etykiet, opisów, rekomendacji i komunikatów akcji, eliminując mieszanie języka polskiego i angielskiego w GUI.
- `Testy`: dodano/rozszerzono testy regresyjne dla snapshotu maintenance DB, bezpiecznego resetu runtime oraz nowych akcji/endpointów w `Settings`.

## 1.8.17.dev - 17.05.2026

### Najważniejsze zmiany
- `Routing / źródła`: dodano nowe logiczne źródło `Local TX`, które obejmuje wyłącznie ramki wygenerowane lokalnie przez APRSBox (beacon/status/WX/object/item/bulletin/message), bez mapowania na fizyczny `TNC TX`.
- `Routing / bezpieczeństwo`: dla `Local TX` dozwolone są tylko targety `APRS-IS uplink` i `Black Hole`; backend odrzuca konfiguracje `Local TX -> RF/TNC` i inne niedozwolone kombinacje.
- `APRS-IS strict filter`: dla `Local TX -> APRS-IS` utrzymano obowiązkowy strict filter (bez dublowania logiki), rozszerzony o twardy wymóg metadanych `origin=local_generated` + `local_generated=true` oraz blokadę ramek `third-party` i `q constructs`.
- `Outbound/runtime`: lokalnie generowane ramki otrzymują spójne metadane źródła (`local_generated`) i trafiają do istniejącego pipeline routingu, dzięki czemu uplink APRS-IS działa wyłącznie przez reguły flow (bez bocznego mechanizmu).
- `UI + I18N + testy`: edytor reguł pokazuje `Local TX` z opisem i zawęża listę targetów; dodano tłumaczenia `PL/EN` oraz testy walidacji i testy runtime dla scenariuszy `Local TX`.

## 1.8.16.dev - 17.05.2026

### Najważniejsze zmiany
- `APRS parser / Mic-E`: naprawiono dekodowanie `destination` z dozwolonym `ambiguity-space` (`K/L/Z`) zgodnie z regułami Mic-E, dzięki czemu poprawne ramki (np. `UQUQ1L`) nie są już odrzucane.
- `APRS parser / Mic-E`: dodano metadane pozycji przybliżonej (`position_ambiguity_digits`, `position_ambiguous`) oraz wyznaczanie współrzędnych jako reprezentacji pozycji nieprecyzyjnej zamiast fałszywej pełnej precyzji.
- `Stations/Map payload`: przekazano informacje o ambiguity do snapshotów stacji i payloadu mapy bez zmian w istniejącym renderowaniu warstw/markerów.
- `Testy`: dodano regresje dla poprawnej ramki Mic-E z ambiguity (`UQUQ1L`) oraz przypadek negatywny z niedozwolonym znakiem; utrzymano zielone testy parsera APRS i snapshot/map.

## 1.8.13.dev - 15.05.2026

### Najważniejsze zmiany
- `TNC SERIAL / close`: domyślnie wyłączono opuszczanie linii sterujących DTR/RTS przy zamknięciu portu (`drop_control_lines=False`), aby ograniczyć nieplanowane resety części urządzeń USB-serial.
- `TNC SERIAL / open`: dodano defensywne `O_CLOEXEC` (jeśli wspierane przez system) oraz doprecyzowano konfigurację portu do trybu raw `8N1` bez hardware/software flow control.
- `TNC SERIAL / flush`: zmieniono kolejność inicjalizacji portu: najpierw `tcsetattr`, potem opcjonalny `tcflush`, żeby czyścić bufory już po przełączeniu w docelowy tryb.
- `TNC SERIAL / IO`: `read_serial_chunk()` zwraca teraz `b""` po `InterruptedError` z `select`, a `write_serial_data()` używa jednego deadline dla całej operacji zapisu (z retry po `InterruptedError`), co stabilizuje timeouty pod obciążeniem.
- `Testy`: dodano testy niskopoziomowe modułu serial (`open/close/read/write`, `O_CLOEXEC`, `CRTSCTS`, semantyka timeoutów), bez wymogu fizycznego portu.

## 1.8.11.dev - 11.05.2026

### Najważniejsze zmiany
- `Messages / APRS queries`: dodano obsługę `?APRSD` z odpowiedzią `Directs= ...` (stacje słyszane bezpośrednio, bez zużytych hopów digi).
- `Messages / APRS queries`: dodano obsługę `?DX` z krótkim raportem `DX: D ... A ...` (najdalsza stacja direct oraz najdalsza stacja ogółem).
- `Messages / query list`: odpowiedź na `?APRS` została rozszerzona o nowe pozycje `?APRSD` i `?DX`.

## 1.8.10.dev - 11.05.2026

### Najważniejsze zmiany
- `Traffic Monitor / interfejsy`: dodano lokalny filtr widoczności ramek per interfejs TNC w GUI (`Pokaż/Ukryj` dla każdego aktywnego interfejsu), bez zmian w API i schemacie bazy.
- `Traffic Monitor / UX`: przełączniki filtrów interfejsów zmieniono na ikonowe (`eye` / `eye-off`) z zachowaniem `aria-label` i `title` dla dostępności.
- `Traffic Monitor / licznik`: licznik `entries` prezentuje teraz liczbę wpisów widocznych po aktywnych filtrach interfejsów.
- `Zakres zmian`: filtr działa wyłącznie po stronie frontend (stan sesyjny; po odświeżeniu strony wraca domyślny widok wszystkich interfejsów).

## 1.8.8.dev - 11.05.2026

### Najważniejsze zmiany
- `DIGI / Path rule`: obowiązkowy krok `Reguła ścieżki` rozszerzono o wbudowane guardy blokujące wejście ramki do kolejki DIGI/TX dla: `message/query` do lokalnych stacji (`My station`, `WX station`), ramek `third-party` (`}`) oraz ramek już powtórzonych przez lokalną stację (`CALL-SSID*` w path).
- `UI / nazewnictwo`: zmieniono nazwę kroku na `Reguła ścieżki i ochrona DIGI` (`Path rule and DIGI guard`) oraz dodano krótki opis i listę przypadków blokowanych przez guardy w edytorze reguł.
- `Diagnostyka`: dodano jednoznaczne kody przyczyny odrzucenia (`DIGI_GUARD_*`) w logu wykonania DIGI Flow.
- `Testy`: dodano regresyjne testy scenariuszy local `message/query`, `third-party`, `already repeated by local` oraz przypadków, które nie powinny być blokowane przez nowe guardy.

## 1.8.7.dev - 10.05.2026

### Najważniejsze zmiany
- `Nowy interfejs RX`: dodano typ `OpenWebRX MQTT (RX only)` z konfiguracją pełnym URL (`mqtt://`/`mqtts://`) i topiciem pobieranym ze ścieżki URL.
- `Bezpieczeństwo danych`: hasło w URL jest maskowane w UI i diagnostyce (`***`); pełny URL z hasłem nie trafia do logów/statusów błędów.
- `Runtime RX`: dodano odbiór ramek APRS z MQTT (JSON), akceptację `mode=APRS` (jeśli `mode` istnieje), odrzucanie invalid JSON z licznikiem oraz mapowanie do wspólnego pipeline TNC2.
- `OpenWebRX SONDE`: dodano obsługę `mode=SONDE` przez bezpieczne mapowanie do ramki `APRS Object` (źródło: lokalny `CALLSIGN-SSID` z `My Settings`), z zachowaniem danych telemetrycznych w komentarzu i symbolem balonu.
- `OpenWebRX ADSB`: dodano obsługę `mode=ADSB` przez bezpieczne mapowanie do ramki `APRS Object` (źródło: lokalny `CALLSIGN-SSID`), z ikoną samolotu i metadanymi lotu (`ICAO/flight/alt/speed/course/vspeed`) w komentarzu.
- `Deduplikacja wejściowa`: dla OpenWebRX MQTT dodano lokalne dedupe (okno 3 s) oraz licznik `duplicates_dropped` (`APRS`: `source+destination+path+raw+freq`, `SONDE/ADSB`: fingerprint telemetrii pozycyjnej/czasu).
- `Routing`: źródło `OpenWebRX MQTT` jest dostępne jako `source` w regułach DIGI, ale nie jest dostępne jako target TX (`tx_rf`); nie dodano auto-iGate, auto-DIGI ani TX przez MQTT.
- `Diagnostyka`: rozszerzono statusy/health runtime interfejsu o `connected`, `subscribed topic`, `broker host/port`, `last frame time`, `frames received`, `duplicates dropped`, `invalid JSON dropped`, `last error`.
- `Monitor ruchu / kolorowanie`: ujednolicono reguły kolorowania ramek tak, aby wszystkie ramki `TX` miały klasę koloru; `query (?)` i `telemetry` są traktowane jak kategoria wiadomości, a `object/item` jak kategoria pozycji/beacon.
- `Monitor ruchu / proxy`: ramki wysyłane przez udostępniony port TNC (`TX-PROXY`) mają własny kolor także wtedy, gdy źródłowy callsign jest lokalny.
- `Monitor ruchu / RX własne`: własne ramki odebrane (`RX`) zachowują ten sam podział kategorii co `TX`, z jaśniejszym wariantem kolorów.
- `Testy`: dodano testy regresyjne kolorowania dla `query`, `object` oraz `TX-PROXY`.

## 1.8.3.dev - 09.05.2026

### Najważniejsze zmiany
- `Beacon / Proportional Path`: dodano tryb `Proportional Path` w `My Settings -> Position Beacon`, aby promować prawidłową pracę RF (częste beacony lokalne, rzadsze szerokie ścieżki).
- `Beacon scheduler`: dla własnego beaconu pozycji dodano deterministyczny harmonogram efektywnej ścieżki (DIRECT / 1-hop / pełna), bez wysyłania kilku beaconów naraz w jednym ticku.
- `Health check konfiguracji`: dodano dynamiczną ocenę pary `Beacon co` + `Ścieżka beaconu` (`Zalecane`, `Do rozważenia`, `Niezalecane`) jako ostrzeżenie edukacyjne, bez twardej blokady zapisu.
- `UX bezpieczeństwa`: przy bardzo agresywnych ustawieniach dodano potwierdzenie przy zapisie konfiguracji; dla `Proportional Path` dodano tooltip z efektywnym harmonogramem zależnym od wybranej ścieżki.
- `Kompatybilność`: zachowano zgodność wsteczną istniejących konfiguracji interwału liczbowego (`fixed`), a nowy tryb działa jako rozszerzenie bez zmiany logiki DIGI/iGate/messages.

## 1.8.2.dev - 08.05.2026

### Najważniejsze zmiany
- `iGate RX-only / hot path`: przyspieszono tor `RF -> APRS-IS` przez wcześniejsze enqueue do runtime DIGI/APRS-IS (przed cięższymi efektami ubocznymi: DB/statystyki/band-condition/messages), aby ograniczyć opóźnienie względem innych iGate.
- `APRS-IS TX`: dodano krótki timeout `drain()` po stronie uplinku APRS-IS, żeby problemy sieciowe nie blokowały długo workera runtime.
- `Diagnostyka opóźnień`: dodano lekkie metryki czasu w logach debug (`rx_to_igate_enqueue_ms`, `igate_queue_wait_ms`, `rx_to_aprsis_write_ms`, `rx_to_db_commit_ms`) dla ramek RX.
- `Bezpieczeństwo routingu`: zachowano dotychczasową semantykę filtrów i guardów (`TCPIP/TCPXX`, `NOGATE/RFONLY`, third-party strict), bez zmian logiki DIGI RF TX i bez zmian formatu bazy.
- `Testy`: dodano test kolejności hot path (`enqueue` przed ciężkimi side-effectami) oraz test timeoutu `APRS-IS drain`; testy regresyjne modułów `traffic/aprsis/digi_flow_runtime` przechodzą.

## 1.8.1.dev - 08.05.2026

### Najważniejsze zmiany
- `APRS WX / parser`: dodano obsługę pola promieniowania `Xxxx` (nSv/h) zgodnie z `APRS-SPEC/weather-new.txt`; wartość nie trafia już do komentarza i jest prezentowana jako metryka `Promieniowanie` w szczegółach stacji.

## 1.8.0

### Stable release
- Wydanie stabilne z linii `dev`.

### Included development snapshots
- zmiany  od 1.7.37.dev do 1.7.47

## 1.7.47.dev - 07.05.2026

### Najważniejsze zmiany
- poprawki w statystykach, naprawa blednych wyliczeń TOP20 sprzet

## 1.7.47.dev - 06.05.2026

### Najważniejsze zmiany
- `Statystyki / zakresy`: utrzymano zakresy `1 godzina`, `1 dzień`, `7 dni`, `30 dni` (usunięto `rok` z selektora UI), z nawigacją okna `Wstecz/Dalej`.
- `Statystyki / agregacja`: dla `1 dzień` używany jest bucket `1h`, a dla dłuższych zakresów bucket `1d`; poprawiono wyliczanie granic bucketów dziennych (UTC), aby bieżący dzień był widoczny w widokach `7 dni` i `30 dni`.
- `Statystyki / TOP20 devices`: dodano numerację pozycji jako pierwszą kolumnę listy.
- `Statystyki / TOP20 devices`: poprawiono semantykę zliczania na `unikalne CALLSIGN-SSID per urządzenie` w wybranym oknie czasu (bez przypisywania stacji wyłącznie do jednego „dominującego” urządzenia), co eliminuje zaniżanie liczników dla urządzeń takich jak `TH-D75`.
- `Statystyki / TOP20 devices`: scalono duplikaty tego samego modelu wykryte przez różne identyfikatory (`TOCALL`/`Mic-E`) do jednej pozycji rankingu oraz ujednolicono `TOCALL APRS` jako `GENERIC APRS`, aby uniknąć równoległych pozycji `Unknown`/`Nieznany`.
- `Statystyki / TOP20 devices`: naprawiono podwójne zliczanie tej samej stacji w obrębie jednego modelu (np. kilka identyfikatorów `TH-D75` dla jednego `CALLSIGN-SSID`), więc licznik modelu odpowiada unikalnym stacjom.
- `Statystyki / TOP20 devices`: API zwraca teraz dodatkowe sumary (`unique_station_keys_total`, `unique_station_device_pairs_total`) do rozróżnienia „ile unikalnych stacji słyszano” vs „ile unikalnych wystąpień urządzeń (station-device) zliczono”.
- `Statystyki / TOP20 devices`: lista jest twardo ograniczona do 20 pozycji (nadmiar agregowany do `Inne`); tooltip pozycji zawiera `TOCALL`, `Identifier`, listę stacji dla wskazanego `TOCALL` oraz pełną listę stacji modelu, z której liczony jest ranking.
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
