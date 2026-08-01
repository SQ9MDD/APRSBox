# Kopia konfiguracji

Ten panel eksportuje i odtwarza migawkę konfiguracji GUI APRSBox w formacie `JSON` kodowanym jako UTF-8.

## Zakres kopii

Migawka zawiera wybrane ustawienia globalne oraz konfigurację źródeł map, interfejsów TNC i APRS-IS, stacji i WX, przepływów i reguł routingu, obiektów i elementów APRS, biuletynów oraz stacji referencyjnych warunków pasmowych.

Ruch runtime, logi zdarzeń, historia wiadomości, konta użytkowników i pozostałe tabele spoza obsługiwanego formatu kopii nie są uwzględniane.

Plik może zawierać znaki, dane połączenia APRS-IS, ścieżki, endpointy i inną konfigurację operacyjną. Traktuj go jako dane wrażliwe.

## Eksport i import

- `Eksportuj kopię konfiguracji` pobiera bieżącą migawkę.
- `Importuj kopię konfiguracji` sprawdza format i wersję, a następnie zastępuje obsługiwane tabele konfiguracji w jednej transakcji bazy.
- Błąd walidacji albo kontroli bazy wycofuje import.

Import nadpisuje bieżącą obsługiwaną konfigurację. Przed odtworzeniem innego pliku wyeksportuj obecny stan. Po udanym imporcie zrestartuj usługi APRSBox; w Dockerze odtwórz albo zrestartuj kontener narzędziem wdrożeniowym.
