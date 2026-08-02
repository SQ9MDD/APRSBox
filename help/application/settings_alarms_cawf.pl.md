# Ostrzeżenia CAWF w APRSBox

CAWF, czyli Common APRS Warning Format, jest zwartą i niezależną od kraju otoczką do dystrybucji publicznych ostrzeżeń terytorialnych jako wiadomości grupowych APRS. Ta pomoc opisuje CAWF v1 według dostarczonego draftu, a następnie wskazuje zachowanie i ograniczenia odbiornika APRSBox.

CAWF jest formatem transportowym. Nie zastępuje autorytatywnego krajowego źródła ostrzeżeń, CAP ani profilu NWS-WARN.

## Model od źródła do odbiornika

- Terytorialny CAWF HUB odczytuje źródło autorytatywne i mapuje jego typ zdarzenia, ważność oraz obszary zgodnie z opublikowanym profilem kraju.
- Wysyła jedną lub kilka wiadomości APRS do grupy ostrzeżeń. Zalecany wzorzec to `CC-WARN`, na przykład `PL-WARN`.
- APRSBox odbiera grupę przez RF lub automatycznie rozszerzony filtr APRS-IS, składa fragmenty, stosuje progi, zapisuje alarm i łączy kody obszarów z lokalną geometrią GeoJSON.
- Grupy ostrzeżeń są adresami rozgłoszeniowymi. APRSBox nie wysyła ACK.

## Payload CAWF v1

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]{MESSAGE_ID
```

Przykład:

```text
012300z,TSTORM2,@3569,1/2,0609,1206,1409{A6474
```

Zgodny payload CAWF v1 ma stałą kolejność pól, protokolarne tokeny zapisane wielkimi znakami ASCII z wyjątkiem dosłownego małego `z`, nie zawiera spacji i ma najwyżej 67 znaków łącznie z identyfikatorem wiadomości APRS.

## Pola

- `EXPIRY` ma postać `DDHHMMz`: dzień, godzina i minuta UTC. APRSBox ustala miesiąc i rok jako najbliższe prawidłowe wystąpienie względem odbioru. Niemożliwa lub uszkodzona wartość nie wygaśnie automatycznie.
- `EVENT_LEVEL` łączy kod zdarzenia i końcowy jednocyfrowy poziom, na przykład `TSTORM2`.
- `ALERT_ID` to `@` i cztery wielkie znaki szesnastkowe. Wszystkie fragmenty jednego logicznego alarmu używają tej samej wartości. Kluczem odbiornika jest callsign źródła, grupa ostrzeżeń i ID alarmu; wartość nie jest globalnie unikatowa.
- `PART/TOTAL` zaczyna się od `1/1`. Numery części są unikatowe, `PART` nie może być większe niż `TOTAL`, a każdy fragment powinien podawać tę samą liczbę wszystkich części.
- `AREA` zawiera 1–8 wielkich liter, cyfr lub myślników. Zera wiodące są istotne, a kod musi dokładnie odpowiadać identyfikatorowi w geometrii profilu.
- `MESSAGE_ID` to pięć wielkich znaków szesnastkowych po `{`. Identyfikuje pojedynczy fragment, a nie cały alarm. Dokładna retransmisja powinna zachować ID, zaś zmieniony fragment otrzymać nowe. Nawias zamykający nie występuje.

Dla interoperacyjności APRSBox przyjmuje nieco szerszy alfanumeryczny identyfikator wiadomości APRS, lecz wydawcy powinni używać ścisłej postaci CAWF v1.

## Poziomy i rejestr zdarzeń

CAWF v1 definiuje aktywne poziomy:

```text
1 = żółty
2 = pomarańczowy
3 = czerwony
```

Poziom `0` oznacza brak aktywnego ostrzeżenia i nie wolno go wysyłać jako aktywnego CAWF. Poziom `4` jest zarezerwowany. Profil kraju musi opisać mapowanie źródła autorytatywnego na poziomy 1–3.

Początkowy rejestr zdarzeń CAWF:

```text
TSTORM WIND RAIN FLOOD FFLOOD SNOW ICE HEAT COLD FOG
COASTAL AVALANC FIRE DUST OTHER
```

APRSBox zachowuje dokładny kod zdarzenia, a znane prefiksy wykorzystuje do wyboru kategorii i ikony. Kody bez osobnej kategorii pozostają widoczne jako `Inne / nieznane` i podlegają progom tej kategorii.

## Składanie fragmentów i duplikaty

- Fragmenty mogą przyjść w dowolnej kolejności. APRSBox grupuje je według callsignu źródła, grupy docelowej i `ALERT_ID`.
- Wpis na liście Alarmy zawiera sumę unikatowych odebranych kodów obszarów oraz liczbę części odebranych i zadeklarowanych.
- Stan zmienia się na `kompletny` po odebraniu wszystkich części od 1 do `TOTAL`; wcześniej alarm jest `niekompletny`.
- Powtórzony fragment z tym samym identyfikatorem APRS zostaje powiązany z istniejącym alarmem i zliczony bez utworzenia drugiego logicznego wpisu.
- Draft CAWF zaleca porzucenie niekompletnego składania po 15 minutach. APRSBox obecnie zachowuje niekompletny wpis do zwykłego wygaśnięcia lub usunięcia przez operatora, dlatego należy sprawdzać jego stan kompletności.

## Cykl życia

- Pierwszy fragment aktywuje lub tworzy logiczny alarm, jeśli pozwala na to próg kolumny Alarmy.
- Kolejne fragmenty i dokładne powtórzenia aktualizują ten sam wpis oraz zachowują odnośniki do ramek Monitora ruchu.
- Ponowne użycie tego samego `ALERT_ID` aktualizuje wpis w zakresie tego samego źródła i grupy. Wydawca powinien unikać ponownego użycia przez co najmniej 48 godzin po wygaśnięciu.
- W chwili `EXPIRY` APRSBox dezaktywuje alarm, lecz zachowuje ramki i historię.
- CAWF v1 nie definiuje standardowego jawnego odwołania. Nie wolno zakładać, że adres anulowania lub własny token odwoła istniejący alarm APRSBox.

## Profile krajowe i geometria mapy

Profil powinien publikować operatora grupy, autorytatywne źródło danych, callsigny wydawców, mapowania zdarzeń i poziomów, znaczenie kodów obszarów, wersję geometrii, politykę ważności i powtórzeń oraz kanał kontaktu.

Dla grupy pasującej do `CC-WARN` APRSBox szuka lokalnego GeoJSON w katalogu odpowiadającym dwuliterowemu kodowi kraju. Geometria musi być `Polygon` albo `MultiPolygon` w WGS84, a jej identyfikator dokładnie odpowiadać przesłanemu `AREA`. `PL-WARN` ma dedykowany zbiór polskich powiatów.

Nieznany kod pozostaje w alarmie, ale jest pomijany na mapie. Jeżeli kilka aktywnych alarmów dotyczy tej samej geometrii, o kolorze decyduje najwyższy znany poziom, a mapa pokazuje wszystkie powiązane alarmy.

## Zaufanie i bezpieczeństwo operacyjne

CAWF v1 nie zapewnia uwierzytelniania kryptograficznego. Draft zaleca listę zaufanych callsignów dla każdej grupy oraz publiczne opisanie operatora HUB i źródła. APRSBox obecnie nie wymusza takiej listy, więc dowolny nadawca może zaadresować skonfigurowaną grupę.

APRS należy traktować jako dodatkowy kanał świadomości sytuacyjnej. Ostrzeżenia o dużym wpływie trzeba potwierdzać w instytucji autorytatywnej, szczególnie gdy nadawca jest nieoczekiwany, alarm niekompletny, czas wygaśnięcia błędny albo obszar nie ma geometrii. Odbiór przez APRS-IS dowodzi tylko transportu, nie autentyczności.

## Źródła

- Dostarczone pliki `CAWF.md` i `CAWF-PL.md`, draft CAWF v1.
- [TAPR APRS Protocol Reference — reguły biuletynów NWS i wiadomości](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- [Dokumentacja usługi alertów NWS CAP](https://www.weather.gov/documentation/services-web-alerts), wykorzystana do rozróżnienia pełnego ostrzeżenia autorytatywnego od zwartego transportu APRS.

[Wróć do ustawień alarmów APRS](settings_alarms.pl.md)
