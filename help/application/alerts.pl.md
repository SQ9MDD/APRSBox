# Alarmy APRS emergency

Zakładka `Alarmy` pokazuje logiczne alarmy utworzone z natywnych ramek APRS emergency oraz wiadomości grupowych CAWF i `NWS-WARN`. Wszystkie trafiają do tej samej listy i mają szczegóły, historię ramek, wyciszanie oraz usuwanie.

`NWS-WARN` służy do odbioru zwartych ostrzeżeń pogodowych dla powiatów USA. W szczegółach alarmu APRSBox pokazuje między innymi surowy kod i rozpoznany opis zdarzenia, opis poziomu, czas wygaśnięcia i kody obszarów UGC, a rozpoznane powiaty zaznacza na mapie. Widok wyraźnie odróżnia poziom CAWF (zdefiniowana skala żółty–pomarańczowy–czerwony) od sufiksu `NWS-WARN`, który jest mapowaniem wydawcy przekaźnika, a nie oficjalną ważnością NWS CAP. Jest to profil odbiorczy: alarmu `NWS-WARN` nie można wysłać ani odwołać z APRSBox. Konfigurację grupy, format ramki, poziomy, mapowanie obszarów i ograniczenia opisuje [szczegółowa pomoc NWS-WARN](settings_alarms_nws_warn.pl.md).

Alarm CAWF wysłany z formularza APRSBox również trafia do tej listy i zachowuje się jak każdy inny alarm.

## Interpretacja kodu i poziomu

W szczegółach alarmu surowy kod pozostaje widoczny obok opisu. Dla CAWF opis jest dobierany według rejestru zdarzeń CAWF v1, a poziomy `1`, `2` i `3` oznaczają odpowiednio żółty, pomarańczowy i czerwony. Kod spoza rejestru albo poziom spoza tej skali jest oznaczany jako nierozpoznany.

W `NWS-WARN` nazwa zdarzenia jest swobodnym tekstem nadawcy. APRSBox może przypisać rozpoznaną nazwę do opisowej kategorii, ale nie zastępuje to oficjalnego produktu NWS. Końcowa cyfra jest mapowaniem 1–3 przyjętym przez wydawcę przekaźnika, a nie oficjalnym poziomem ważności NWS CAP. Szczegółowe zasady opisują pomoce [CAWF](settings_alarms_cawf.pl.md) i [NWS-WARN](settings_alarms_nws_warn.pl.md).

Jeżeli pełny znak źródłowy alarmu CAWF jest identyczny ze znakiem skonfigurowanej stacji, na liście pojawia się przycisk `Odwołaj alarm`. Po potwierdzeniu APRSBox zatrzymuje powtórzenia i wysyła protokolarną ramkę CAWF `CANCEL` z tym samym źródłem, grupą i logicznym `ALERT_ID`.

Przycisk `Wyślij alarm` obok `Usuń zaznaczone` otwiera osobną stronę kreatora. W formularzu pole `Ścieżka (RF)` określa ścieżkę używaną podczas nadawania radiowego. Domyślnie wybrana jest ścieżka skonfigurowana dla stacji. `Direct (bez ścieżki)` nadaje bez hopów digi. Wybrana ścieżka jest zapisywana z alarmem i pozostaje taka sama dla jego powtórzeń oraz ramki `CANCEL`. Nie jest to wybór trasy serwerowej APRS-IS.

- Kliknięcie wiersza otwiera modal z najnowszą ramką alarmu.
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

Po zezwoleniu na automatyczne odtwarzanie niewyciszona ramka zakwalifikowana do popupu alarmowego otwiera modal i uruchamia dźwięk bez dodatkowego kliknięcia. Dotyczy to także `NWS-WARN`, jeżeli jego kategoria i poziom spełniają skonfigurowany próg popupu. Alarm wyciszony nadal się aktualizuje, ale celowo nie odtwarza dźwięku.

## Wyciszanie

Dostępne są wyciszenia na `1 godzinę`, `4 godziny`, `24 godziny` oraz bezterminowe. Po upływie wyciszenia czasowego dopiero kolejna ramka danego alarmu może uruchomić modal i dźwięk.

## Usuwanie

Usunięcie kasuje logiczny rekord alarmu i jego powiązania. Oryginalne ramki pozostają w Monitorze ruchu. Kolejna pasująca ramka może ponownie utworzyć alarm.
