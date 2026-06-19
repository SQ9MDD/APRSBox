# Biuletyny i ogłoszenia

Ten dokument opisuje podstawowe użycie zakładki `Bulletins / Announcements` w APRSBox.

Ekran służy do przygotowania ramek APRS w formacie wiadomości, używanych do publikowania biuletynów i ogłoszeń.

## Zastosowanie

Biuletyny i ogłoszenia przydają się do przekazywania krótkich informacji tekstowych, takich jak:

- informacje klubowe i operatorskie,
- krótkie komunikaty organizacyjne,
- zapowiedzi wydarzeń,
- lokalne komunikaty techniczne lub pogodowe.

## Podstawowe pola

- `Type` wybiera rodzaj wpisu, na przykład biuletyn ogólny, biuletyn grupowy albo ogłoszenie. Od tego pola zależy sposób zbudowania adresata APRS oraz to, które pola pomocnicze mają znaczenie.
- `Code` służy do oznaczania biuletynu lub ogłoszenia pojedynczym znakiem. Dla biuletynów zwykle używa się cyfr `0-9`, a dla ogłoszeń liter `A-Z`, dzięki czemu odbiorca łatwiej rozpoznaje typ komunikatu.
- `Group` pozwala przypisać wpis do krótkiej grupy, używanej głównie przy biuletynach grupowych. To pole powinno pozostać krótkie, czytelne i stabilne, bo staje się częścią identyfikatora widocznego po stronie odbiorcy.
- `Message` zawiera właściwą treść komunikatu wysyłanego do sieci APRS. Najlepiej wpisywać tu krótki, jednoznaczny tekst, który da się wygodnie odczytać na radiu lub prostym kliencie APRS bez przewijania i bez domyślania się kontekstu.
- `Path` określa ścieżkę APRS, jeśli ma być użyta przy emisji radiowej. Dla prostych lokalnych komunikatów najbezpieczniej zostawić to pole puste, a jeśli w danym regionie stosowana jest konkretna praktyka, warto trzymać się lokalnych zasad.
- `Send interval` określa co ile minut wpis może być ponownie wysyłany, a `Activation` ustala kiedy wpis jest aktywny. W praktyce te pola działają razem: jedno odpowiada za odstęp między emisjami, a drugie za okno czasowe, w którym wysyłka jest w ogóle dozwolona.

## Krótkie zasady praktyczne

- Dla biuletynów ogólnych i grupowych używaj kodów `0-9`.
- Dla ogłoszeń używaj kodów `A-Z`.
- Pole grupy powinno być krótkie i czytelne.
- Treść wiadomości powinna być zwięzła i konkretna.
- Tekst powinien mieścić się w limicie 67 znaków i używać drukowalnego ASCII.
- Dla prostych, lokalnych emisji najbezpieczniej pozostawić pustą ścieżkę albo użyć tylko tego, co wynika z lokalnej praktyki.

## Uwagi

Biuletyny APRS nie są miejscem na długie opisy. Lepiej wysyłać krótkie, jednoznaczne komunikaty niż rozbudowany tekst trudny do odczytania na radiu lub prostym kliencie APRS.
