# Biuletyny i ogłoszenia APRS

Ten ekran służy do przygotowania krótkich komunikatów rozgłoszeniowych APRS w formacie wiadomości. Biuletyny i ogłoszenia nie są prywatnymi wiadomościami do jednej stacji. 
Są przeznaczone dla wielu odbiorców, na przykład dla lokalnych operatorów, uczestników wydarzenia, grupy klubowej albo stacji znajdujących się w zasięgu radiowym.

## 1. Teoria

### Czym jest biuletyn APRS

Biuletyn APRS to krótka informacja tekstowa wysyłana do wielu odbiorców. Może zawierać komunikat klubowy, organizacyjny, techniczny, pogodowy albo informację przydatną podczas lokalnej aktywności radiowej.

Biuletyn nie jest rozmową tekstową i nie powinien zastępować długiego opisu, strony WWW ani prywatnej wiadomości do konkretnej osoby. Jego zadaniem jest szybkie przekazanie informacji, która ma znaczenie tu i teraz.

Dobre zastosowania biuletynów:

- informacja o lokalnej sieci lub spotkaniu,
- komunikat dla uczestników wydarzenia,
- informacja klubowa,
- krótka zapowiedź pracy przemiennika, digi, iGate albo stacji terenowej,
- lokalny komunikat techniczny,
- krótka informacja pogodowa lub organizacyjna.

Przykłady dobrych komunikatów:

```text
NET 19:00 local repeater SR5XXX
HAMFEST parking on 145.550
WX alert: strong wind until 18 UTC
APRS test 12:00-14:00 local area
```

### Czym jest ogłoszenie APRS

Ogłoszenie jest podobne do biuletynu, ale zwykle ma charakter bardziej informacyjny lub zapowiadający. W praktyce może służyć do publikowania krótkich zapowiedzi aktywności, wydarzeń lub ważnych lokalnych informacji.

Dla użytkownika najważniejsza różnica jest prosta:

```text
biuletyn      krótka informacja rozgłoszeniowa, zwykle numerowana cyfrą
ogłoszenie    krótka informacja oznaczana literą
```

### Biuletyn a zwykła wiadomość APRS

Zwykła wiadomość APRS jest kierowana do konkretnego znaku stacji. Biuletyn lub ogłoszenie jest kierowane do specjalnego adresata typu `BLN`, dlatego może zostać rozpoznane przez klientów APRS jako komunikat rozgłoszeniowy.

Biuletyn:

- nie jest prywatną wiadomością,
- nie jest typowym czatem,
- nie powinien wymagać odpowiedzi od konkretnej stacji,
- powinien być krótki i zrozumiały bez dodatkowego kontekstu.

## 2. Zgodność z protokołem APRS

Biuletyny i ogłoszenia są wysyłane jako ramki APRS w formacie wiadomości. Różnią się od zwykłej wiadomości tym, że pole adresata zawiera specjalny identyfikator zaczynający się od `BLN`.

Typowe identyfikatory:

```text
BLN0       biuletyn ogólny numer 0
BLN1       biuletyn ogólny numer 1
BLNA       ogłoszenie oznaczone literą A
BLN0GRP    biuletyn grupowy, przykład z krótką grupą GRP
```

Pole adresata APRS ma ograniczoną długość, dlatego kod i nazwa grupy muszą być krótkie. Nie warto tworzyć długich ani niestandardowych identyfikatorów, 
bo starsze radia i proste klienty APRS mogą ich nie pokazać w oczekiwany sposób.

Dla zgodności i czytelności najlepiej stosować:

```text
0-9    dla biuletynów ogólnych i grupowych
A-Z    dla ogłoszeń
```

Treść komunikatu powinna mieścić się w limicie krótkiej wiadomości APRS. Bezpieczną praktyką jest trzymanie się maksymalnie 67 znaków tekstu i używanie drukowalnego ASCII. 
Warto unikać narodowych znaków, symboli specjalnych i formatowania, ponieważ część radii i starszych klientów APRS może ich nie wyświetlić poprawnie.

## 3. Zasady dobrego użycia

APRS został zaprojektowany jako system bieżącej informacji operatorskiej. Dobry biuletyn powinien odpowiadać na pytanie: czy ta informacja jest przydatna dla stacji, które odbiorą ją teraz i tutaj?

Najlepsze praktyki:

- pisz krótko i konkretnie,
- przekazuj informacje przydatne lokalnie lub operacyjnie,
- używaj prostego języka,
- unikaj długich opisów,
- unikaj zbyt częstego powtarzania,
- nie używaj biuletynów jako reklamy bez znaczenia dla lokalnych operatorów,
- nie wysyłaj treści, które lepiej umieścić na stronie WWW, w mailu albo komunikatorze.

Dobry biuletyn APRS to krótka informacja o bieżącej wartości dla lokalnych operatorów, a nie tekst wysyłany do sieci tylko dlatego, że technicznie da się go nadać.

### Interwał wysyłki

Interwał powinien być dobrany rozsądnie. Biuletyn ma przypominać o ważnej informacji, ale nie powinien stale zajmować kanału radiowego.

Dla lokalnych emisji RF unikaj bardzo krótkich odstępów. Jeżeli komunikat nie jest pilny, lepiej wysyłać go rzadziej. 
Przy wydarzeniach i aktywnościach terenowych dobrym podejściem jest ustawienie okna aktywności i umiarkowanego interwału powtórzeń.

### Ścieżka APRS

Dla prostych lokalnych emisji najbezpieczniej zostawić ścieżkę pustą albo użyć ustawień zgodnych z lokalną praktyką. 
Zbyt szeroka ścieżka może niepotrzebnie obciążać kanał radiowy i rozprowadzać lokalny komunikat dalej, niż jest to potrzebne.

Jeżeli komunikat ma trafić tylko do APRS-IS, ścieżka radiowa zwykle nie ma znaczenia.

### Grupy

Grupa ma sens wtedy, gdy komunikat jest przeznaczony dla konkretnego środowiska, wydarzenia, klubu albo lokalnej aktywności. Nazwa grupy powinna być krótka, stabilna i łatwa do rozpoznania.

Dobre nazwy grup:

```text
CLUB
FIELD
ARES
EVENT
SP5
```

Specyfikacja APRS opisuje, że adres biuletynu grupowego składa się z `BLN`, jednocyfrowego identyfikatora biuletynu i nazwy grupy o długości do 5 znaków, uzupełnianej spacjami do 5 znaków.

## 4. Obsługa formularza

### Typ

Pole `Typ` wybiera rodzaj wpisu.

Typowe możliwości:

```text
Biuletyn ogólny
Biuletyn grupowy
Ogłoszenie
```

Od wybranego typu zależy sposób zbudowania adresata APRS i znaczenie pól pomocniczych.

### Kod

Pole `Kod` oznacza biuletyn lub ogłoszenie pojedynczym znakiem.

Zalecane użycie:

```text
0-9    dla biuletynów
A-Z    dla ogłoszeń
```

Przykłady:

```text
0    pierwszy biuletyn
1    drugi biuletyn
A    ogłoszenie A
B    ogłoszenie B
```

Nie zmieniaj kodu bez potrzeby, jeżeli komunikat jest kontynuacją tej samej informacji. Stabilny kod ułatwia odbiorcom rozpoznanie, że widzą aktualizację tego samego biuletynu lub ogłoszenia.

### Grupa

Pole `Grupa` jest używane głównie przy biuletynach grupowych. Pozwala ograniczyć znaczenie komunikatu do konkretnej grupy odbiorców lub konkretnej aktywności.

Grupa powinna być:

- krótka,
- czytelna,
- stabilna,
- zapisana prostymi znakami ASCII.

Przykład:

```text
EVENT
CLUB
SP5
```

### Treść wiadomości

Pole `Treść wiadomości` zawiera właściwy komunikat APRS.

Najlepsza treść jest krótka, jednoznaczna i zrozumiała bez dodatkowego kontekstu. Pamiętaj, że komunikat może być czytany na małym ekranie radia, a nie tylko w wygodnej aplikacji na komputerze.

Zalecenia:

- maksymalnie 67 znaków,
- drukowalne ASCII,
- bez polskich znaków,
- bez długich zdań,
- bez formatowania,
- bez niepotrzebnych ozdobników.

Dobry przykład:

```text
NET 19:00 SR5XXX, check-ins welcome
```

Słabszy przykład:

```text
Dzisiejsze spotkanie naszej grupy odbedzie sie wieczorem, szczegoly na stronie internetowej, prosimy wszystkich o zapoznanie sie z informacjami.
```

### Ścieżka

Pole `Ścieżka` określa ścieżkę APRS używaną przy emisji radiowej.

Dla prostych lokalnych komunikatów najlepiej pozostawić je puste albo użyć tylko takiej ścieżki, jaka jest przyjęta lokalnie. 
Nie ustawiaj szerokiej ścieżki tylko po to, żeby komunikat dotarł jak najdalej. Biuletyn powinien trafiać tam, gdzie ma wartość dla odbiorców.

### Interwał wysyłki

Pole `Interwał wysyłki` określa, co ile minut komunikat może być ponownie wysłany, gdy jest aktywny.

To pole nie decyduje samo o tym, kiedy komunikat wolno nadawać. Interwał działa razem z trybem aktywacji i harmonogramem.

Przykład:

```text
Interwał wysyłki: 30 minut
Aktywne od: 10:00 UTC
Aktywne do: 14:00 UTC
```

Oznacza to, że komunikat może być wysyłany co 30 minut tylko w oknie od 10:00 do 14:00 UTC.

### Tryb aktywacji

Pole `Tryb aktywacji` określa, kiedy wpis jest aktywny.

Typowe tryby:

```text
Ręczny       wpis jest włączany i wyłączany ręcznie
Zaplanowany  wpis ma jedno określone okno aktywności
Cykliczny    wpis wraca regularnie według powtarzalnego planu
```

### Aktywne od

Pole `Aktywne od` określa moment rozpoczęcia aktywności wpisu w czasie UTC.

W trybie zaplanowanym jest to początek jednego okna emisji. W trybie cyklicznym jest to pierwszy start całego cyklu.

### Aktywne do

Pole `Aktywne do` określa moment zakończenia aktywności wpisu w czasie UTC.

W trybie zaplanowanym jest to koniec jednego okna emisji. W trybie ręcznym może służyć jako dodatkowe ograniczenie ważności wpisu.

### Aktywne przez

Pole `Aktywne przez` określa, jak długo pojedynczy cykl pozostaje aktywny w trybie cyklicznym.

Przykład:

```text
Aktywne przez: 3 godziny
Powtarzaj co: 7 dni
```

Oznacza to, że po każdym starcie cyklu komunikat będzie aktywny przez 3 godziny.

### Powtarzaj co

Pole `Powtarzaj co` określa odstęp między kolejnymi startami cyklu.

Przykład:

```text
Powtarzaj co: 1
Jednostka powtórzenia: tydzień
```

Oznacza cykl powtarzany raz na tydzień.

### Jednostka powtórzenia

Pole `Jednostka powtórzenia` określa jednostkę używaną przez `Powtarzaj co`.

Typowe jednostki:

```text
dni
tygodnie
miesiące
lata
```

W przypadku miesięcy i lat pamiętaj, że są to jednostki kalendarzowe. Nie każdy miesiąc ma tę samą liczbę dni.

## 5. Przykłady użycia

### Biuletyn ogólny

Użycie: krótka informacja dla wszystkich odbiorców.

```text
Typ: Biuletyn ogólny
Kod: 0
Treść wiadomości: NET 19:00 SR5XXX, check-ins welcome
Interwał wysyłki: 30 minut
```

Przykładowy sens komunikatu:

```text
Lokalna sieć rozpoczyna się o 19:00 na przemienniku SR5XXX.
```

### Biuletyn grupowy

Użycie: komunikat dla konkretnej grupy, wydarzenia albo aktywności.

```text
Typ: Biuletyn grupowy
Kod: 1
Grupa: EVENT
Treść wiadomości: EVENT parking on 145.550 simplex
Interwał wysyłki: 20 minut
```

Przykładowy sens komunikatu:

```text
Uczestnicy wydarzenia znajdą informację o kanale parkingowym.
```

### Ogłoszenie

Użycie: krótka zapowiedź lub informacja organizacyjna.

```text
Typ: Ogłoszenie
Kod: A
Treść wiadomości: HAMFEST gates open 08:00 UTC
Interwał wysyłki: 60 minut
```

Przykładowy sens komunikatu:

```text
Ogłoszenie informuje o godzinie otwarcia wydarzenia.
```

## 6. Na co uważać

Unikaj:

- bardzo długich komunikatów,
- polskich znaków i znaków specjalnych,
- zbyt częstego powtarzania,
- szerokiej ścieżki bez wyraźnej potrzeby,
- komunikatów niezwiązanych z lokalną sytuacją operatorską,
- treści, które powinny być zwykłą wiadomością do konkretnej stacji,
- treści, które powinny trafić na stronę WWW, do maila albo komunikatora.

Pamiętaj, że kanał APRS na radiu ma ograniczoną przepustowość. Każdy nadawany biuletyn powinien mieć sens dla odbiorców.

## 7. Krótka ściąga

```text
Biuletyn APRS     krótki komunikat rozgłoszeniowy
Ogłoszenie APRS   krótka zapowiedź lub informacja
BLN               specjalny adres używany dla biuletynów i ogłoszeń
0-9               zalecane kody biuletynów
A-Z               zalecane kody ogłoszeń
Grupa             krótki identyfikator odbiorców lub aktywności
67 znaków         bezpieczny limit treści wiadomości
ASCII             najbezpieczniejszy zestaw znaków
Interwał          jak często powtarzać aktywny komunikat
Aktywacja         kiedy komunikat może być nadawany
```

## 8. Najważniejsza zasada

Biuletyn APRS powinien być krótki, lokalnie użyteczny i łatwy do odczytania na prostym sprzęcie. 
Jeśli komunikat wymaga długiego wyjaśnienia, wielu zdań albo linkowania do dodatkowych informacji, prawdopodobnie nie nadaje się jako biuletyn APRS.
