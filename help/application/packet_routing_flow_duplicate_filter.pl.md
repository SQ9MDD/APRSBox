# Filtr opóźnienia duplikatów RF

Ten blok nie przepuszcza pakietu od razu. Pierwsza ramka z danym fingerprintem zostaje najpierw wstrzymana na czas okna nasłuchu.

Jak działa naprawdę:

- okno nasłuchu można ustawić od `2` do `7` sekund,
- fingerprint budowany jest z `source callsign + info field`,
- ścieżka nie bierze udziału w porównaniu duplikatów,
- pierwsza ramka z danym fingerprintem czeka do końca okna,
- jeśli w tym czasie pojawi się druga ramka z tym samym fingerprintem, obie są odrzucane,
- jeżeli do końca okna nie pojawi się duplikat, pierwsza ramka rusza dalej dopiero po wygaśnięciu timera.

Konsekwencje praktyczne:

- dwa pakiety od tej samej stacji z tym samym payloadem, ale z inną ścieżką, nadal liczą się jako duplikat,
- filtr działa jak viscous-delay: najpierw czeka, potem dopiero decyduje,
- może wystąpić tylko raz i powinien być pierwszym filtrem w ścieżce RF.

Kiedy używać:

- gdy kilka digi może słyszeć tę samą stację,
- gdy chcesz ograniczyć zbędne powtórzenia bez natychmiastowego TX.

## Nawigacja

[Wróć do opisu Packet Flow](packet_routing_flow.pl.md)
