# Reguła dostarczania wiadomości APRS-IS

Ta obowiązkowa reguła systemowa realizuje standardową ścieżkę wiadomości dwukierunkowego iGate w restrykcyjnym flow `APRS-IS → RF`. Jest wykonywana po kontroli bezpieczeństwa wejścia, a przed Regułą znaku i promienia.

## Co może przekazać

Reguła może zatwierdzić:

- wiadomości, potwierdzenia (`ack`) i odrzucenia (`rej`) skierowane do jednego dokładnego lokalnego znaku z SSID,
- zapytania skierowane do jednego dokładnego lokalnego znaku z SSID,
- następny pakiet pozycji nadawcy, którego wiadomość została skutecznie zakolejkowana na RF.

Bulletiny, wiadomości grupowe, definicje telemetryczne i zapytania ogólne nie są obowiązkowym ruchem wiadomościowym.

## Sprawdzanie lokalnego adresata

Adresat musi być niedawno słyszany przez jedno ze skonfigurowanych lokalnych źródeł RF. Dopasowanie obejmuje SSID: `SQ9MDD` i `SQ9MDD-1` są różnymi stacjami.

Reguła odrzuca wiadomość, gdy adresat nie był słyszany w ustawionym czasie, został odebrany przez zbyt wiele wykorzystanych hopów DIGI, był ostatnio widziany jako stacja pochodząca z Internetu albo nadawca wiadomości był ostatnio słyszany w tym samym lokalnym zasięgu RF.

## Konfiguracja

- **Lokalne źródła nasłuchu RF**: jedna nazwa interfejsu w każdym wierszu. Pusta lista używa docelowego interfejsu RF.
- **Ważność lokalnego nasłuchu**: od 5 do 60 minut; domyślnie 60.
- **Maksymalna liczba wykorzystanych hopów DIGI**: od 0 do 2; domyślne 0 oznacza wyłącznie odbiór bezpośredni.

Użyj najmniejszego zasięgu, który niezawodnie dociera do zamierzonych stacji lokalnych.

## Współpraca z pozostałymi regułami

Zatwierdzona wiadomość omija `Regułę znaku i promienia APRS-IS`, ale nadal przechodzi przez końcową regułę bezpieczeństwa TX, kontrolę duplikatów, limity transmisji, enkapsulację third-party i kontrolę długości AX.25.

[Reguła znaku i promienia APRS-IS](packet_routing_flow_aprsis_callsign_radius_rule.pl.md)

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
