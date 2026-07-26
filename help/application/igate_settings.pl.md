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

## Identyfikacja jednokierunkowego i dwukierunkowego iGate

Oba tryby używają zweryfikowanego logowania APRS-IS. `pass -1` oznacza niezweryfikowanego klienta APRS-IS tylko do odbioru i nie pozwala wysyłać odebranych ramek RF.

APRSBox identyfikuje możliwość powrotu na RF osobno dla każdej bramkowanej stacji:

- `qAO` jest używane, gdy odbierający interfejs TNC nie może nadawać, ma zablokowany TX albo nie ma aktywnego flow powrotu wiadomości `APRS-IS → RF`.
- `qAR` jest używane, gdy odbierający interfejs TNC jest aktywny, ma dozwolony TX i aktywny flow `APRS-IS → RF` zapewnia ścieżkę powrotu wiadomości.
- Ramki wygenerowane lokalnie przez APRSBox używają `TCPIP*`; są to pakiety klienta, a nie pakiety bramkowane z RF.

Wyłączenie flow `APRS-IS → RF` powoduje użycie `qAO` w kolejnych uplinkach RF.

## Diagnostyka

Panel stanu pokazuje aktualne połączenie, login, aktywne reguły APRSIS, ostatni błąd oraz liczniki ramek wysłanych i odrzuconych przed TX do APRS-IS.

Cel `TX APRS-IS` używa systemowego filtra bezpieczeństwa. Filtr odrzuca między innymi ramki z tokenami `TCPIP` / `TCPXX`, ramki z `NOGATE` / `RFONLY` oraz niepoprawną enkapsulację third-party.
