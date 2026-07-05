# Moja stacja

Ta zakładka konfiguruje główną stację APRSBox: znak, beacon pozycji, osobny APRS Status, symbol na mapie i ręczne wysyłanie ramek lokalnych.

## Position Beacon

Beacon pozycji to ramka APRS z lokalizacją stacji. Jest używany przez mapy, inne stacje i reguły `Local TX`.

- `Callsign` to główny znak stacji bez SSID.
- `SSID` wybiera końcówkę znaku, na przykład `SQ9XYZ-4`.
- `Interface` wskazuje TNC do nadawania, wszystkie aktywne interfejsy albo `Internal TX`.
- `Beacon Comment` trafia do ramki pozycji i ma krótki limit znaków ASCII.
- `Beacon at every` ustawia interwał automatycznego beaconu albo tryb `Proportional Path`.
- `Beacon Path` ustawia ścieżkę radiową, na przykład puste pole dla emisji lokalnej albo `WIDE2-1`.
- `Get location` ustawia współrzędne z mapy.
- `Symbol Table`, `Symbol Code` i `Overlay` wybierają symbol APRS widoczny na mapach.
- `Enable automatic beacon transmission every selected interval` włącza cykliczne nadawanie beaconu.

Przycisk `Send beacon` zapisuje aktualny formularz i od razu kolejkuje pojedynczą ramkę beaconu.

## Ścieżka i obciążenie kanału

APRSBox pokazuje ostrzeżenie, gdy wybrana ścieżka i interwał mogą nadmiernie obciążać kanał RF.

- Puste pole, `DIRECT` albo brak szerokiej ścieżki oznacza emisję lokalną.
- Ścieżka z jednym hopem powinna zwykle mieć dłuższy interwał.
- Ścieżka z dwoma hopami, na przykład `WIDE2-2`, wymaga szczególnej ostrożności.
- `Proportional Path` wysyła częstsze ramki lokalne i rzadsze ramki z pełną ścieżką, żeby zmniejszyć ruch na kanale.

Jeżeli aplikacja prosi o potwierdzenie zapisu, oznacza to, że ustawienie może znacząco zwiększyć ruch RF.

## PHG Generator

Ikona kalkulatora przy `Beacon Comment` tworzy kod `PHG` z mocy, wysokości anteny, zysku i kierunku anteny. Wygenerowany kod jest wstawiany na początku komentarza beaconu.

PHG jest przydatne głównie dla stacji stałych, przemienników, bramek i digipeaterów. Dla zwykłej stacji mobilnej zwykle nie jest potrzebne.

## APRS Status

`APRS Status` to osobna ramka z identyfikatorem danych `>`. Nie zastępuje komentarza beaconu pozycji.

- `Status Text` jest tekstem statusu i ma osobny limit długości.
- `APRS Status at every` ustawia interwał cyklicznego statusu.
- `Enable periodic APRS Status transmission` włącza automatyczną wysyłkę statusu.

Przycisk `Send status` zapisuje aktualny formularz i kolejkuje pojedynczą ramkę statusu. Jeżeli status jest włączony, tekst statusu nie może być pusty.

## Internal TX

`Internal TX` nie wysyła bezpośrednio przez fizyczny TNC. Ramki są generowane lokalnie i mogą być dalej obsłużone przez reguły `Packet Routing`, na przykład `Local TX -> TX APRS-IS`.

Jeżeli nie ma aktywnej reguły `Local TX -> TX APRS-IS`, Internal TX zachowuje się jak lokalny czarny otwór: ramka powstaje w APRSBox, ale nie wychodzi dalej.

## Station TX Log

Log pokazuje ostatnie zadania beaconu i statusu: czas, typ, status, interfejs, liczbę prób, błąd oraz podgląd ramki TNC2. Wiersz przekreślony oznacza, że zadanie zostało zapisane, ale transmisja została pominięta, na przykład z powodu wyłączonego albo zablokowanego TNC.
