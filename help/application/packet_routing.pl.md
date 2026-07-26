# Reguły routingu pakietów

Ten ekran pokazuje listę reguł, które sterują przepływem pakietów APRS w APRSBox.

Na tym poziomie ustawiasz przede wszystkim:

- jakie reguły istnieją,
- w jakiej kolejności są wykonywane,
- które reguły są aktywne,
- do której reguły chcesz wejść, aby ją edytować.

## Po co używa się tej zakładki

Zakładka `Packet Routing` służy do zarządzania logiką ruchu pomiędzy wejściami i wyjściami APRSBox.

Najczęstsze zastosowania:

- przekazywanie pakietów z `Odbiornik RF` do `TX APRS-IS`,
- budowa reguł digipeatera `Odbiornik RF -> TX RF`,
- kierowanie ruchu lokalnie generowanego `Local TX -> TX APRS-IS`,
- ścieżki diagnostyczne kończące się na `Black Hole`,
- rozdzielenie kilku źródeł RF na różne scenariusze routingu.

## Jak czytać listę reguł

Każdy wiersz pokazuje:

- kolejność reguły,
- nazwę i opis,
- źródło wejściowe,
- cel końcowy,
- stan aktywności.

Kolejność na liście ma znaczenie organizacyjne i operacyjne, dlatego warto utrzymywać reguły w czytelnym układzie.

## Typowe scenariusze

### `Odbiornik RF -> TX APRS-IS`

Używane wtedy, gdy lokalnie odebrany ruch z eteru ma trafić do APRS-IS.

### `Odbiornik RF -> TX RF`

Używane wtedy, gdy APRSBox ma pełnić rolę digi i powtarzać ruch dalej w RF.

### `Local TX -> TX APRS-IS`

Używane wtedy, gdy obiekty, statusy, pogoda, biuletyny albo inne ramki tworzone przez APRSBox mają być wysyłane do APRS-IS.

### `Odbiornik RF -> Black Hole`

Używane do testów i obserwacji ruchu bez dalszego nadawania.

## Gdzie jest dokładny opis

Szczegółowy opis bloków, filtrów, pól konfiguracyjnych i gotowych schematów reguł znajduje się w pomocy ekranu `Packet Flow`:

[Szczegółowy opis Packet Flow](packet_routing_flow.pl.md)
