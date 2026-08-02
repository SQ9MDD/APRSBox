# Aktualizacja aplikacji

Ten panel sprawdza zainstalowaną wersję APRSBox i — na obsługiwanych instalacjach — aktualizuje aplikację z wybranego kanału.

## Kanał aktualizacji

Kanał wskazuje gałąź źródłową używaną do sprawdzania wersji i aktualizacji. Kanał inny niż stabilny może zawierać niedokończone albo niekompatybilne zmiany; ostrzeżenie pozostaje widoczne, gdy taki kanał jest wybrany.

`Zapisz kanał aktualizacji` zmienia źródło kolejnych sprawdzeń i aktualizacji. Samo zapisanie kanału nie aktualizuje aplikacji.

## Akcje

- `Sprawdź wersję` porównuje wersję zainstalowaną z wybranym kanałem i niczego nie modyfikuje.
- `Aktualizuj aplikację` pobiera kod z tego kanału, uruchamia inicjalizację bazy i na końcu restartuje `aprsbox-core` oraz `aprsbox-web`.
- Podczas restartu GUI może chwilowo utracić połączenie. Okno postępu śledzi zadanie w tle i próbuje połączyć się ponownie.

## Instalacja Docker

W Dockerze porównanie wersji ma wyłącznie charakter informacyjny, a akcje aktualizujące host są wyłączone. Aktualizację wykonuje się przez pobranie odpowiedniego obrazu i odtworzenie kontenera narzędziem używanym przez wdrożenie.

Tylko administrator i operator mogą zmienić kanał lub rozpocząć aktualizację.
