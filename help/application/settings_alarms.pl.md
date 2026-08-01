# Ustawienia alarmów APRS

Ten panel konfiguruje odbiorczy kanał alarmowy dla wiadomości grupowych APRS. Określa, które grupy docelowe są traktowane jako alarmy, jakie zdarzenia trafiają na listę Alarmy, które mogą otworzyć popup w stylu emergency oraz jakie grupy są dopisywane do filtra odbiorczego APRS-IS.

## Szybka konfiguracja

- Włącz `Alarmy APRS`.
- Wpisz grupy rozdzielone przecinkami, na przykład `PL-WARN, NWS-WARN`.
- Ustaw progi `Alarmy` i `Popup alarmu` dla każdej kategorii zdarzeń.
- Zapisz ustawienia i sprawdź pokazane pod formularzem efektywne grupy RF oraz automatyczny filtr APRS-IS.

Nazwa grupy może zawierać 1–9 wielkich liter, cyfr lub myślników. Małe litery są zamieniane na wielkie, duplikaty są usuwane, a adresy biuletynów `BLN...` są odrzucane.

## Co dzieje się z odebraną ramką

- Tylko wiadomość APRS skierowana do włączonej i zapisanej grupy alarmowej trafia do tej ścieżki.
- Nazwa zdarzenia wybiera kategorię, na przykład tornado, burza, powódź, wiatr, upał albo `Inne / nieznane`.
- Końcowe cyfry kodu zdarzenia są interpretowane jako poziom ważności.
- `Alarmy` decydują, czy ramka utworzy lub zaktualizuje wpis na liście Alarmy.
- `Popup alarmu` niezależnie decyduje, czy pierwsza ramka danego alarmu może otworzyć globalny popup.
- Warstwa mapy ma osobny przełącznik na stronie Mapa i wymaga lokalnej geometrii pasującej do każdego kodu obszaru.

Próg liczbowy przyjmuje wskazany poziom i poziomy wyższe. `Wył.` wyłącza kategorię w danej kolumnie. Nieznany poziom jest zachowywany, gdy kategoria jest włączona, aby nowy lub uszkodzony format nie został cicho odrzucony; nie otrzymuje klasyfikacji żółtej, pomarańczowej ani czerwonej i przy dostępnej geometrii jest szary.

## Obsługiwane formaty ostrzeżeń

- [Szczegółowa pomoc CAWF](settings_alarms_cawf.pl.md) — profile krajowe, takie jak `PL-WARN`, alarmy wieloczęściowe, geometria, cykl życia i zaufanie.
- [Szczegółowa pomoc NWS-WARN](settings_alarms_nws_warn.pl.md) — amerykański format ostrzeżeń powiatowych, kody UGC, pokrycie mapy i ograniczenia APRSBox.
- [Lista Alarmy, wyciszanie i usuwanie](alerts.pl.md) — działania operatora po przyjęciu alarmu.

## Ważne granice

- Przełącznik dotyczy skonfigurowanych grup alarmowych. Natywne ramki APRS emergency oraz Mic-E emergency korzystają ze wspólnego systemu Alarmy niezależnie od niego.
- Wiadomości grup alarmowych nie trafiają do zwykłych rozmów, nie uruchamiają standardowych transportów powiadomień o wiadomościach i nigdy nie otrzymują APRS ACK.
- APRSBox nie uwierzytelnia obecnie wydawców ostrzeżeń i nie ma listy zaufanych nadawców dla grup. Sam odbiór przez APRS-IS nie dowodzi, że ostrzeżenie jest oficjalne.
- Nieprawidłowego lub brakującego czasu `DDHHMMz` nie można automatycznie rozwiązać. Taki wpis może pozostać aktywny do zastąpienia albo ręcznego usunięcia.
