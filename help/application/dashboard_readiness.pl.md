# Gotowość stacji

Ten kafelek jest prostą checklistą pierwszego uruchomienia. Pokazuje, czego jeszcze brakuje w konfiguracji, ale nie sprawdza jakości anteny, zasięgu radiowego ani tego, czy inne stacje odbierają Twoje ramki.

## Zanim zaczniesz — trzy pojęcia

- **RF** oznacza ruch radiowy odbierany lub nadawany przez TNC.
- **APRS-IS** to internetowa sieć APRS.
- **Flow** to reguła routingu „skąd → dokąd”, na przykład `Receiver RF → TX APRS-IS`.

Wykonuj kroki po kolei. Interfejsy tworzą źródła i cele, których później użyjesz w `Mojej stacji` oraz w `Packet Routing`.

## Zalecana kolejność konfiguracji

### 1. Interfejsy

Najpierw otwórz `Interfejsy` i dodaj:

- co najmniej jeden aktywny interfejs radiowy `TCP` albo `SERIALL`; `OpenWebRX MQTT` jest tylko odbiorczy,
- interfejs `APRS-IS (RX/TX)`, jeżeli stacja ma odbierać z APRS-IS lub wysyłać do niego ramki.

Sprawdź, czy interfejsy są włączone, fizyczny TNC nie ma niezamierzonej blokady TX, a połączenie APRS-IS osiąga stan połączony.

**Po tym kroku:** pozycje `Interfejsy radiowe` i `Połączenie APRS-IS` powinny być zielone. Gdy włączona jest tylko część skonfigurowanych interfejsów radiowych, ich stan jest ciemnożółty. Brak aktywnego interfejsu radiowego daje stan czerwony.

[Pomoc: Interfejsy](tnc.pl.md)

### 2. Moja stacja

Następnie skonfiguruj `Moja stacja`:

- znak i SSID,
- współrzędne oraz symbol APRS,
- komentarz, interwał i ścieżkę beaconu,
- cel TX: konkretny interfejs radiowy, wszystkie aktywne interfejsy albo `Internal TX`,
- włącz automatyczny beacon, jeżeli ma być nadawany cyklicznie.

`Internal TX` tworzy ramkę wewnątrz APRSBox, ale nie wysyła jej do fizycznego TNC. Wybierz ten cel, gdy dalszą drogę ramki ma określić wyłącznie routing. Wybranie interfejsu radiowego lub wszystkich aktywnych interfejsów powoduje nadanie beacona przez RF.

**Po tym kroku:** pozycja `Beacon zdefiniowany` powinna być zielona. Samo zdefiniowanie beacona nie oznacza jeszcze, że trafi on do APRS-IS — za to odpowiada flow z kroku 3.

[Pomoc: Moja stacja](station.pl.md)

### 3. Packet Routing

Na końcu otwórz `Packet Routing` i dodaj aktywne flow odpowiadające roli stacji.

Do pełnego zielonego stanu kafelek sprawdza:

- `Local TX → TX APRS-IS` — własne beacony, statusy, pogodę, obiekty, itemy, biuletyny i wiadomości wysyłane bezpośrednio do APRS-IS,
- `Receiver RF → TX APRS-IS` dla każdego aktywnego wejścia RF — klasyczny uplink iGate,
- `APRS-IS → TX RF` dla każdego aktywnego interfejsu z TX — bezpieczny powrót kwalifikujących się wiadomości z APRS-IS do RF,
- `Receiver RF → TX RF` pomiędzy wymaganymi aktywnymi interfejsami — funkcję digi albo cross-band zgodnie z konfiguracją stacji.

[Pomoc: Packet Routing](packet_routing.pl.md)

**Po tym kroku:** `Local TX → APRS-IS` oraz potrzebne pola w wierszach aktywnych interfejsów powinny być zielone. Odszukaj brakujący kierunek na kafelku i porównaj go z powyższą listą.

## Własne ramki a APRS-IS

Ramka nadana przez własny interfejs RF nie trafia automatycznie bezpośrednio do APRS-IS. Może pojawić się w sieci, jeżeli odbierze ją radiowy iGate — własny lub zewnętrzny — ale zależy to od zasięgu RF, filtrów i działania tej bramki.

Jeżeli własne ramki mają trafiać do APRS-IS niezależnie od radiowego iGate, utwórz aktywny flow `Local TX → TX APRS-IS`. Dotyczy to zarówno ramki skierowanej na `Internal TX`, jak i własnej ramki nadawanej równocześnie przez interfejs RF.

To osobna droga od `Receiver RF → TX APRS-IS`: `Local TX` obsługuje ramki utworzone przez APRSBox, a `Receiver RF` ramki rzeczywiście odebrane z radia. Nie twórz flow z wyjścia radiowego — źródłem własnych ramek w routingu zawsze jest `Local TX`.

## Jak czytać kolory

- zielony — wymagany element jest aktywny lub flow istnieje,
- ciemnożółty — konfiguracja jest częściowa albo brakuje flow,
- czerwony — brak aktywnego interfejsu lub błąd połączenia,
- szary — interfejs jest wyłączony albo dany kierunek go nie dotyczy.

Jeżeli świadomie nie chcesz pełnić jednej z ról, na przykład digi albo bramki `APRS-IS → RF`, odpowiadające pole może pozostać ostrzeżeniem. Nie oznacza to awarii — pokazuje różnicę względem pełnej macierzy gotowości.
