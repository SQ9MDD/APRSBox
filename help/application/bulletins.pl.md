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

- `Type` wybiera rodzaj wpisu.
- `Code` służy do oznaczania biuletynu lub ogłoszenia.
- `Group` pozwala przypisać wpis do krótkiej grupy.
- `Message` zawiera właściwą treść komunikatu.
- `Path` określa ścieżkę APRS, jeśli ma być użyta.
- `Send interval` i `Activation` sterują częstotliwością oraz harmonogramem wysyłki.

## Krótkie zasady praktyczne

- Dla biuletynów ogólnych i grupowych używaj kodów `0-9`.
- Dla ogłoszeń używaj kodów `A-Z`.
- Pole grupy powinno być krótkie i czytelne.
- Treść wiadomości powinna być zwięzła i konkretna.
- Tekst powinien mieścić się w limicie 67 znaków i używać drukowalnego ASCII.
- Dla prostych, lokalnych emisji najbezpieczniej pozostawić pustą ścieżkę albo użyć tylko tego, co wynika z lokalnej praktyki.

## Uwagi

Biuletyny APRS nie są miejscem na długie opisy. Lepiej wysyłać krótkie, jednoznaczne komunikaty niż rozbudowany tekst trudny do odczytania na radiu lub prostym kliencie APRS.
