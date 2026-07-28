# Alarmy APRS emergency

Zakładka `Alarmy` pokazuje logiczne alarmy utworzone z odebranych ramek APRS emergency. Kolejne ramki z tego samego pełnego znaku wywoławczego aktualizują jeden alarm i jego historię.

- Kliknięcie wiersza otwiera modal z najnowszą ramką emergency.
- Przycisk szczegółów alarmu otwiera pełny rekord i historię powiązanych ramek.
- Wyciszenie nie zatrzymuje aktualizacji alarmu ani licznika ramek.
- Usunięcie alarmu nie usuwa oryginalnych ramek z Monitora ruchu.

## Dźwięk alarmu w przeglądarce

Przeglądarki mogą domyślnie blokować automatyczne odtwarzanie dźwięku. Wtedy modal alarmu pojawi się prawidłowo, ale dźwięk rozpocznie się dopiero po kliknięciu na stronie.

Na komputerze, na którym jest wyświetlany APRSBox:

1. Otwórz uprawnienia witryny przy pasku adresu.
2. Znajdź ustawienie `Automatyczne odtwarzanie`.
3. Wybierz `Zezwalaj na dźwięk i wideo` albo równoważną opcję zezwalającą na dźwięk.
4. Odśwież kartę APRSBox.

To ustawienie trzeba wykonać w przeglądarce komputera z podglądem. Komputer uruchamiający serwer APRSBox może być innym urządzeniem.

Sprawdź również, czy karta, przeglądarka i system operacyjny nie są wyciszone oraz czy wybrane jest właściwe wyjście audio.

Po zezwoleniu na automatyczne odtwarzanie niewyciszona ramka emergency otwiera modal i uruchamia dźwięk bez dodatkowego kliknięcia. Alarm wyciszony nadal się aktualizuje, ale celowo nie odtwarza dźwięku.

## Wyciszanie

Dostępne są wyciszenia na `1 godzinę`, `4 godziny`, `24 godziny` oraz bezterminowe. Po upływie wyciszenia czasowego dopiero kolejna ramka emergency może uruchomić modal i dźwięk.

## Usuwanie

Usunięcie kasuje logiczny rekord alarmu i jego powiązania. Oryginalne ramki pozostają w Monitorze ruchu. Następna ramka emergency z tego źródła utworzy nowy alarm.
