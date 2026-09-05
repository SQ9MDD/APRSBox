# Wykresy aktywności i obciążenie kanału APRS RF

Ten blok zawiera dwa wykresy dla tego samego zakresu czasu, bucketów i zoomu. Górny pokazuje liczbę zdarzeń ruchu APRS. Dolny pokazuje szacowane obciążenie kanału APRS RF. Zakres wybierasz w prawym górnym rogu bloku; przeciągnięcie po wykresie przybliża wybrany fragment, a podwójne kliknięcie przywraca pełny zakres.

## Górny wykres: aktywność APRS

Górny wykres pokazuje liczbę zdarzeń w każdym przedziale:

- **RX** — ramki odebrane przez APRSBox,
- **TX** — lokalnie zapisane transmisje RF,
- **repeats** — transmisje oznaczone jako digipeat,
- **APRS-IS uplink** — ramki wysłane z APRSBox do APRS-IS.

To liczba ramek, więc nie opisuje bezpośrednio zajętości kanału: krótkie i długie ramki mają tę samą wartość. APRS-IS uplink jest ruchem internetowym i nie zajmuje kanału RF.

## Dolny wykres: obciążenie kanału RF

Dolny wykres pokazuje szacowane obciążenie kanału APRS RF na podstawie ramek poprawnie odebranych i zdekodowanych przez APRSBox oraz transmisji RF zapisanych przez APRSBox. Jest to narzędzie diagnostyczne dla obserwowanego ruchu APRS, a nie pomiar rzeczywistego zajęcia medium radiowego.

Każdy punkt jest udziałem oszacowanego czasu nadawania RF w czasie całego przedziału. Na przykład suma `60 s` airtime w przedziale `5 min` daje obciążenie `20%`.

Wybierasz jeden interfejs RF. Interfejs i wszystkie jego porty KISS powinny odpowiadać jednemu fizycznemu kanałowi RF. Oddzielnych interfejsów APRSBox nie sumuje, ponieważ mogą pracować na różnych częstotliwościach lub obsługiwać ten sam ruch z różnych odbiorników.

Nowe dane pojawiają się po zamknięciu pełnego przedziału agregacji. Puste miejsce oznacza brak wystarczających danych do estymacji, a nie zerowe obciążenie kanału.

## Jak APRSBox liczy airtime

Dla każdej ramki RF APRSBox używa dostępnej długości surowej ramki AX.25, a nie długości tekstu TNC2 ani framingu KISS. Standardowo interfejsy KISS `SERIALL` i `TCP` używają stałej prędkości RF `1200 bit/s`; `Baud Rate` portu UART nie jest prędkością modemu radiowego i nie bierze udziału w obliczeniu.

Do długości AX.25 APRSBox dodaje fizyczne dwa bajty FCS oraz dwa znaczniki HDLC (flagi). Bit stuffing HDLC jest uwzględniony jako stałe, deterministyczne przybliżenie `63/62`, bez analizowania bitstreamu każdej ramki:

```
airtime_s = ((długość_AX.25 + 2) × 8 × 63/62 + 16) / 1200
```

KISS framing nie jest częścią transmisji RF i nie jest liczony. APRSBox nie zna zwykle TXDELAY, preambuły ani tailu obcych stacji, dlatego ich nie zgaduje i nie dodaje. Wykres pokazuje zatem oszacowany airtime ramki, a nie pełny czas zajęcia nośnej.

Obciążenie przedziału jest liczone jako:

```
obciążenie_% = suma_airtime_s / czas_przedziału_s × 100
```

Wartość powyżej `100%` pozostaje widoczna. Oznacza to, że suma zarejestrowanych zdarzeń transmisji przekracza długość przedziału; APRSBox jej nie maskuje ani nie ogranicza do `100%`.

APRS-IS nie zużywa airtime RF. Ramka odebrana z RF, a potem nadana przez digi, tworzy dwa rzeczywiste zdarzenia RF i oba są liczone osobno.

## Progi diagnostyczne

- poniżej `20%` — **normalne**,
- od `20%` do poniżej `40%` — **podwyższone**,
- `40%` i więcej — **przeciążony**.

Progi pomagają ocenić lokalnie obserwowany ruch. Nie są fizycznymi limitami kanału ani granicami wynikającymi z pomiaru DCD.

## Ograniczenia pomiaru

APRSBox widzi tylko ramki, które radio i TNC poprawnie odebrały oraz zdekodowały, a także lokalnie zapisane transmisje RF. Kolizje, zakłócenia, zajęta nośna bez poprawnej ramki AX.25 i transmisje niedekodowane przez TNC mogą pozostać niewidoczne. Bez telemetrii DCD wykres nie mierzy faktycznego fizycznego wykorzystania kanału.

Model jest przeznaczony do porównywania okresów ruchu i wykrywania rosnącego obciążenia obserwowanego kanału APRS.
