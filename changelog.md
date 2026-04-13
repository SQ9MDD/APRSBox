# Changelog

## 1.4.67 - 14.04.2026

### Added
- W tabeli `Configured Packet Routing Flows` dodano numerację reguł.
- W `Actions` dodano przyciski do zmiany kolejności reguł (góra/dół) z zapisem kolejności w bazie danych.
- W widoku wiadomości dodano jednoznaczne oznaczenie statusu `Rejected (REJ)`.

### Changed
- W kolumnach `Source` i `Target` dla reguł routingu wyświetlana jest teraz sama nazwa endpointu, bez prefiksu typu (np. bez `receiver_rf:`).
- Dodano pełną obsługę protokołową `REJ` dla wiadomości APRS: `REJ` kończy proces wysyłki tak jak `ACK` (bez dalszych retry).

### Fixed
- Poprawiono rozróżnienie w GUI między brakiem `ACK` a odrzuceniem wiadomości przez `REJ`.

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
