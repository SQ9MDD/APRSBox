# Ustawienia iGate

Ten ekran konfiguruje połączenie APRSBox z APRS-IS oraz pokazuje stan pracy uplinku. Nie jest osobnym włącznikiem iGate. Ruch do APRS-IS jest uruchamiany przez aktywne reguły `Packet Routing`, które kończą się celem `TX APRS-IS`.

## Kiedy tego używać

- `Odbiornik RF -> TX APRS-IS` tworzy klasyczny uplink iGate z radia do APRS-IS.
- `Local TX -> TX APRS-IS` wysyła do APRS-IS ramki wygenerowane lokalnie przez APRSBox, na przykład beacon, status, pogodę, obiekty, itemy, biuletyny i wiadomości.

Szczegółowy opis budowania tych ścieżek znajduje się w pomocy:

[Packet Routing](packet_routing.pl.md)

## Pola konfiguracji

- `Server` to host APRS-IS. Domyślnie używany jest `rotate.aprs2.net`.
- `Port` to port serwera APRS-IS. Typowa wartość to `14580`.
- `Login callsign / callsign-SSID` może zostać puste. Wtedy aplikacja używa znaku ze stacji lokalnej.
- `Passcode` może zostać puste. Wtedy aplikacja wylicza standardowy passcode APRS-IS dla znaku logowania.

Passcode APRS-IS nie jest hasłem do konta. To standardowy kod wyliczany ze znaku wywoławczego, wymagany przez serwery APRS-IS do wysyłania ramek.

## Diagnostyka

Panel stanu pokazuje aktualne połączenie, login, aktywne reguły APRSIS, ostatni błąd oraz liczniki ramek wysłanych i odrzuconych przed TX do APRS-IS.

Cel `TX APRS-IS` używa systemowego filtra bezpieczeństwa. Filtr odrzuca między innymi ramki z tokenami `TCPIP` / `TCPXX`, ramki z `NOGATE` / `RFONLY` oraz niepoprawną enkapsulację third-party.
