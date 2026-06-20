# Biuletyny i ogłoszenia

Ekran służy do przygotowania ramek APRS w formacie wiadomości, używanych do publikowania biuletynów i ogłoszeń.

## Zastosowanie

Biuletyny i ogłoszenia przydają się do przekazywania krótkich informacji tekstowych, takich jak:

- informacje klubowe i operatorskie,
- krótkie komunikaty organizacyjne,
- zapowiedzi wydarzeń,
- lokalne komunikaty techniczne lub pogodowe.

## Podstawowe pola

- `Typ` wybiera rodzaj wpisu, na przykład `Biuletyn ogólny`, `Biuletyn grupowy` albo `Ogłoszenie`. Od tego pola zależy sposób zbudowania adresata APRS oraz to, które pola pomocnicze mają znaczenie.
- `Kod` służy do oznaczania biuletynu lub ogłoszenia pojedynczym znakiem. Dla biuletynów zwykle używa się cyfr `0-9`, a dla ogłoszeń liter `A-Z`, dzięki czemu odbiorca łatwiej rozpoznaje typ komunikatu.
- `Grupa` pozwala przypisać wpis do krótkiej grupy, używanej głównie przy biuletynach grupowych. To pole powinno pozostać krótkie, czytelne i stabilne, bo staje się częścią identyfikatora widocznego po stronie odbiorcy.
- `Treść wiadomości` zawiera właściwą treść komunikatu wysyłanego do sieci APRS. Najlepiej wpisywać tu krótki, jednoznaczny tekst, który da się wygodnie odczytać na radiu lub prostym kliencie APRS bez przewijania i bez domyślania się kontekstu.
- `Ścieżka` określa ścieżkę APRS, jeśli ma być użyta przy emisji radiowej. Dla prostych lokalnych komunikatów najbezpieczniej zostawić to pole puste, a jeśli w danym regionie stosowana jest konkretna praktyka, warto trzymać się lokalnych zasad.
- `Interwał wysyłki` określa co ile minut wpis może być ponownie wysyłany. To ustawienie nie mówi jeszcze kiedy wpis wolno nadawać, tylko jaki ma być odstęp między kolejnymi emisjami, jeśli wpis jest aktualnie aktywny.
- `Tryb aktywacji` wybiera tryb aktywacji wpisu. `Ręczny` oznacza ręczne włączenie bez harmonogramu, `Zaplanowany` pozwala zdefiniować jedno ciągłe okno czasowe, a `Cykliczny` służy do cyklicznego włączania wpisu według powtarzalnego planu.
- `Aktywne od` określa moment rozpoczęcia aktywności wpisu w czasie UTC. W trybie `Zaplanowany` jest to początek jednego zadanego okna aktywności, a w trybie `Cykliczny` jest to pierwszy moment startu całego cyklu.
- `Aktywne do` określa moment zakończenia aktywności wpisu w czasie UTC. W trybie `Zaplanowany` zwykle wyznacza koniec jednego przedziału emisji, a w trybie ręcznym może być użyte jako dodatkowe ograniczenie ważności wpisu.
- `Aktywne przez (godziny)` określa jak długo pojedynczy cykl ma pozostawać aktywny w trybie `Cykliczny`. Innymi słowy, pole to definiuje długość jednego okna nadawania po każdym uruchomieniu cyklu.
- `Powtarzaj co` określa co jaki interwał cykl ma się powtarzać w trybie `Cykliczny`. Razem z polem jednostki definiuje odstęp pomiędzy kolejnymi startami aktywnego okna.
- `Jednostka powtórzenia` określa jednostkę używaną przez `Powtarzaj co`, na przykład dni, tygodnie, miesiące albo lata. To pole decyduje, czy powtarzanie ma być liczone w prostych odstępach dobowych, tygodniowych czy w dłuższych krokach kalendarzowych.

## Krótkie zasady praktyczne

- Dla biuletynów ogólnych i grupowych używaj kodów `0-9`.
- Dla ogłoszeń używaj kodów `A-Z`.
- Pole grupy powinno być krótkie i czytelne.
- Treść wiadomości powinna być zwięzła i konkretna.
- Tekst powinien mieścić się w limicie 67 znaków i używać drukowalnego ASCII.
- Dla prostych, lokalnych emisji najbezpieczniej pozostawić pustą ścieżkę albo użyć tylko tego, co wynika z lokalnej praktyki.
- Przy harmonogramach warto pamiętać, że `Interwał wysyłki` i `Tryb aktywacji` działają wspólnie: harmonogram określa kiedy wolno nadawać, a interwał określa jak często wpis ma być wysyłany w dozwolonym oknie.

## Uwagi

Biuletyny APRS nie są miejscem na długie opisy. Lepiej wysyłać krótkie, jednoznaczne komunikaty niż rozbudowany tekst trudny do odczytania na radiu lub prostym kliencie APRS.
