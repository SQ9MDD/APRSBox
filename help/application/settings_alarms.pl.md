# Ustawienia alarmów APRS

Ten panel steruje odbiorem alarmów, przenoszeniem ich na listę Alarmy, popupami emergency oraz automatycznym filtrem APRS-IS dla grup alarmowych.

## Główny przełącznik i grupy

- `Włącz alarmy APRS` włącza albo wyłącza przetwarzanie alarmów.
- `Grupy alarmowe` przyjmują jedną lub więcej nazw grup APRS rozdzielonych przecinkami.
- Zapisane grupy alarmowe są dodawane do efektywnych grup odbioru wiadomości RF i do automatycznego filtra grup APRS-IS.

Podsumowanie pod formularzem pokazuje efektywne grupy RF oraz dokładny filtr automatyczny wynikający z zapisanej konfiguracji.

## Progi według typu zdarzenia

Każda kategoria zdarzenia ma dwa niezależne progi:

- `Alarmy` sterują przeniesieniem z Wiadomości na listę Alarmy.
- `Popup alarmu` steruje popupem w stylu emergency.
- Wartość liczbowa przyjmuje ten poziom i wszystkie poziomy wyższe.
- `Wył.` wyłącza kategorię w danej kolumnie.

Nieznane poziomy ważności są zachowywane ze względów bezpieczeństwa zamiast cichego odrzucenia.

Widocznością alarmów na mapie zarządza się bezpośrednio z panelu alarmów na stronie Mapa. Te ustawienia nie zastępują przełącznika mapy.
