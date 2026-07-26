# Filtr bezpośredniego odbioru RF

Ten filtr przepuszcza tylko pakiety usłyszane bezpośrednio.

Jak działa naprawdę:

- sprawdza wyłącznie, czy w path istnieje jakikolwiek już zużyty hop oznaczony `*`,
- nie interesują go hop-y jeszcze niezużyte, na przykład `WIDE1-1`,
- pakiet `...,WIDE1-1:` przejdzie,
- pakiet `...,SR5ABC*,WIDE1-1:` zostanie odrzucony.

Kiedy używać:

- gdy chcesz reagować tylko na stacje słyszane lokalnie,
- gdy nie chcesz dalej obrabiać ramek już powtórzonych przez inne digi,
- gdy budujesz testy typu "co słyszę bezpośrednio".

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
