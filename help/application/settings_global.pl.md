# Globalne ustawienia

Ten panel steruje wspólnymi ustawieniami wyglądu, retencji i logowania. Administratorzy i operatorzy mogą zapisywać zmiany, a użytkownicy z rolą podglądu widzą tylko bieżące wartości.

## Język i jednostki

- `Język` wybiera język interfejsu oraz pomocy kontekstowej.
- `Jednostki` przełączają wartości metryczne i imperialne tam, gdzie aplikacja obsługuje konwersję.
- `Zestaw ikon` wybiera starszy albo nowoczesny wygląd symboli APRS.
- `Paleta kolorów` zmienia paletę aplikacji dla wszystkich użytkowników.

## Ruch i logi zdarzeń

- `Retencja historii ruchu` określa, jak długo ramki runtime pozostają w bazie. Widoczność stacji na mapie i listach korzysta z tego samego okna.
- `Minimalny poziom zapisu logów` zapisuje wybrany poziom i wszystkie poziomy poważniejsze.
- `Włącz logi DEBUG` dopuszcza szczegółowe wpisy diagnostyczne. Warto włączać je tymczasowo, bo zwiększają liczbę zdarzeń.

## Wygląd zasięgu

- `Krycie wypełnienia zasięgu` jest zapisywane globalnie i steruje wnętrzem obszarów zasięgu na mapie.
- `Krycie obrysu zasięgu` dotyczy tylko obramowania i jest zapisywane lokalnie w bieżącej przeglądarce.
- Wartość `0%` ukrywa odpowiednio wypełnienie albo obrys.
- `Grupuj nakładające się ikony stacji na mapie` zastępuje blisko położone symbole niebieską ikoną z liczbą stacji. Opcja jest domyślnie wyłączona, aby mapa pokazywała osobne symbole APRS, dopóki operator świadomie nie włączy agregacji.
- `Włącz rozsuwanie nakładających się markerów` rozsuwa nachodzące na siebie pojedyncze markery po najechaniu myszą blisko maksymalnego zoomu; kliknięcie rozsuniętej ikony otwiera szczegóły stacji, a wyjście kursora poza obszar grupy ponownie ją składa. Na urządzeniach dotykowych pierwszy tap rozsuwa grupę, a drugi otwiera wybraną stację.
- `Aktywuj X poziomów przed maksymalnym zoomem` wyznacza próg względem maksymalnego zoomu aktywnego źródła mapy. Domyślne `2` oznacza aktywację od zoomu 14, 16 albo 18, gdy maksimum wynosi odpowiednio 16, 18 albo 20.
- `Odległość nakładania markerów [px]` określa, jak blisko mogą znajdować się środki widocznych markerów, zanim zostaną uznane za nakładające się. Wartość domyślna to `20` px.

Przycisk `Zapisz globalne ustawienia` zapisuje wartości globalne.
