# Local TX

To źródło dla ramek wygenerowanych lokalnie przez APRSBox.

Obejmuje między innymi:

- beacony,
- status,
- pogodę,
- obiekty,
- itemy,
- biuletyny,
- wiadomości.

Nie obejmuje:

- ramek odebranych z RF,
- ramek już digipeatowanych,
- zwykłego ruchu wejściowego z TNC.

W praktyce:

- to osobna ścieżka dla ruchu "wewnętrznego",
- `Local TX` może prowadzić tylko do `TX APRS-IS` albo `Black Hole`.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
