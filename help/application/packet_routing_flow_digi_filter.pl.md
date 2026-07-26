# Filtr DIGI

Ten filtr nie patrzy na cały path i nie sprawdza hop-ów jeszcze niezużytych. Analizuje wyłącznie listę hop-ów już oznaczonych `*`, po zdjęciu tej gwiazdki.

Jak działa naprawdę:

- z path `SR5BCD-2*,WIDE1-1` widzi tylko `SR5BCD-2`,
- z path `WIDE1-1` nie widzi nic, bo nie ma jeszcze żadnego zużytego hopu,
- wzorce są porównywane do zużytych hop-ów; wildcard `*` może być użyty w dowolnym miejscu,
- tryb `allow` przepuszcza pakiet tylko wtedy, gdy co najmniej jeden zużyty hop pasuje do listy,
- tryb `deny` odrzuca pakiet tylko wtedy, gdy co najmniej jeden zużyty hop pasuje do listy.

Konsekwencje praktyczne:

- pusta lista `allow` odrzuca wszystko,
- pusta lista `deny` przepuszcza wszystko,
- wpis `*` w `deny` blokuje wszystkie pakiety już kiedyś digipeatowane,
- wpis `*` w `deny` nie blokuje ramek direct, bo direct nie ma żadnego zużytego hopu do dopasowania.

Przykłady:

- path `SR5BCD-2*,WIDE1-1` + wzorzec `SR5BCD*` -> match,
- path `SR5ABC*,WIDE1-1` + `deny: *` -> drop,
- path `WIDE1-1` + `deny: *` -> pass.

Kiedy używać:

- gdy chcesz przepuszczać ruch tylko po wybranych digi,
- gdy chcesz wyciąć ruch, który przyszedł już przez określone stacje pośrednie.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
