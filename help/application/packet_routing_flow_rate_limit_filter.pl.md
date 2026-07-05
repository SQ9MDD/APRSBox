# Filtr limitu tempa

Ten filtr nie liczy "pakietów na minutę". To prosty limiter czasu od ostatnio przepuszczonej ramki dla znaku źródłowego.

Format reguły:

```text
CALL_OR_PATTERN - LIMIT
```

Przykłady:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

Jak działa:

- filtr działa wyłącznie na źródłowym callsignie pakietu,
- pierwsza pasująca ramka zawsze przechodzi,
- kolejna ramka od tego samego źródła i dla tego samego dopasowanego wzorca zostanie zablokowana, jeśli przyjdzie przed upływem limitu,
- licznik aktualizuje się tylko po ramce przepuszczonej,
- jeśli żadna reguła nie pasuje do źródła, filtr nic nie blokuje i przepuszcza pakiet dalej.

Jak dopasowywane są wzorce:

- `SQ9MDD-7` bez wildcardu pasuje tylko do dokładnie tego SSID,
- `SQ9MDD` bez wildcardu, ale też bez SSID, pasuje do tego callsignu z dowolnym SSID,
- `SQ*` działa jako wildcard,
- gdy pasuje kilka reguł naraz, runtime wybiera najbardziej szczegółową; przy remisie wygrywa wcześniejsza linia.

Ograniczenia formatu:

- `LIMIT` można zapisać jako `30`, `30s` albo `30S`,
- dozwolony zakres to od 5 do 300 sekund,
- krok wynosi 5 sekund.

Kiedy używać:

- gdy bardzo aktywne stacje generują zbyt dużo ruchu,
- gdy chcesz ochronić ścieżkę RF bez całkowitego blokowania źródła.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
