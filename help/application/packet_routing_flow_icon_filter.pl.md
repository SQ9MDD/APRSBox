# Filtr symbolu APRS

Ten filtr działa na symbolu APRS zapisanym dokładnie w postaci `table+code`.

Jak działa:

- dopasowanie jest dokładne, bez wildcardów,
- filtr porównuje dokładnie taki symbol, jaki zwrócił parser APRSBox,
- w trybie `allow` brak dopasowania oznacza odrzucenie,
- w trybie `deny` brak dopasowania oznacza przepuszczenie,
- jeśli symbolu nie da się zdekodować, `allow` odrzuca, a `deny` przepuszcza.

Przykłady wpisów:

- `/>`,
- `\\l`.

Kiedy używać:

- gdy chcesz osobno obsłużyć określone klasy obiektów albo stacji,
- gdy symbol ma być ważniejszy niż sam typ pakietu.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
