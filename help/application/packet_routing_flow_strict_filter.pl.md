# Filtr ścisły

To systemowy filtr bezpieczeństwa dla ścieżek kończących się na `TX APRS-IS`.

Jak działa dla ramek z `Odbiornik RF`:

- sprawdza całą zewnętrzną ścieżkę,
- odrzuca pakiet, jeśli gdziekolwiek w path występuje `TCPIP`, `TCPXX`, `NOGATE` albo `RFONLY`,
- jeśli ramka jest third-party, najpierw sprawdza poprawność enkapsulacji,
- dla poprawnej third-party sprawdza także ścieżkę wewnętrzną i tam również blokuje `TCPIP`, `TCPXX`, `NOGATE` oraz `RFONLY`.

Jak działa dla `Local TX`:

- wymaga, aby ramka była oznaczona w metadanych jako ruch lokalnie wygenerowany przez APRSBox,
- odrzuca każdą ramkę third-party,
- odrzuca ramkę, jeśli w path znajduje się konstrukcja `q..`, na przykład `qAO`,
- nadal blokuje `TCPIP`, `TCPXX`, `NOGATE` i `RFONLY`.

Najważniejsze uwagi:

- przy `TX APRS-IS` ten filtr jest obowiązkowy,
- to nie jest filtr do sterowania digipeaterem RF,
- jeśli parser TNC2 nie rozpozna ramki, filtr ją odrzuca.

Typowe use case'y:

- `Odbiornik RF -> Filtr ścisły -> TX APRS-IS`,
- `Local TX -> Filtr ścisły -> TX APRS-IS`.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
