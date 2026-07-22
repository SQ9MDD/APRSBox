# Interfejsy

Zakładka Interfejsy konfiguruje wejścia APRSBox. Interfejsy radiowe mogą odbierać KISS/TNC2, wysyłać ramki outbound i opcjonalnie udostępniać port KISS w LAN. APRS-IS można włączyć jako interfejs tylko do odbioru.

## Lista interfejsów

Tabela pokazuje skonfigurowane interfejsy. Wiersz można kliknąć, żeby przejść do edycji.

- `Status` pokazuje stan konfiguracji i runtime, na przykład połączenie, błąd albo wyłączony interfejs.
- `TX Block` pokazuje, czy nadawanie przez dany interfejs jest zablokowane.
- `LAN` pokazuje, czy APRSBox wystawia proxy KISS/TNC dla klientów LAN.

Wyłączenie interfejsu zatrzymuje jego odbiór. Wyłączenie interfejsu radiowego zatrzymuje także użycie go do wysyłki. Konfiguracje beaconu, WX, obiektów, biuletynów i wiadomości mogą nadal wskazywać taki interfejs radiowy, ale wysyłka zostanie pominięta albo zakończy się błędem zależnie od kontekstu.

## Typy interfejsu

- `TCP` łączy się z TNC lub programem wystawiającym KISS przez TCP. `Ścieżka / adres / filtr` ma zwykle format `host:port`, na przykład `127.0.0.1:8001`.
- `SERIALL` używa lokalnego portu szeregowego, na przykład `/dev/ttyUSB0` albo `/dev/ttyACM0`, i wymaga poprawnego `Baud Rate`.
- `OpenWebRX MQTT (RX only)` odbiera pakiety z MQTT OpenWebRX. Ten typ jest tylko odbiorczy: TX jest blokowany, a proxy LAN jest wyłączane.
- `APRSIS` odbiera linie TNC2 przez istniejące połączenie APRS-IS skonfigurowane w ustawieniach iGate. Nie używa KISS i w tym interfejsie służy tylko do odbioru. Może istnieć tylko jeden interfejs APRSIS.

Dla OpenWebRX MQTT pole adresu powinno być URL-em `mqtt://` albo `mqtts://` z tematem w ścieżce, na przykład `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

Dla APRSIS pole `Ścieżka / adres / filtr` jest filtrem serwera APRS-IS. Nowy interfejs otrzymuje domyślnie `m/20`; można wpisać inny poprawny filtr, na przykład `r/52.23/21.01/50`. Serwer, port, callsign i passcode nadal pochodzą z ustawień iGate.

## Pola konfiguracji

- `Name` to nazwa widoczna w logach, listach interfejsów i wyborach TX.
- `Band` opisuje pasmo interfejsu.
- `Enabled` włącza interfejs w runtime APRSBox.
- `Block TX on this interface` pozwala odbierać ruch, ale blokuje nadawanie outbound.
- `TX Min Gap (s)` ustawia minimalną przerwę między transmisjami na tym TNC. Dozwolony zakres to `0.2` do `1.2` sekundy.
- `RX Silence Reconnect Timeout (s)` dotyczy seriala. Po ciszy RX dłuższej od ustawionej wartości broker serial może wymusić reconnect. `0` wyłącza ten watchdog.

`Baud Rate` jest używany tylko dla `SERIALL`. Dla APRSIS pola seriala, TX i proxy LAN są ukryte.

## Expose Port

`Expose Port` wystawia połączenie TNC przez APRSBox jako port TCP dla klientów w sieci LAN. APRSBox przekazuje ramki między fizycznym TNC a klientami.

- `Allow TX from remote clients` pozwala klientom LAN wysyłać ramki do TNC. Gdy jest wyłączone, klienci mogą tylko odbierać.
- `Bind Address` określa adres nasłuchu. `0.0.0.0` oznacza wszystkie interfejsy sieciowe.
- `Port` to port TCP wystawiany przez APRSBox. Maksymalnie obsługiwane są 3 jednoczesne połączenia.
- `Whitelist` ogranicza dostęp do adresów IPv4 albo sieci CIDR. Wpisuj po jednym wpisie w linii; przecinki też są akceptowane.

Nie włączaj zdalnego TX w niezaufanej sieci. Jeżeli wystawiasz port poza lokalną maszynę, ustaw whitelist.

## Kiedy używać kilku interfejsów

Kilka aktywnych interfejsów może działać równolegle. Ruch jest odbierany osobno per interfejs, a transmisja radiowa zależy od wyboru w danej zakładce, na przykład `My Station`, `WX`, obiektach, biuletynach, wiadomościach albo regułach `Packet Routing`. Ruch odebrany z APRS-IS jest widoczny w historii, szczegółach stacji i na mapie, ale jest wykluczony ze wszystkich statystyk APRSBox.

Jeżeli potrzebujesz tylko wejścia z OpenWebRX, użyj `OpenWebRX MQTT (RX only)`. Jeżeli potrzebujesz pełnego RX/TX przez radio, użyj `TCP` albo `SERIALL`.
