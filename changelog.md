# Changelog

## 1.10.16.dev - 20.08.2026
- `Wiadomości APRS / lista konwersacji`: listę przebudowano na zwarte, jednowierszowe rekordy ze stałymi kolumnami dla zaznaczenia, znaku, stanu słyszalności, stanu przeczytania i usuwania; czas od ostatniej ramki przeniesiono do tooltipa wiersza, a wskaźniki ujednolicono za pomocą ikon Material Design.
- `Wiadomości APRS / usuwanie zbiorcze`: dodano checkboxy przy konwersacjach oraz wspólny checkbox ze stanem pośrednim w nagłówku listy, wyrównany nad kolumną zaznaczeń; przycisk usuwania zaznaczonych znajduje się nad kolumną koszy i usuwa wybrane konwersacje wraz z ich wiadomościami po jednym potwierdzeniu.

## 1.10.15.dev - 16.08.2026
- `Ustawienia / HTTPS`: dodano panel zarządzania certyfikatem `aprsbox.crt`, kluczem `aprsbox.key` i opcjonalnym łańcuchem CA w `/opt/aprsbox/data/ssl`; interfejs sprawdza zgodność certyfikatu z kluczem, pokazuje statusy plików, obsługuje upload i bezpieczne usuwanie oraz pozwala pobrać łańcuch CA. Generator lokalnego PKI i pobieranie Root CA pozostają na razie nieaktywne.
- `HTTPS / uruchamianie`: przełącznik zapisuje stan HTTPS i restartuje usługi; tryb HTTP działa na porcie `8000`, natomiast tryb HTTPS wyłącza ten listener, uruchamia Uvicorn z TLS na `443` i osobną usługę przekierowującą port `80` do HTTPS kodem `308`.
- `Instalator / aktualizator`: dodano obsługę redirectora i nowych jednostek Uvicorn dla systemd oraz OpenRC, rezygnując z uruchamiania web i core przez Gunicorna; poprawiono migrację jednostek, przekazywanie stanu HTTPS, uprawnienie `CAP_NET_BIND_SERVICE` oraz działanie kolejnych aktualizacji uruchamianych z GUI.
- `HTTPS / niezawodność i pomoc`: restart końcowy jest wykonywany poza cgroup usługi web i raportuje pełny postęp, przejście między HTTP i HTTPS czeka na podniesienie usług i czyści stary stan zadania, a katalog SSL jest naprawiany do `aprsbox:aprsbox` z trybem `0750`; dodano lokalizowaną pomoc opisującą mDNS, SAN dla nazw DNS i certyfikaty wystawiane dla adresów IP.

## 1.10.14.dev - 16.08.2026
- `GUI / alarmy`: pozycja `Alarmy` w sidebarze jest ukrywana, gdy opcja `Włącz alarmy APRS` jest wyłączona.

## 1.10.12.dev - 15.08.2026
- `Ustawienia / modale`: natywne okna przeglądarki `confirm` i `prompt` zastąpiono wspólnym modalem APRSBox dla aktualizacji aplikacji, importu konfiguracji, konserwacji bazy, restartu usług oraz operacji na hoście; potwierdzenia `REBOOT` i `POWER OFF` wymagają wpisania właściwej frazy, a przycisk zamknięcia modala postępu pojawia się dopiero po zakończeniu operacji.
- `Ustawienia / źródła map`: zapis i edycja źródła, zmiana kolejności, ustawienie domyślnego źródła, usuwanie oraz czyszczenie cache używają teraz tego samego asynchronicznego modala ze spinnerem, lokalizowanym komunikatem wyniku i obsługą błędów jak pozostałe akcje systemu; zachowano walidację formularza przed wysłaniem.

## 1.10.11.dev - 15.08.2026
- `GUI / pomoc`: wspólny modal wszystkich plików pomocy ma teraz widoczny, cienki pasek przewijania dopasowany kolorystycznie do aktywnego motywu; przewijanie pozostaje wewnątrz okna i nie przenosi się na stronę pod modalem.
- `APRS / wybór symbolu`: listy symboli w `Mojej stacji`, `Obiektach / Elementach` oraz filtrze ikon `Packet Flow` pokazują teraz obok ikony i kodu oficjalny opis z indeksu symboli aprs.fi; opis oraz podgląd zmieniają się zgodnie z wybraną tablicą podstawową `/` lub alternatywną `\`.
- `APRS / ikony modern`: naprawiono uszkodzone symbole `/!` (posterunek policji), `\!` (alarm) oraz `/q` i `\q` (warianty siatki kwadratowej), zastępując błędne lub zawierające cały arkusz pliki prawidłowymi kafelkami ze źródłowych arkuszy ikon.

## 1.10.10.dev - 14.08.2026
- `Packet Routing / zapis`: włączanie i wyłączanie reguł oraz zapis w edytorze używają teraz standardowego modala APRSBox ze spinnerem, komunikatem wyniku i obsługą błędów bez przeładowania strony; po udanym zapisie użytkownik wraca do właściwej listy lub edytowanej reguły.
- `GUI / pomoc`: wszystkie przyciski pomocy mają ikonę powiększoną o 50% oraz stały niebieski akcent ikony, obramowania i tła, dzięki czemu są jednoznacznie rozpoznawalne we wszystkich widokach i paletach kolorystycznych.
- `Mapa / siatka QTH`: zmniejszono rozmiar etykiet czteroznakowych lokatorów przy powiększeniu `6`, aby ograniczyć ich dominowanie i nakładanie się w gęstym widoku siatki.

## 1.10.9.dev - 14.08.2026
- `Wiadomości APRS / zgodność`: odbiór wiadomości, potwierdzeń `ack` i odrzuceń `rej` obsługuje teraz alfanumeryczne identyfikatory o długości od 1 do 5 znaków; ponownie odebrana numerowana wiadomość od tego samego nadawcy nie tworzy duplikatu nawet po zmianie konwersacji, ale nadal otrzymuje ponowne potwierdzenie.

## 1.10.8.dev - 14.08.2026
- `Pulpit / gotowość stacji`: przebudowano ocenę wokół połączenia APRS-IS, flow `Local TX → APRS-IS`, zdefiniowanego beaconu oraz kompletności kierunków `RF → APRS-IS`, `APRS-IS → RF` i `RF → RF` dla aktywnych interfejsów; stany są prezentowane ikonami, a liczba aktywnych interfejsów ma kolor zielony dla kompletu, ciemnożółty dla części i czerwony dla zera.
- `Pulpit / układ`: kafelek gotowości przeniesiono do widocznej części obok wykresu, usunięto kafelki ostatnich ważnych zdarzeń oraz powtórzonego podsumowania interfejsów i aktywności RF, a pozostałą zawartość dopasowano do bieżącego okna; usunięto również mylący łączny licznik gotowości, który pomijał wyłączone interfejsy.
- `Pulpit / pomoc konfiguracji`: link konfiguracji w kafelku gotowości zastąpiono standardową ikoną pomocy osadzoną w kafelku; dodano przystępny przewodnik w czterech językach, prowadzący przez `Interfejsy → Moja stacja → Packet Routing` oraz wyjaśniający różnicę między własnym flow `Local TX → APRS-IS` a uplinkiem ramek odebranych przez RF. Automatyczne odświeżanie pulpitu jest wstrzymywane podczas czytania pomocy i otrzymuje pełne 30 sekund po jej zamknięciu.
- `Ustawienia / sprawdzanie wersji`: przycisk `Sprawdź wersję` pobiera teraz bezpośrednio plik `VERSION` z GitHub przez HTTPS, dzięki czemu działa również w obrazie Docker, w którym nie ma programu `git`; dla innych źródeł zachowano dotychczasowy mechanizm Git. Porównanie wersji nie proponuje już „aktualizacji” nowszej wersji developerskiej do starszego wydania stabilnego.

## 1.10.7.dev - 14.08.2026
- `Mapa / backend stacji`: dodano trwałą projekcję `map_station_state`, aktualizowaną podczas odbioru i nadawania ramek APRS oraz odtwarzaną z historii; endpointy mapy nie rekonstruują już stanu przez ponowne parsowanie `traffic_frames` (zmierzony TTFB `stations-lite` spadł z ok. `3,4 s` do ok. `63 ms`).
- `Stacje / odświeżanie`: mapa i lista stacji czytają gotową projekcję, a polling według rewizji pobiera tylko zmienione rekordy i informacje o usunięciach; podsumowanie RF również nie skanuje historii.
- `Pulpit / wydajność`: stan ostatnio słyszanych stacji i początkowy wykres korzystają z istniejących projekcji, KPI ruchu są liczone jednym zapytaniem, a lista słyszanych stacji nie jest ponownie parsowana z `traffic_frames`, gdy dostępny jest bufor godzinowy.

## 1.10.6 - 13.08.2026
- `Wydanie stabilne`: scalono zmiany z wersji `1.10.2.dev–1.10.5.dev`, obejmujące bezpieczniejszą kopię konfiguracji v2, ujednolicone akcje i modale GUI, poprawki ergonomii oraz przewijania, automatyczne odświeżanie APRS Device Identification, warstwę siatki Maidenhead/QTH z adaptacyjną dokładnością i obsługą obu motywów, naprawę zawijania świata na mapie oraz standardowy modal potwierdzenia aktualizacji aplikacji.

## 1.10.5.dev - 13.08.2026
- `Ustawienia / aktualizacja aplikacji`: natywne pytanie przeglądarki przed rozpoczęciem aktualizacji zastąpiono standardowym modalem APRSBox, zgodnym z pozostałymi potwierdzeniami oraz jasnym i ciemnym motywem; modal obsługuje anulowanie, klawisz Escape, kliknięcie tła i prawidłowe przywracanie fokusu.

## 1.10.4.dev - 13.08.2026
- `Mapa / Maidenhead QTH Locator`: dodano opcjonalną warstwę siatki lokatorów z zapamiętywanym przełącznikiem; poziom szczegółowości zmienia się z zoomem od pól 2-znakowych przez lokatory 4- i 6-znakowe do 8-znakowych pól rozszerzonych.
- `Mapa / siatka QTH / czytelność`: etykiety są centrowane w rzeczywistych granicach pól projekcji Web Mercator, dynamicznie dopasowują rozmiar do kratki i mają osobne kontrastowe kolory, obwódki oraz linie dla jasnego i ciemnego motywu.
- `Mapa / zawijanie świata`: długość geograficzna zapisanego widoku i poleceń centrowania jest normalizowana do zakresu `-180…180°`, a `worldCopyJump` zapobiega pozostawaniu na sąsiedniej kopii świata bez markerów, tras i zasięgów.

## 1.10.3.dev - 09.08.2026
- `GUI / akcje i modale`: ujednolicono zapis, wysyłanie i usuwanie w Interfejsach, Mojej stacji, WX, Powiadomieniach, Obiektach i Biuletynach; akcje używają wspólnych potwierdzeń, modala ze spinnerem i komunikatu wyniku.
- `Powiadomienia / Packet Routing`: formularze zachowują pozycję edytowanego bloku, a edytor flow ma akcje w kolumnie bieżących kroków, wysokość dopasowaną do ich zawartości i niezależnie przewijany katalog filtrów oraz reguł.
- `GUI / przewijanie i mapa`: dodano dyskretne scrollbary zgodne z motywem w katalogu routingu, konwersacjach, Monitorze ruchu i scrollerze mapy; kliknięcie stacji w scrollerze centruje ją na mapie.
- `APRS Device Identification`: wejście do Ustawień cicho odświeża bazę w tle, gdy nie była wcześniej aktualizowana lub ostatnia udana aktualizacja ma ponad 30 dni; nieudane próby mają 24-godzinny odstęp.
- `Ustawienia / ergonomia`: akcje, edycja źródeł mapy i przeładowania po zapisie zachowują aktywny panel oraz pozycję przewinięcia zamiast wracać na początek strony.

## 1.10.2.dev - 08.08.2026
- `Kopia konfiguracji v2`: uzupełniono zakres eksportu i wprowadzono bezpieczny import bez zrywania powiązań runtime; pliki v1 nie są obsługiwane.

## 1.10 - 06.08.2026
- `Wydanie stabilne`: scalono zmiany z wersji `1.9.1.dev–1.9.8.dev`, obejmujące alarmy APRS i pogodowe, nowy Dashboard, rozwój warunków pasma, uporządkowanie APRS-IS i GUI, rozbudowaną pomoc, filtry stacji oraz bezpieczniejszą aktualizację aplikacji i obsługę zadań systemowych.

## 1.9.8.dev - 05.08.2026
- `Ustawienia / zadania systemowe`: aktualizacja aplikacji, restart usług, restart hosta i wyłączenie hosta przekazują identyfikator zadania oraz ścieżkę bazy jawnie do skryptów przez granicę uprawnień, dzięki czemu status i postęp są zapisywane w tym samym rekordzie także po użyciu `sudo`.
- `Ustawienia / odzyskiwanie zadań`: monitor statusu wykrywa osierocone zadania aktualizacji lub restartu, które utknęły na etapie uruchamiania i których proces już nie działa; oznacza je jako błąd i wyświetla komunikat zalecający sprawdzenie zainstalowanej wersji przed ponowną próbą.

## 1.9.7.dev - 04.08.2026
- `Stacje / filtry`: dodano zwarty, jednorzędowy pasek kafelków z ikonami i tooltipami oraz filtr `Słyszane bezpośrednio` dla stacji odebranych przez RF bez zużytego hopu digi.
- `Ustawienia / aktualizacja aplikacji`: modal pokazuje rzeczywisty etap i procent postępu, zachowuje stan podczas restartu WWW i kończy operację wyłącznie po terminalnym statusie procesu zamiast po samym powrocie endpointu zdrowia.

## 1.9.6.dev - 01.08.2026
- `Ustawienia / Pomoc`: dodano osobną pomoc Markdown dla 8 paneli w EN/DE/PL/ES/TLH i uproszczono interfejs, usuwając powtórzone opisy.
- `Pomoc / renderer`: dodano bezpieczne otwieranie zewnętrznych linków z dokumentów pomocy.
- `Alarmy / pomoc`: dodano podlinkowane, źródłowe przewodniki CAWF i NWS-WARN w EN/DE/PL/ES/TLH, obejmujące format ramek, fragmentację, UGC, mapę, cykl życia, progi i ograniczenia zaufania.

## 1.9.5.dev - 31.07.2026
- `Warunki pasma / GUI i runtime`: zakładka jest ukrywana, a zbieranie i przetwarzanie danych wyłączane, gdy żaden aktywny interfejs RF nie ma włączonej oceny pasma; pozostałe statystyki radiowe działają bez zmian.
- `Alarmy / formaty`: dodano odbiór i obsługę alarmów pogodowych w formatach `CAWF` oraz `NWS-WARN`.
- `Alarmy / Polska / obszary organizacyjne`: dodano granice powiatów oraz mapowanie identyfikatorów obszarów ostrzeżeń, dzięki czemu alarmy mogą wyświetlać odpowiadające im obszary na mapie.
- `Mapa / wydajność / pierwsze wczytanie`: obszary alarmowe są dociągane osobno po podstawowych danych mapy, a ikony stacji z opisami pojawiają się progresywnie w priorytetyzowanych paczkach, dzięki czemu kafelki nie pozostają długo bez markerów i mapa zachowuje responsywność.

## 1.9.4.dev - 29.07.2026
- `GUI / treść`: przejrzano wszystkie główne ekrany i usunięto nadmiarowe opisy sekcji, powtórzone instrukcje oraz oczywiste podpowiedzi; zachowano stany, wymagania formatu, walidację i ostrzeżenia dotyczące RF lub operacji administracyjnych.
- `Dashboard / stacja`: usunięto opis stanu odbioru i datę ostatniej aktywności RF z głównej karty stacji oraz zmniejszono jej wysokość i odstępy.

## 1.9.3.dev - 29.07.2026
- `Interfejsy / APRS-IS`: usunięto osobną pozycję `Ustawienia iGATE`; serwer, port, login, passcode, filtr oraz diagnostyka połączenia są teraz dostępne bezpośrednio w formularzu interfejsu `APRS-IS (RX/TX)`, a stary adres przekierowuje do tego interfejsu.
- `Interfejsy / formularz`: formularz używa stałej części wspólnej i osobnych paneli dla SERIALL, TCP, OpenWebRX MQTT oraz APRS-IS, dzięki czemu pola nie zmieniają przypadkowo kolumn i kolejności po przełączeniu typu połączenia.
- `Interfejsy / APRS-IS / GUI`: połączenie APRS-IS jest teraz prawidłowo opisane jako RX/TX; przełącznik `Włącz połączenie APRS-IS` steruje całym wspólnym transportem, a kolumna TX pokazuje stan aktywnego flow `TX APRS-IS` zamiast pozornej blokady TNC.
- `Interfejsy / APRS-IS / runtime`: wyłączenie połączenia zatrzymuje zarówno odbiór, jak i transmisję APRS-IS; poprawiono też faktyczne ukrywanie pól przeznaczonych wyłącznie dla fizycznych TNC.
- `Packet Routing / APRS-IS`: źródło i cel APRS-IS są dostępne tylko po zdefiniowaniu interfejsu APRSIS, a walidacja backendowa blokuje zapis i ponowne włączenie takich flow po usunięciu interfejsu.
- `Packet Routing / Interfejsy / GUI`: uproszczono formularze przez usunięcie opisów i powtórzonych etykiet dostępnych już w rozbudowanej pomocy; pozostawiono komunikaty bezpieczeństwa, walidację i dynamiczne wartości konfiguracji.
- `Pomoc / I18N`: pomoc TNC oraz tłumaczenia PL/EN/ES/DE opisują wysyłkę `Receiver RF → TX APRS-IS` i `Local TX → TX APRS-IS` przez to samo połączenie.

## 1.9.2.dev - 29.07.2026
- `GUI / menu`: uporządkowano kolejność pozycji i sekcji menu bocznego oraz uproszczono pasek użytkownika do kompaktowych, wyrównanych ikon.
- `GUI / beacon`: dodano podręczny przycisk wysyłania beacona z centralnym potwierdzeniem oraz 10-sekundową blokadą ponownego użycia, sygnalizowaną wyszarzeniem ikony.

## 1.9.1.dev - 29.07.2026
- `Alarmy APRS emergency`: dodano osobną zakładkę z konsolidacją ramek według pełnego znaku źródłowego, historią powiązanych ramek, licznikiem, wyciszaniem czasowym lub bezterminowym oraz bezpiecznym usuwaniem bez kasowania ramek z Monitora ruchu.
- `Alarmy / GUI`: dodano globalny modal alarmowy, oznaczenia i odnośniki w Monitorze ruchu, listę i szczegóły alarmu, licznik w menu oraz ponowne wyświetlanie modala dla kolejnych niewyciszonych ramek; pomoc opisuje wymagane zezwolenie przeglądarki na automatyczne odtwarzanie dźwięku.
- `Dashboard`: przebudowano ekran główny, dodając czytelniejsze KPI z wybranego zakresu, wykres aktywności RF oraz zwarte podsumowania konfiguracji, usług i stanu runtime.
- `Warunki pasma / mapa`: historia propagacji ma zakresy `24h / 7d / 30d / 365d` i punkt bieżącej godziny; poprawiono również zachowanie ostatniego widoku mapy oraz globalne ustawienie wypełnienia zasięgu.

## 1.9.0 - 26.07.2026
- `Wydanie stabilne`: scalono do `main` duży pakiet zmian z wersji `1.8.45.dev–1.8.57.dev`, obejmujący APRS-IS/iGate, wiadomości, warunki pasma, monitor ruchu, mapę, GUI, wydajność i instalator Alpine.

## 1.8.57.dev - 25.07.2026
- `Warunki pasma / interfejsy`: ocena propagacji jest teraz opcjonalna dla każdego interfejsu i domyślnie wyłączona; do wyboru pozostają `2 m` oraz `70 cm`, bez ręcznego wskazywania stacji referencyjnych.
- `Warunki pasma / model W0–W5`: dodano automatyczne uczenie typowej słyszalności stacji stałych osobno dla każdego interfejsu. Pierwsza ocena pojawia się po 24 godzinach, a wykrywanie otwarć uwzględnia liczbę stacji, typowy zasięg, odległości, dalekie stacje i nowe obszary geograficzne.
- `Warunki pasma / pewność i historia`: dodano konserwatywny, rosnący wraz z ilością danych indeks pewności — ograniczony do 30% po pierwszej dobie, 55% po tygodniu i 90% po 30 dniach — prosty wskaźnik W0–W5 z czytelną legendą skali, wykres godzinowy obejmujący ostatnie 365 dni oraz osobny, dyskretny blok pokazujący zebrane dane, etap uczenia i postęp do pierwszej oraz dojrzałej oceny.
- `Warunki pasma / wydajność`: analizę przeniesiono z gorącej ścieżki odbioru ramek do wspólnego agregatora pięciominutowego; ramki są parsowane jednokrotnie, a szczegółowe obserwacje i historia mają ograniczoną retencję.

## 1.8.56.dev - 24.07.2026
- `Wiadomości / APRS-IS`: naprawiono ACK i automatyczne odpowiedzi do lokalnej stacji; wracają przez `Local TX → APRS-IS`, bez TX RF.
- `Monitor ruchu / kolory`: dodano oznaczanie wierszy według pochodzenia i kierunku ramek, modalną legendę oraz alarmowe wyróżnienie `APRS-IS → RF` na żółto ze znacznikiem `IS → RF`.
- `APRS-IS → RF`: dodano szybkie czyszczenie znaku i promienia, przywracające tryb tylko wiadomości.

## 1.8.55.dev - 23.07.2026
- `iGate / wiadomości`: obowiązkowa reguła dostarczania automatycznie używa wszystkich aktywnych TNC z dozwolonym TX; zakwalifikowane wiadomości i powiązana pozycja omijają regułę znaku i promienia, a jej puste pola ustawiają tryb tylko wiadomości.
- `Routing / logi`: kroki, które nie dotyczą pakietu lub zostały ominięte, mają stan `pominięto` zamiast `przeszedł`.

## 1.8.54.dev - 23.07.2026
- `APRS-IS / routing`: dodano APRS-IS jako interfejs oraz bezpieczny routing `APRS-IS → RF`.
- `iGate / wiadomości`: dodano dwukierunkowe bramkowanie wiadomości APRS z kontrolą lokalnej osiągalności i poprawnym `qAR`/`qAO`.

## 1.8.53.dev - 14.07.2026
- `Wiadomości / rozmowy grupowe`: dodano wątki dla jawnie skonfigurowanych grup docelowych z oznaczeniem nadawcy; pozostałe grupy są ignorowane, a wysyłka grupowa odbywa się jednokrotnie, bez numeru wiadomości, ACK i retry.
- `Wiadomości / ustawienia / GUI`: dodano domyślną ścieżkę, odbiór dla dowolnego SSID własnego znaku oraz walidowaną listę grup (`ALL`, `QST`, `CQ` przy pierwszym użyciu); panel uproszczono i uzupełniono wielojęzyczną pomoc.

## 1.8.52.dev - 08.07.2026
- `GUI / layout / spójność`: uporządkowano marginesy, odstępy i ramki między ekranami; ujednolicono widoki `Mapa`, `Monitor ruchu`, `Statystyki`, `Moja stacja` i formularze ustawień oraz dopracowano zwijany sidebar.

## 1.8.50.dev - 05.07.2026
- `Pomoc / GUI / I18N`: dodano komplet lokalnych plików pomocy Markdown w `PL/EN/ES/DE` dla zakładek `Ustawienia iGate`, `Powiadomienia`, `Wiadomości`, `WX`, `Moja stacja` i `TNC`, podpięto je pod kontekstową ikonę pomocy oraz ujednolicono jej pozycję w nagłówkach ekranów.

## 1.8.49.dev - 29.06.2026
- `Wydajność / runtime / SQLite`: odciążono gorące ścieżki na słabszych maszynach: radar sprawdza `radar_enabled` przed kosztowną analizą, cleanup `traffic_frames` wypadł z RX hot path do batch cleanupu w maintenance schedulerze, dodano krótkie cache dla snapshotów traffic/stations, indeksy SQLite dla hot-path wiadomości/outbound, scheduler WX przenosi blokujące odświeżanie do wątku, a strona `Messages` nie odpytuje już podwójnie `unread-status`.
- `Mapa / pierwsze wczytanie / render`: pierwsze wejście na mapę używa lekkiego payloadu markerów (`stations-lite`), a szczegóły stacji i `mobile_tracks` są dociągane osobno po pierwszym renderze; frontend aktualizuje teraz markery, zasięgi PHG i tracki przyrostowo zamiast pełnego redraw, co skraca oczekiwanie na punkty i usuwa mruganie overlayów.

## 1.8.48.dev - 25.06.2026
- `Traffic Monitor / filtry`: w odpowiedzi na GitHub `issue #53` (`Traffic monitor - filters`) główny toolbar dostał frontendowe szybkie filtry `RX`, `TX` i zdalnego `TX` od klientów, tekstowy filtr typu grep oraz przycisk `Clear filters`; wszystkie filtry działają na żywo także dla kolejnych odświeżeń SSE, bez zmian w backendzie.

## 1.8.47.dev - 25.06.2026
- `GUI / sidebar / scrolling`: w odpowiedzi na GitHub `issue #54` (`Menu panel independent scrolling`) sidebar na desktopie przewija się teraz niezależnie od głównej zawartości, a jego scrollbar pozostaje ukryty.

## 1.8.46.dev - 23.06.2026
- `Settings / Global settings / Traffic frames`: dodano globalne ustawienie retencji historii ruchu (`1h` do `6h` co `30 min`, plus `12h` i `24h`, domyślnie `1h`), które steruje cleanupem tabeli `traffic_frames`; widoczność stacji, obiektów i śladów na mapie wynika teraz bezpośrednio z tego okna retencji danych.
- `Wiadomości / TX / multi-TNC`: naprawiono obsługę błędów wysyłki przy `Transmit on all active interfaces`; pojedynczy błąd jednego TNC nie oznacza już całej wiadomości jako `failed`, jeśli ta sama runda TX nadal trwa na innych interfejsach albo jeden z nich nadał poprawnie.
- `Wiadomości / retry`: wiadomość przechodzi teraz na `failed` dopiero wtedy, gdy cała runda wysyłki dla danego `scheduled_at` zakończy się bez żadnego `sent`, co przywraca retry/ACK flow dla przypadków `fail + success` w multi-TNC.

## 1.8.45.dev - 22.06.2026
- `Moja stacja / Beacon`: znak stacji w formularzu beaconu ograniczono do maksymalnie 6 drukowalnych znaków ASCII, z walidacją także po stronie backendu.
- `Moja stacja / Beacon`: pola `znak stacji` i `Beacon Path` są teraz automatycznie normalizowane do wielkich liter w formularzu i przy zapisie.
- `Moja stacja / Lokalizacja`: ręczna edycja pól `szerokość` i `długość geograficzna` została zablokowana; współrzędne są teraz ustawiane wyłącznie przez przycisk `Pobierz lokalizację`.
- `Settings / Global settings`: przycisk `Save Global Settings` przeniesiono na dół bloku, a `Coverage fill opacity` ma domyślnie `10%`, o ile użytkownik nie zapisał własnej wartości.
- `Settings / Global settings / I18N`: uzupełniono brakujące tłumaczenia pola `Icon set`, listy opcji oraz opisu pod selectem.

## 1.8.44 - 22.06.2026

### Stable release
- Migracja wydania z gałęzi `dev` do `main`.

### Included development snapshots
- zmiany od `1.8.25.dev` do `1.8.43.dev`

### Najważniejsze zmiany
- `Mapa / UX / diagnostyka`: przebudowano widok mapy i monitor sytuacyjny: lepszy layout viewportu, scroller `Latest packet` / ostatni digi, filtry per interfejs TNC, poprawki tooltipów oraz dopracowane renderowanie ikon APRS.
- `Routing / TX / APRS-IS`: dodano logiczne źródło `Local TX`, neutralny tryb `Internal TX`, twarde guardy dla uplinku APRS-IS i lokalnie generowanych ramek oraz pacing/per-TNC dla kolejek TX.
- `DIGI / flow engine`: rozszerzono ochronę `Path rule and DIGI guard`, aktywowano `Rate limit filter`, wymuszono bezpieczną kolejność kroków RF i dodano propagację zmiany nazwy TNC do referencji flow.
- `Objects / Bulletins / content`: dodano planowane i cykliczne nadawanie obiektów, dokładność `Valid until` do minuty, wyliczanie timestampu obiektu przy realnym TX, ręczne `Send now`, ukrycie obiektów `killed` oraz lokalną pomoc Markdown dla `Objects` i `Bulletins`.
- `Integracje / RX / parser`: dodano `OpenWebRX MQTT (RX only)` z obsługą `APRS/SONDE/ADSB`, lokalną deduplikacją i rozszerzoną diagnostyką oraz poprawiono dekodowanie i prezentację danych Mic-E.
- `Utrzymanie / GUI / I18N`: dodano hiszpański i wielojęzyczne changelogi (`PL/EN/ES/DE`), guardy Docker mode dla akcji hosta, diagnostykę i bezpieczny reset danych runtime SQLite, powiadomienia Telegram/webhook, nowe logo sidebara oraz lokalne pliki pomocy.

## 1.8.43.dev - 21.06.2026
- `Traffic Monitor / KISS RX`: puste ramki danych KISS (`0x00` bez payloadu) z TNC TCP/IP są teraz ignorowane, więc monitor ruchu nie pokazuje już szumu `AX.25 decode failed (payload too short (0B))` między prawidłowymi pakietami.
- `Changelog / I18N`: dodano niemiecki plik changeloga i wybór treści `DE` zgodnie z aktualnym językiem GUI.

## 1.8.42.dev - 21.06.2026
- `GUI / sidebar / branding`: stary branding sidebara (ikonka + `APRSBox` + `Natywna konsola APRS`) zastąpiono nowym logo APRSBox renderowanym jako inline SVG.
- `GUI / sidebar / logo`: kolory logo podłączono do istniejącego systemu motywów i palet przez zmienne CSS, więc branding zmienia się automatycznie po przełączeniu motywu użytkownika.
- `GUI / sidebar / layout`: logo skaluje się responsywnie w obrębie aktualnej szerokości sidebara, bez poszerzania sidebara i bez rozbijania układu menu.

## 1.8.41.dev - 20.06.2026
- `Help / Objects / Bulletins`: dodano lokalne pliki pomocy Markdown dla zakładek `Objects` i `Bulletins / Announcements` w wariantach `PL/EN/ES`, wraz z podstawową nawigacją między dokumentami i podpięciem pod formularze GUI.

## 1.8.40.dev.mice - 17.06.2026
- `Mic-E / Station Details`: uzupełniono diagnostykę o dekodowane pola Mic-E w szczegółach stacji, bez osobnej sekcji i bez pustych etykiet; poprawiono też priorytet `message capable` względem surowego bajtu typu.

## 1.8.39.dev - 15.06.2026
- `Mapa / ikony modern`: wycentrowano overlay na ikonach oraz dodano lepszy cień dla czytelności.

## 1.8.38.dev - 14.06.2026
- `DIGI / Rate limit filter`: aktywowano istniejący bloczek `Filtr limitu tempa` dla flowów z `TX = tnc radio`; filtr przechowuje ostatnio przepuszczoną ramkę per instancja, odrzuca kolejne ramki przed upływem ustawionego limitu 5-60 s i loguje blokadę wraz z limitem.
- `DIGI / Rate limit filter`: dodano maskę znaku źródłowego z wildcardem `*`; limit działa teraz na pasujące znaki wywoławcze, a `*` obejmuje wszystkie źródła.
- `DIGI / Path rule`: dla flowów RF zachowano wymuszoną kolejność, tak aby `Filtr limitu tempa` był zawsze bezpośrednio przed `Reguła ścieżki i ochrony digi`.

## 1.8.37.dev - 11.06.2026
- `Objects / timestamp`: dla obiektów tymczasowych timestamp APRS jest teraz liczony dopiero przy realnym nadaniu ramki (`DDHHMMz`), a obiekty permanentne nadal używają stałego `111111z`.
- `DIGI / Path rule`: opis pola `Paths (TRACE / traced)` uzupełniono o przykładowe ścieżki `WIDE1-1`, `WIDE2-1` i `WIDE2-2`, a dla flowów z `TX = tnc radio` wymuszono sztywno kolejność: `Duplicate Filter (viscous-delay)` zawsze pierwszy, `Path rule and DIGI guard` zawsze ostatni.
- `Map / scroller / objects`: poprawiono wyświetlanie obiektów w prawym scrollerze mapy, żeby korzystały z właściwego `display_callsign`.

## 1.8.36.dev - 11.06.2026
- `Outbound/TX queue`: naprawiono pacing lokalnych ramek, tak aby opóźnione pakiety były ostatecznie nadawane zamiast być odkładane w nieskończoność.
- `DIGI / rename TNC`: zmiana nazwy TNC propaguje się teraz do referencji source/target w flowach DIGI oraz do konfiguracji kroków RF, więc routing dalej wskazuje ten sam interfejs.

## 1.8.35.dev - 11.06.2026
- `Outbound/TX queue`: dodano per-TNC pacing dla lokalnie generowanych ramek APRSBox, aby obiekty, biuletyny, beacon, WX, status i ręczny TX były rozkładane w czasie przed fizycznym nadaniem zamiast nadawania jeden po drugim.

## 1.8.34.dev - 09.06.2026
- `Objects / inbound-outbound`: obiekty `killed` nie trafiają już do widocznej listy/mapy, a ramki outbound nadal używają znacznika `_` dla killed object.
- `Objects / manual TX`: w edycji obiektu dodano przycisk `Wyślij`, który wymusza ręczne nadanie obiektu.
- `GUI / icons`: w ustawieniach globalnych dodano wybór zestawu ikon APRS (`legacy` / `modern`) i podłączono lokalny katalog PNG z nowymi symbolami do renderowania w całym GUI.

## 1.8.33.dev - 05.06.2026
- `Mapa / lista stacji`: usunięto mieszanie ikonek i kolorów w prawym scrollerze mapy przez lookup po bazowym znaku; wpisy korzystają teraz z dokładnego `display_callsign`.

## 1.8.32.dev - 03.06.2026
- `Powiadomienia / Telegram / webhooks`: zaimplementowano powiadomienia Telegram przez webhooki dla wiadomości i radaru stacji.

## 1.8.31.dev - 02.06.2026
- `Objects / Items`: dodano wysyłkę obiektów zaplanowanych i cyklicznych (`issue #31`, SQ2FRG).
- `I18N`: dodano tłumaczenia polskie.

## 1.8.30.dev - 01.06.2026

### Najważniejsze zmiany
- `My Station / TX target`: dodano nową opcję `Internal TX` jako neutralny tryb bez fizycznego nadajnika RF.
- `Changelog / I18N`: dodano obsługę wielojęzycznych plików changeloga (`PL/EN/ES`) z automatycznym wyborem treści na podstawie aktualnego języka GUI.
- `UX / dostępność`: opcja `Internal TX` jest dostępna stale na liście interfejsów nadajnika, niezależnie od konfiguracji flow.
- `UX / komunikaty`: w formularzu `My Station` dodano kontekstowy komunikat dla `Internal TX` z aktywnym `Local TX -> APRS-IS` (ramki mogą być przekazywane do APRS-IS).
- `UX / komunikaty`: w formularzu `My Station` dodano kontekstowy komunikat dla `Internal TX` bez aktywnego flow (`Internal TX` działa lokalnie jak `black hole`).
- `Outbound/runtime`: dla `Internal TX` joby są oznaczane jako `internal_tx_only`, nie wykonują transportu RF/TCP/serial, ale nadal generują ramkę i przekazują ją do pipeline `Local TX` (routing decyduje o dalszym losie, np. APRS-IS).
- `Logi i podgląd`: wpisy `Station TX Log` dla tego trybu pokazują interfejs `Internal TX` zamiast `Unknown interface`.
- `Testy`: dodano regresje dla `Internal TX` bez aktywnego APRS-IS flow, kolejkowania bez `interface_id` oraz ścieżki runtime bez prób transportu RF.

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
