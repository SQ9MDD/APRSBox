# Packet Flow - szczegółowy opis reguły

Ten plik pomocy jest krótkim przewodnikiem po tym, do czego służy edytor `Packet Flow` i kiedy warto użyć typowych ścieżek. Szczegółowy opis każdego bloku znajdziesz niżej pod linkami.

## Co robi ten ekran

Reguła routingu opisuje, co APRSBox ma zrobić z pakietem po jego odebraniu albo wygenerowaniu lokalnie.

Każda reguła ma jedno źródło, zero lub więcej bloków pośrednich i jeden cel końcowy.

Pakiet zawsze idzie od góry do dołu. Gdy którykolwiek blok go odrzuci, kolejne kroki nie są już wykonywane.

## Po co używać Packet Flow

- `Odbiornik RF -> TX APRS-IS` - klasyczny uplink iGate z eteru do APRS-IS.
- `Odbiornik RF -> TX RF` - klasyczna ścieżka digipeatera pracującego w radiu.
- `Local TX -> TX APRS-IS` - wysyłka ramek generowanych lokalnie przez APRSBox, takich jak beacon, pogoda, obiekty, itemy, biuletyny i wiadomości.
- `Źródło APRS-IS -> Reguła bezpieczeństwa wejścia APRS-IS -> Reguła znaku i promienia APRS-IS -> Reguła bezpieczeństwa TX APRS-IS → RF -> TX RF` - bezpieczne przekazanie jawnie dopuszczonych ramek z sieci na fizyczny TNC.
- `... -> Black Hole` - diagnostyka, testy i budowa reguły bez dalszego nadawania.

## Jak budować regułę

1. Wybierz źródło.
2. Wybierz cel.
3. Dodaj tylko te bloki, które są potrzebne dla danej ścieżki.
4. Zapisz regułę i sprawdź log wykonania.

## Bloki źródłowe

- [Odbiornik RF](packet_routing_flow_receiver_rf.pl.md)
- [Local TX](packet_routing_flow_local_tx.pl.md)
- [Obowiązkowe reguły bezpieczeństwa APRS-IS → RF](packet_routing_flow_rf_guard.pl.md)

## Bloki filtrów i reguł

- [Reguła bezpieczeństwa uplinku APRS-IS](packet_routing_flow_strict_filter.pl.md)
- [Reguła dostarczania wiadomości APRS-IS](packet_routing_flow_aprsis_message_delivery_rule.pl.md)
- [Reguła znaku i promienia APRS-IS](packet_routing_flow_aprsis_callsign_radius_rule.pl.md)
- [Reguła ścieżki DIGI RF](packet_routing_flow_path_rule_and_digi_guard.pl.md)
- [Filtr opóźnienia duplikatów RF](packet_routing_flow_duplicate_filter.pl.md)
- [Filtr bezpośredniego odbioru RF](packet_routing_flow_direct_only.pl.md)
- [Filtr DIGI](packet_routing_flow_digi_filter.pl.md)
- [Filtr źródłowego znaku](packet_routing_flow_callsign_filter.pl.md)
- [Filtr typu pakietu APRS](packet_routing_flow_packet_type_filter.pl.md)
- [Filtr symbolu APRS](packet_routing_flow_icon_filter.pl.md)
- [Filtr stref pozycji](packet_routing_flow_distance_filter.pl.md)
- [Filtr tempa transmisji](packet_routing_flow_rate_limit_filter.pl.md)

## Bloki docelowe

- [TX RF](packet_routing_flow_tx_rf.pl.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.pl.md)
- [Black Hole](packet_routing_flow_black_hole.pl.md)

## Krótkie uwagi

- `TX APRS-IS` wymaga `Reguły bezpieczeństwa uplinku APRS-IS`.
- Transmisja RF → RF wymaga `Reguły ścieżki DIGI RF`.
- `Local TX` może kończyć się tylko na `TX APRS-IS` albo `Black Hole`.
- Flow `APRS-IS → RF` zawiera dokładnie cztery obowiązkowe reguły systemowe. Nie można dodać do niego opcjonalnych filtrów. Ruch skierowany do niedawno słyszanej lokalnej stacji RF może dopuścić reguła dostarczania wiadomości; pozostały ruch wymaga znaku **i** promienia, a pusta konfiguracja nie przepuszcza innych ramek.
