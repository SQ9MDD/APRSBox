# APRS Queries

Opracowanie na podstawie dokumentu **"APRS Queries, Information Exchange & Groups"** compiled by SA7SKY, update 2018-06-30 1130z.

## Uwagi ogólne

- UI-View jest **case sensitive**.
- Dla wywołań z callsignem należy używać **SSID, jeśli istnieje**.
- Ten plik został przygotowany **wyłącznie na podstawie dostarczonego PDF**, bez użycia innych źródeł.

---

## 1. Standard APRS queries

| Input | To | Znaczenie / odpowiedź | Przykład |
|---|---|---|---|
| `?APRS?` | `callsign` | Prośba o listę wszystkich zapytań, na które dana stacja/system potrafi odpowiedzieć | `?APRS?` |
| `?WX?` | `CQ` | Zapytanie do wszystkich stacji pogodowych | `?WX?` |
| `!PROGRAMNAME.EXE` | `callsign` | UI-View może uruchomić program z katalogu RCOMMAND, np. `!Orbitron.exe` albo `!Orbitron` | `!help` |
| `?ABOUT` | `callsign` | Wersja oprogramowania stacji, system operacyjny, obciążenie CPU, równoważne z `?APRSV` i `?VER` | `?APRST APRSIS32 Win v6.1 b7601 p2 9.1/6.4%` |
| `?APRSD` | `callsign` | Stacje słyszane bezpośrednio, bez hopów digipeatera | `?APRSD` |
| `?APRSH` | `callsign` | Stacje słyszane wraz z typem ścieżki pakietu: `I`, `G`, `D`, `d`, `R` | `?APRSH` |
| `?APRSH DF8LS-9` | `callsign` | Czy stacja słyszała wskazany callsign, odpowiedź zawiera statystyki z ostatnich 18 godzin | `?APRSH DF8LS-9` |
| `?APRSL` | `callsign` | Stacje słyszane lokalnie w ostatnich 30 minutach, maksymalnie do 2 hopów | `?APRSL` |
| `?APRSM` | `callsign` | Message query, pyta czy stacja ma wiadomości dla mnie w kolejce | `?APRSM` |
| `?APRSO` | `callsign` | Object query, wysyła aktywne obiekty utworzone przez stację, z wyłączeniem obiektów QRU-server | `?APRSO` |
| `?APRSP` | `callsign` | Position query, zwykle powoduje wymuszenie beaconu po stronie odbiorcy | `?APRSP` |
| `?APRSS` | `callsign` | Status query, np. status portów APRSIS32 | `?APRSS` |
| `?APRST` | `callsign` | Ślad pakietów stacji do interfejsu internetowego APRS-IS lub przez radio, równoważne `?PING?` | `?APRST` |
| `?APRSV` | `callsign` | Wersja oprogramowania, system, CPU, równoważne `?ABOUT` i `?VER` | `?APRSV` |
| `?CPU` | `callsign` | Wersja oprogramowania, system, obciążenie jądra i użytkownika | `?CPU` |
| `?DX` | `callsign` | Raport DX w skróconej formie, najdalsza odebrana stacja z ostatniej godziny | `?DX` |
| `?IGATE` | `callsign` | Aktywność na portach IGATE, w APRSIS32 także informacja o pracy bi-directional | `?IGATE` |
| `?PING?` | `callsign` | To samo co `?APRST` | `?PING?` |
| `?VER` | `callsign` | To samo co `?ABOUT` i `?APRSV` | `?VER` |

### Znaczenie skrótów w `?APRSH`

- `I` - pakiety z internetu, także z samego APRS-IS
- `G` - pakiety stacji bramkowanych, callsign-SSID po konstrukcji `qAS`, `qAR` itd.
- `D` - pakiety stacji zdigipeatowane, których pierwsza kopia przyszła z internetu
- `d` - pakiety zdigipeatowane, słyszane lokalnie
- `R` - pakiety słyszane przez radio

---

## 2. Funkcje tylko dla UI-View

| Input | To | Znaczenie |
|---|---|---|
| `BCN` | `callsign` | Pozycja i comment text jako pakiet beacon |
| `LGS` lub `LG1` | `callsign` | Start logowania wszystkich odebranych stacji |
| `LGX` lub `LG0` | `callsign` | Zakończenie logowania odebranych stacji, komenda musi pochodzić od samej stacji |
| `QAS` | `callsign` | Wszystkie słyszane stacje |
| `QWS` | `callsign` | Słyszane stacje pogodowe |

---

## 3. ANSRVR i CQSRVR

### ANSRVR

| Input | To | Znaczenie |
|---|---|---|
| `?` | `ANSRVR` | Lista dostępnych grup zainteresowań, bez limitu czasu lub aktywności |
| `? GROUP NAME` | `ANSRVR` | Liczba członków danej grupy |
| `D GROUP NAME` | `ANSRVR` | Opis grupy i lista członków |
| `L` | `ANSRVR` | Grupy, do których należę |
| `J GROUP NAME` | `ANSRVR` | Dołącz do grupy, członkostwo ważne 12 godzin |
| `U GROUP NAME` | `ANSRVR` | Wypisz z grupy |
| `CQ GROUP NAME Text...` | `ANSRVR` | Jednoczesne dołączenie do grupy i wysłanie wiadomości do członków |

### Uwagi do `CQ GROUP NAME Text...`

- Jeśli grupa nie istnieje, nadawca staje się jej właścicielem.
- Przy inicjowaniu grupy nazwa może mieć maksymalnie **46 znaków**.
- Właściciel może usunąć grupę dopiero wtedy, gdy nie ma już członków.

### CQSRVR

| Input | To | Znaczenie |
|---|---|---|
| `INFO` | `CQSRVR` | Lista grup krótkoterminowych, członkostwo i grupa wygasają po 12 godzinach bez aktywności |

---

## 4. QRU-Server

### Zapytania ogólne

| Input | To | Znaczenie |
|---|---|---|
| `INFO` | `QRU` | Jakie grupy obiektów QRU są dostępne w moim promieniu geograficznym, domyślnie np. 50 km |
| `INFO 250` | `QRU` | To samo, ale dla promienia 250 km |
| `OBJECT GROUP NAME` | `QRU` | Jakie obiekty z danej grupy są dostępne w moim promieniu |
| `OBJECT GROUP NAME 150` | `QRU` | Jakie obiekty z danej grupy są dostępne w promieniu 150 km |

### Zachowanie odpowiedzi QRU

- Przy zapytaniu przez internet wszystkie obiekty są wypisywane.
- W APRSIS32 mogą się też otworzyć okna mapy z ich lokalizacją.
- Przy zapytaniu przez radio zwracana jest końcowa wiadomość typu `Sent 5 RP70 Objects Max 5@50km`.
- Obiekty są następnie wysyłane przez IGATE i mogą pojawić się na wyświetlaczu radiotelefonu, liście stacji albo w systemie nawigacyjnym.
- Dokument podaje, że obiekty nie pokazują się na aprs.fi, jeśli zapytanie wykonano przez internet, ale pokazują się, jeśli zapytanie wykonano przez radio.

### Grupy obiektów QRU

| Kod | Znaczenie |
|---|---|
| `AERO` | Aerodrome |
| `AIRP` | Airport |
| `AMBU` | Ambulance |
| `CLUB` | Amateur Radio Club |
| `CIVD` | Civil Defense |
| `ECHO` | EchoLink |
| `FIRE` | Fire Department |
| `FOOD` | Restaurant |
| `FUEL` | Gas Station |
| `HELI` | Rescue Helicopter |
| `HOSP` | Hospital |
| `INFO` | Info Kiosk Collection |
| `LIFEBOAT` | Lifeboat |
| `POLI` | Police |
| `POST` | Post Office |
| `RAIL` | Railway |
| `RD2M` | 2m D-Star Repeater |
| `RD70` | 70cm D-Star Repeater |
| `RP10` | 10m Repeater |
| `RP23` | 23cm Repeater |
| `RP2M` | 2m Repeater |
| `RP6M` | 6m Repeater |
| `RP70` | 70cm Repeater |
| `SHOP` | Shopping Center |
| `SRAIL` | Steam Railway |
| `STOR` | Amateur Radio Shop |
| `T2SRV` | T2 Server |
| `VETE` | Veterinarian |

---

## 5. AVRS, Automatic Voice Relay System

| Input | To | Znaczenie |
|---|---|---|
| `?` | `AVRS` | Gdzie od mojej pozycji znajduje się najbliższa stacja EchoLink, IRLP albo Allstar |
| `? CALLSIGN-SSID` | `AVRS` | Gdzie od pozycji wskazanej stacji znajduje się jej najbliższa stacja EchoLink, IRLP albo Allstar |
| `CALLSIGN-SSID` | `AVRS` | Prośba o zestawienie informacji potrzebnych do nawiązania kontaktu głosowego przez najbliższy węzeł EchoLink |

### Uwaga

Do poprawnego działania AVRS przynajmniej jeden beacon z pozycją musi wcześniej trafić do APRS-IS.

---

## 6. APRSlink, WLNK-1

APRSlink służy do zapytań dla użytkowników Winlink posiadających adres `callsign@winlink.org`.

| Input | To | Znaczenie |
|---|---|---|
| `H` | `WLNK-1` | Pomoc |
| `I` | `WLNK-1` | Informacje o APRSlink |
| `?L` | `WLNK-1` | Pomoc dla konkretnej komendy |
| `L` | `WLNK-1` | Lista dostępnych wiadomości, zwykle ostatnich 5 |
| `R<numer>` | `WLNK-1` | Odczyt konkretnej wiadomości |
| `Y<numer>` | `WLNK-1` | Odpowiedź na konkretną wiadomość |
| `K<numer>` | `WLNK-1` | Usunięcie konkretnej wiadomości |
| `F<numer>` | `WLNK-1` | Forward konkretnej wiadomości |
| `SP <email/callsign/alias> <subject>` | `WLNK-1` | Rozpoczęcie nadawania dłuższego maila w kilku krokach |
| `/EX` | `WLNK-1` | Zakończenie i wysłanie kompletnej wiadomości |
| `P` | `WLNK-1` | Playback wiadomości |
| `SMS ...` | `WLNK-1` | Wysłanie jednoliniowej wiadomości |
| `A ALIAS=mail@provider.net` | `WLNK-1` | Utworzenie lub aktualizacja aliasu |
| `A ALIAS=` | `WLNK-1` | Usunięcie aliasu |
| `AL` | `WLNK-1` | Lista aliasów |
| `G<number>` | `WLNK-1` | Zapytanie o najbliższe bramy RMS Packet, domyślnie 1 |

### Sekwencja `SP`

1. Rozpocznij: `SP <email lub callsign lub alias> <subject>`
2. Wysyłaj kolejne fragmenty tekstu
3. Zakończ osobną wiadomością `/EX`

Dokument zaznacza, że do czasu komendy kończącej tekst można wysyłać do `WLNK-1` bez dodatkowej identyfikacji.

---

## 7. WHO-IS, zapytania o callsign na QRZ.com

| Input | To | Znaczenie |
|---|---|---|
| `callsign` | `WHO-IS` | Krótkie zapytanie: klasa / imię / kraj |
| `F callsign` | `WHO-IS` | Pełne zapytanie: imię / klasa / ulica / miasto / kraj |

Dokument podaje, że zapytanie jest możliwe także przez `WHO-15`.

---

## 8. QRZ, zapytania o obiekty

| Input | To | Znaczenie |
|---|---|---|
| `object name` | `QRZ` | Krótkie zapytanie o obiekt nie starszy niż 2 godziny: nazwa obiektu i tekst |
| `object*` | `QRZ` | Wersja z wildcardem `*` na końcu, odpowiedź zawiera wybór dostępnych obiektów |

---

## 9. METAR, zapytania pogodowe

| Input | To | Znaczenie |
|---|---|---|
| `ICAO Code` | `WXBOT` | Krótkie zapytanie o aktualną pogodę lotniskową, SA/METAR |

Przykład z dokumentu: `EDDL`.

---

## 10. WHERE-IS, pozycje, odległość, alerty

**Ważne:** dokument zaznacza, że `WHERE` i `WHERE-IS` są **case sensitive**.

| Input | To | Znaczenie |
|---|---|---|
| `callsign` | `WHERE` lub `WHERE-IS` | Krótkie zapytanie o odległość, namiar i czas ostatniego raportu |
| `where callsign` | `WHERE` lub `WHERE-IS` | To samo co wyżej |
| `dir callsign` | `WHERE` lub `WHERE-IS` | Tylko kierunek i czas |
| `direction callsign` | `WHERE` lub `WHERE-IS` | Pełna forma `dir` |
| `dis callsign` | `WHERE` lub `WHERE-IS` | Tylko odległość i czas |
| `distance callsign` | `WHERE` lub `WHERE-IS` | Pełna forma `dis` |
| `dis callsign @km` | `WHERE` lub `WHERE-IS` | Odległość w konkretnych jednostkach |
| `pos callsign` | `WHERE` lub `WHERE-IS` | Tylko współrzędne i czas |
| `loc callsign` | `WHERE` lub `WHERE-IS` | To samo co `pos` |
| `position callsign` | `WHERE` lub `WHERE-IS` | Pełna forma `pos` |
| `location callsign` | `WHERE` lub `WHERE-IS` | Pełna forma `loc` |
| `last callsign` | `WHERE` lub `WHERE-IS` | Tylko data i czas ostatniego raportu |
| `alert callsign < 15 km` | `WHERE` lub `WHERE-IS` | Alert, gdy stacja zbliży się poniżej zadanej odległości |
| `alert callsign > 15 km` | `WHERE` lub `WHERE-IS` | Alert, gdy stacja oddali się powyżej zadanej odległości |
| `cancel callsign` | `WHERE` lub `WHERE-IS` | Kasuje zapisany alert |
| `help` | `WHERE` lub `WHERE-IS` | Pokazuje dostępne komendy |

### Jednostki w `WHERE` / `WHERE-IS`

Dostępne jednostki:

- `@miles` lub `@mi`
- `@nm`
- `@yards` lub `@y`
- `@foot` lub `@f`
- `@meters` lub `@m`
- `@km`

### Ograniczenia alertów

- Alert dotyczy tylko **jednej stacji**
- Po wyzwoleniu alert jest usuwany
- Dokument mówi, że trwałe i wielokrotne przechowywanie alertów nie było jeszcze dostępne

---

## 11. SMSGTE

| Input | To | Znaczenie |
|---|---|---|
| `@6135551234 free text...` | `SMSGTE` | System łączący APRS i telefony komórkowe |

### Uwaga

Dokument zaznacza, że `SMSGTE` jest dostępne tylko w **USA i Kanadzie**.

---

## 12. Krótkie podsumowanie praktyczne

Najważniejsze grupy zapytań z dokumentu:

- standardowe zapytania APRS do stacji i systemów
- funkcje specyficzne dla UI-View
- grupy ANSRVR i CQSRVR
- obiekty i katalogi QRU
- AVRS do wyszukiwania najbliższych węzłów głosowych
- APRSlink do Winlinka przez `WLNK-1`
- WHO-IS i QRZ do danych o znakach i obiektach
- WXBOT dla METAR
- WHERE / WHERE-IS dla pozycji, odległości i alertów
- SMSGTE jako most APRS do SMS

