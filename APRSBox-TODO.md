# APRSBox TODO

Lista rozjazdów między obecną implementacją APRSBox a kopiami specyfikacji APRS z repo, z priorytetami poprawek i rozwoju.

## P1

### 1. Query APRS są ACK-owane mimo wymagań specyfikacji
- Status: rozjazd funkcjonalny
- Priorytet: P1
- Problem:
  - Kod wysyła `ack-now` i `ack-delayed` dla zapytań APRS.
  - W bundlowanej specyfikacji query są transmisjami jednorazowymi i nie powinny być ACK-owane.
- Obszary kodu:
  - `app/services/messages.py`
- Zakres poprawki:
  - wyłączyć ACK dla `?APRS`, `?APRSP`, `?APRSS`, `?APRSD`, `?DX`, `?APRSV`, `?VER`
  - przejrzeć testy wiadomości i query
- Ryzyko:
  - zmiana obecnego zachowania testów i UX rozmów APRS

### 2. Numery wiadomości i `reply-ack` są tylko częściowo zgodne
- Status: rozjazd protokołowy
- Priorytet: P1
- Problem:
  - implementacja używa krótkich numerów 1-2 znaki
  - brak pełnej obsługi formatu `reply-ack` `{MM}AA`
  - parser odbiera część składni, ale generator outbound jej nie emituje
- Obszary kodu:
  - `app/services/messages.py`
  - `app/services/outbound.py`
- Zakres poprawki:
  - rozszerzyć line number do zgodnego zakresu używanego przez spec i/lub świadomie ustalić ograniczenie kompatybilności
  - dodać pełny mechanizm `reply-ack` dla dialogu APRS
  - dopasować retry i deduplikację do nowego formatu
- Ryzyko:
  - dotyka logiki ACK, retry, parsera i interoperacyjności z innymi klientami

### 3. `Items` nie są domknięte end-to-end
- Status: brak funkcji
- Priorytet: P1
- Problem:
  - formularze i walidacja istnieją, ale transmisja itemów nie jest wdrożona
  - parser itemów wyciąga tylko nazwę i komentarz, bez pełnej pozycji
- Obszary kodu:
  - `app/sections.py`
  - `app/services/content.py`
  - brak odpowiednika buildera/schedulera/runtime dla itemów
- Zakres poprawki:
  - dodać builder ramki item
  - dodać scheduler/runtime TX dla itemów
  - rozszerzyć parser itemów o pozycję, symbol i stan
- Ryzyko:
  - nowa ścieżka TX, zmiany w UI i testach

## P2

### 4. Telemetria APRS jest głównie czyszczona z komentarza, nie dekodowana
- Status: częściowa implementacja
- Priorytet: P2
- Problem:
  - kod usuwa `|...|` i `!DAO!` z komentarzy
  - brak właściwego dekodowania base91 comment telemetry
  - telemetry packets `T#...`, `PARM.`, `UNIT.`, `EQNS.`, `BITS.` nie są rozwijane do struktury danych
- Obszary kodu:
  - `app/services/content.py`
- Zakres poprawki:
  - dodać dekoder base91 telemetry
  - dodać dekoder definicji telemetrii
  - zachować surowe dane i dane zdekodowane równolegle
- Ryzyko:
  - umiarkowane, głównie parser i prezentacja

### 5. Timestampy APRS nie są zachowywane jako dane protokołowe
- Status: częściowa implementacja
- Priorytet: P2
- Problem:
  - pozycje timestamped są parsowane bez zachowania samego timestampa
  - status nie obsługuje wariantu z timestampem
  - aplikacja opiera się głównie na czasie odbioru z bazy
- Obszary kodu:
  - `app/services/content.py`
- Zakres poprawki:
  - przechowywać timestamp APRS osobno od czasu odbioru
  - rozróżnić `received_at` i `aprs_timestamp`
  - rozszerzyć parser status i innych ramek timestamped
- Ryzyko:
  - zmiany modelu danych wyświetlania i analityki

### 6. Third-party frames nie odtwarzają w pełni logicznej ścieżki
- Status: częściowa implementacja
- Priorytet: P2
- Problem:
  - aplikacja rozpakowuje inner frame
  - nie dokleja stacji przenoszącej jako pseudo-digi do logic path zgodnie z opisem w specyfikacji
- Obszary kodu:
  - `app/services/content.py`
  - `app/services/messages.py`
- Zakres poprawki:
  - odtworzyć logiczny path zgodny z opisem third-party
  - utrzymać jednocześnie outer path i reconstructed path
- Ryzyko:
  - wpływ na routing, diagnostykę i prezentację ścieżek

### 7. Zestaw wspieranych APRS query jest wąski
- Status: brak części funkcji
- Priorytet: P2
- Problem:
  - wspierane są tylko podstawowe zapytania lokalne
  - brak m.in. `?APRSM`, `?APRSO`, `?APRSH`, `?WX?` i wariantów ogólnych/radius
- Obszary kodu:
  - `app/services/messages.py`
- Zakres poprawki:
  - dodać kolejne typy query
  - zdefiniować, które odpowiedzi APRSBox ma umieć generować lokalnie
- Ryzyko:
  - niskie do umiarkowanego

## P3

### 8. Obsługa tekstu jest ograniczona do printable ASCII
- Status: świadome ograniczenie
- Priorytet: P3
- Problem:
  - wiadomości, biuletyny, obiekty i itemy blokują UTF-8
  - repo zawiera notatkę dopuszczającą UTF-8 w części zastosowań APRS
- Obszary kodu:
  - `app/services/content.py`
- Zakres poprawki:
  - zdecydować, czy APRSBox pozostaje ASCII-only, czy dopuszcza UTF-8 w wybranych polach
  - jeśli tak, wdrożyć to osobno dla messages/status/free text
- Ryzyko:
  - interoperacyjność z radiami i starszym oprogramowaniem

### 9. Brak części klasycznych formatów APRS
- Status: brak funkcji
- Priorytet: P3
- Problem:
  - brak parsera dla surowych NMEA (`$GPRMC`, `$GPGGA`, `$GPGLL`)
  - brak pełniejszej obsługi DF/`DFS`, `RNG`, grid square i podobnych starszych formatów
- Obszary kodu:
  - `app/services/content.py`
- Zakres poprawki:
  - zdecydować, które formaty są realnie potrzebne w APRSBox
  - wdrażać tylko te, które mają sens dla bieżącego scope aplikacji
- Ryzyko:
  - łatwo rozszerzyć parser ponad potrzebny zakres

### 10. TOCALL `APBOX0` wymaga decyzji kompatybilnościowej
- Status: do potwierdzenia
- Priorytet: P3
- Problem:
  - aplikacja generuje destination `APBOX0`
  - w repo jest tabela TOCALL-i APRS, ale nie sprawdzałem formalnej rejestracji tego identyfikatora dla APRSBox
- Obszary kodu:
  - `app/services/outbound.py`
- Zakres poprawki:
  - potwierdzić, czy `APBOX0` jest zamierzone i bezpieczne
  - w razie potrzeby zmienić na zarejestrowany/politycznie poprawny TOCALL
- Ryzyko:
  - umiarkowane, głównie interoperacyjność i identyfikacja klienta

## Proponowana kolejność prac

1. Wyłączyć ACK dla query.
2. Uporządkować numerację wiadomości i pełne `reply-ack`.
3. Domknąć `items` po stronie parser/TX/runtime.
4. Dodać właściwe dekodowanie telemetrii i zachowanie timestampów APRS.
5. Rozszerzyć query i ewentualnie third-party path reconstruction.
6. Na końcu rozważyć UTF-8, dodatkowe starsze formaty i decyzję o TOCALL.
