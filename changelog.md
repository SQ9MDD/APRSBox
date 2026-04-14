# Changelog

## 1.4.68.DEV - 14.04.2026

### Added
- W `Station Readiness` dodano pozycję `WX callsign`.
- W `Station Readiness` dodano listę `Active interfaces` z per‑interfejsowym statusem (`Enabled` / `Disabled` / `Connecting` / `Error` / `Unknown`).
- W `Station Readiness` dodano sekcję `Enabled services` ze statusami (`Enabled` / `Disabled`) dla: `Beacon enabled`, `Status enabled`, `WX enabled`, `iGate enabled`.
- Dodano nowe tłumaczenia UI dla etykiet dashboardu związanych z nową checklistą.

### Changed
- Dashboard został skompaktowany wizualnie (mniejsze odstępy, paddingi i wysokości kart), aby więcej treści było widoczne bez przewijania.
- W pierwszym bloczku statusu pozostawiono tylko podsumowanie stacji (usunięto skróty `Interface` i `Last traffic`).
- W `Station Readiness` `Callsign` zastąpiono polem `Main callsign` z dołączanym `SSID` (gdy ustawiony).
- W listach `Active interfaces` i `Enabled services` wprowadzono kolorowe badge statusów.
- Ujednolicono opisy statusów w checklistach do wspólnego formatu (`Enabled` / `Disabled` / `Connecting` / `Error` / `Unknown`).
- Wysokość panelu `Band Condition` została wyrównana do wysokości panelu po lewej stronie w górnym rzędzie dashboardu.

### Fixed
- Zaktualizowano testy dashboardu do nowego kontraktu danych checklisty (`entries` dla list statusów i nowe etykiety pól).
- Poprawiono wybór kanału aktualizacji aplikacji z GUI: `update.sh` otrzymuje teraz jawnie wybrany kanał jako argument `--git-branch`, co eliminuje sporadyczny fallback do `main` przy uruchomieniu przez `sudo`/`doas` bez przekazanego środowiska.

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
