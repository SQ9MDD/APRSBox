# Filtr źródłowego znaku

Ten filtr sprawdza wyłącznie znak źródłowy nadawcy pakietu. Nie analizuje ścieżki, hop-ów digi ani celu pakietu.

Jak działa:

- bez wildcard `*` dopasowanie jest dokładne,
- `SQ9MDD` nie pasuje do `SQ9MDD-4`,
- wildcard `*` może być użyty w dowolnym miejscu,
- `allow` działa jak whitelist,
- `deny` działa jak blacklist.

Konsekwencje praktyczne:

- pusta lista `allow` odrzuca wszystko,
- pusta lista `deny` przepuszcza wszystko.

Przykłady:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Kiedy używać:

- do rozdzielenia ruchu klubowego, testowego albo technicznego,
- do blokowania znanych źródeł zakłócających ruch.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
