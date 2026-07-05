# Reguła ścieżki i ochrona DIGI

To najważniejszy blok dla ścieżek `... -> TX RF`. Ten krok robi dwie rzeczy naraz: najpierw wykonuje ochronę DIGI, a dopiero potem obsługuje pierwszy jeszcze niezużyty element ścieżki. Ten blok powinien być zawsze ostatnim blokiem we flow, bo modyfikuje ścieżkę i może zakłócić działanie innych filtrów.

Najpierw część ochronna odrzuca:

- ramki third-party,
- wiadomości APRS do lokalnej `My station`,
- query APRS do lokalnej `My station`,
- wiadomości APRS do lokalnej stacji `WX`,
- query APRS do lokalnej stacji `WX`,
- pakiety, w których lokalny znak jest już w path jako hop zużyty, na przykład `MYCALL-SSID*`.

Dopiero potem analizowany jest path:

- jeżeli ścieżka jest pusta, pakiet odpada,
- jeżeli wszystkie hop-y są już zużyte, pakiet odpada,
- sprawdzany jest tylko pierwszy element bez `*`,
- dalsze elementy nie są analizowane, dopóki pierwszy nie zostanie obsłużony.

Pola konfiguracyjne:

- `Paths (TRACE / traced)`:
  Jeśli pierwszy niezużyty hop pasuje do tej listy, APRSBox zużywa go i wstawia własny znak z `My settings` jako hop powtórzony przez lokalne digi.
- `Paths (NO TRACE / not traced)`:
  Jeśli pierwszy niezużyty hop pasuje do tej listy, APRSBox redukuje ten hop w miejscu bez dopisywania lokalnego znaku digi.

Co dokładnie można wpisać:

- każdy wpis podajesz w osobnej linii,
- `TRACE`: pełny hop `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: pełny hop `SP1-1`, `SP2-1`, `SP2-2` albo własny `CALLSIGN-SSID`.
- wpis `WIDE2-2` pasuje tylko do `WIDE2-2`; nie obsługuje `WIDE2-1` ani `WIDE1-1`,
- wpis `SP2-2` pasuje tylko do `SP2-2`; nie obsługuje `SP2-1` ani `SP1-1`,
- każdą obsługiwaną ścieżkę wpisz osobno.

Przekształcenie ścieżki w praktyce:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `SP1-1` -> `SP1*`,
- NO TRACE `SP2-1` -> `SP2*`,
- NO TRACE `SP2-2` -> `SP2-1`,
- jeśli hop nie ma postaci `N-N`, NO TRACE po prostu dopisuje `*`.

Typowe wpisy startowe:

`TRACE`:

- `WIDE1-1` - tylko ścieżka `WIDE1-1`,
- `WIDE2-1` - tylko ścieżka `WIDE2-1`,
- `WIDE2-2` - tylko ścieżka `WIDE2-2`.

`NO TRACE`:

- `SP1-1` - tylko ścieżka `SP1-1`,
- `SP2-1` - tylko ścieżka `SP2-1`,
- `SP2-2` - tylko ścieżka `SP2-2`,
- `CALLSIGN-SSID` - własny jawny hop, który ma być redukowany bez TRACE.

Dlaczego własny znak warto dodać do `NO TRACE`:

- jeżeli chcesz zużywać pakiety kierowane bezpośrednio do Twojego znaku bez ponownego dopisywania go do ścieżki,
- jeżeli w lokalnej sieci używasz własnego znaku jako jawnego hopu bez śladu TRACE,
- jeżeli chcesz lokalnie redukować rodzinę typu `SP` bez wstawiania swojego znaku do path.

Najważniejsze uwagi:

- jeżeli TRACE zadziała, a lokalny znak nie jest skonfigurowany, pakiet zostanie odrzucony,
- jeżeli pierwszy niezużyty hop nie pasuje ani do TRACE, ani do NO TRACE, pakiet zostanie odrzucony,
- to właśnie ten blok pilnuje sensownego użycia ścieżki w eterze.

Typowy schemat:

```text
Odbiornik RF -> Filtr duplikatów -> Reguła ścieżki i ochrona DIGI -> TX RF
```

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
