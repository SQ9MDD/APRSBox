# Filtr typu pakietu APRS

Ten filtr działa na tym, co parser APRSBox zdekoduje jako typ lub grupę pakietu APRS.

Najczęściej używane selektory:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Znaczenie praktyczne:

- `message` obejmuje także ACK/REJ, bulletin i announcement,
- `weather` dotyczy tylko ramek weather-only,
- pozycja z danymi pogody nadal liczy się jako `position`,
- dla zgodności wstecznej działają też stare kody typu, na przykład `M`, `S`, `O`, `W`, oraz inne surowe kody zwracane przez parser.

Jak działa:

- w trybie `allow` pakiet przechodzi tylko wtedy, gdy zdekodowany typ lub grupa pasuje do listy,
- w trybie `deny` pakiet odpada tylko wtedy, gdy pasuje do listy,
- jeśli parser nie potrafi określić grupy/typu, `allow` odrzuca, a `deny` przepuszcza.

Kiedy używać:

- gdy chcesz osobno traktować wiadomości, obiekty, pozycje albo pogodę,
- gdy jedna ścieżka ma dotyczyć tylko jednego rodzaju ruchu.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
