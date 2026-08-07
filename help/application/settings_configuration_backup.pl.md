# Kopia konfiguracji

Ten panel eksportuje i odtwarza migawkę konfiguracji GUI APRSBox w formacie `JSON` kodowanym jako UTF-8.

## Zakres kopii

Migawka v2 zawiera ustawienia globalne, wiadomości i powiadomień oraz konfigurację źródeł map, interfejsów TNC i APRS-IS, stacji i WX, transportów i reguł radaru powiadomień, przepływów i reguł routingu, obiektów i elementów APRS, biuletynów oraz stacji referencyjnych warunków pasmowych.

Ruch runtime, wyniki testów transportów, stan radaru powiadomień, logi zdarzeń, historia wiadomości, własne alarmy APRS, konta użytkowników i pozostałe tabele spoza obsługiwanego formatu kopii nie są uwzględniane.

Plik może zawierać znaki, dane połączenia APRS-IS, ścieżki, endpointy, tokeny webhooków i Telegrama oraz inną konfigurację operacyjną. Traktuj go jako dane wrażliwe.

## Eksport i import

- `Eksportuj kopię konfiguracji` pobiera bieżącą migawkę.
- `Importuj kopię konfiguracji` sprawdza format i wersję, a następnie zastępuje obsługiwane tabele konfiguracji w jednej transakcji bazy.
- Błąd walidacji albo kontroli bazy wycofuje import.
- Obsługiwany jest wyłącznie format v2. Pliki v1 utworzone przez starsze wydania nie mogą zostać zaimportowane.

Import nadpisuje bieżącą obsługiwaną konfigurację. Przed odtworzeniem innego pliku wyeksportuj obecny stan. Po udanym imporcie zrestartuj usługi APRSBox; w Dockerze odtwórz albo zrestartuj kontener narzędziem wdrożeniowym.
