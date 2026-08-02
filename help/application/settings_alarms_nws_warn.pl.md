# Ostrzeżenia NWS-WARN w APRSBox

`NWS-WARN` jest dedykowanym profilem odbiorczym APRSBox dla zwartych amerykańskich ostrzeżeń powiatowych skierowanych do grupy APRS `NWS-WARN`. Jest to otoczka przekaźnikowa APRS, a nie bezpośrednie połączenie z National Weather Service ani pełny produkt NWS CAP lub VTEC.

APRSBox nie pobiera alertów z `api.weather.gov`. Interpretuje wyłącznie ramki APRS odebrane przez skonfigurowany interfejs RF albo APRS-IS.

## Konfiguracja

- Włącz alarmy APRS i dodaj dokładną grupę `NWS-WARN`.
- Ustaw próg Alarmy dla odpowiednich kategorii zdarzeń. Bez niego odebrane ramki pozostają w Monitorze ruchu, ale nie tworzą wpisów NWS-WARN.
- Progi Popup alarmu włącz tylko dla kategorii, które mają przerwać pracę operatora.
- Sprawdź, czy automatyczny filtr APRS-IS zawiera `g/NWS-WARN` i czy wymagany interfejs odbiorczy jest aktywny.

## Postać ramki obsługiwana przez APRSBox

```text
SOURCE>APRS,...::NWS-WARN :DDHHMMz,EVENTLEVEL,SSCnnn[,SSCnnn...]{MSGID
```

Przykład:

```text
NWSWX>APRS,TCPIP*::NWS-WARN :010200z,TORNADO3,TNC037,TNC189{N1001
```

Dziewięcioznakowe pole adresata APRS zawiera `NWS-WARN` uzupełnione spacją. Ponieważ jest to biuletyn grupowy, APRSBox nigdy nie wysyła ACK.

## Pola interpretowane przez APRSBox

- `DDHHMMz` oznacza dzień, godzinę i minutę wygaśnięcia w UTC. APRSBox wybiera najbliższy prawidłowy miesiąc i rok względem chwili odbioru. Sufiks `z` lub `Z` jest wymagany do automatycznego wygaśnięcia.
- `EVENTLEVEL` jest nazwą zdarzenia. Historyczne materiały APRS definiują typ jako tekst dowolny; APRSBox dodatkowo odczytuje końcowe cyfry jako ważność. Dla przewidywalnych progów i kolorów należy używać znormalizowanego kodu zakończonego `1`, `2` albo `3`, na przykład `TORNADO3`.
- `SSCnnn` jest kodem Universal Geographic Code NWS w postaci powiatowej. Wiele kodów rozdzielonych przecinkami tworzy jeden alarm.
- `MSGID` to alfanumeryczny identyfikator wiadomości APRS o długości 1–5 znaków. Służy do deduplikacji przesłanej wiadomości; jest informacją referencyjną i nie żąda ACK.

Historyczny tekst pogodowy APRS opisywał także etykiety powiatów oparte na nazwach i najwyżej pięć pól powiatowych. Bieżący profil mapowy NWS-WARN w APRSBox oczekuje stabilnych maszynowo kodów UGC, aby pewnie łączyć je z geometrią.

## Kody powiatowe UGC

Kod obsługiwany na mapie ma dokładnie sześć znaków:

```text
SS C nnn
```

- `SS` jest dwuliterowym identyfikatorem stanu lub terytorium USA.
- `C` oznacza county, parish albo independent city.
- `nnn` jest trzycyfrową częścią powiatową identyfikatora FIPS.
- `TNC037` identyfikuje w tej postaci Davidson County w Tennessee.

NWS używa także kodów `Z` dla publicznych stref prognoz i obszarów morskich. APRSBox celowo mapuje tylko kody powiatowe pasujące do `[A-Z]{2}C[0-9]{3}`. Kod `TNZ037` albo `ANZ630` pozostaje w zapisanym alarmie, lecz nie jest rysowany. Poprawny składniowo kod powiatu, którego nie ma w dołączonej geometrii, na przykład kod nieznany lub wycofany, również jest pomijany na mapie.

Zbiór granic powiatów NWS zmienia się w czasie. Gdy oficjalny kod nie jest rysowany, trzeba porównać wersję geometrii zainstalowaną w APRSBox z bieżącym zbiorem GIS NWS.

## Ważność zdarzenia i progi

APRSBox stosuje wspólną skalę alarmową:

```text
1 = żółty
2 = pomarańczowy
3 = czerwony
```

Ten sufiks liczbowy jest konwencją transportową APRSBox/CAWF, a nie pełnym modelem ważności NWS CAP ani mapowaniem zdefiniowanym w historycznej składni biuletynu APRS NWS. Operator przekaźnika odpowiada za opisanie, jak oficjalny produkt NWS staje się poziomem 1–3.

Jeśli sufiksu brakuje albo ma wartość spoza 1–3, ważność jest nieznana. Gdy kategoria zdarzenia jest włączona, APRSBox zachowuje alarm zamiast cicho go odrzucić; dostępna geometria jest szara. Znane prefiksy nazw wybierają kategorię, a nazwa nierozpoznana trafia do `Inne / nieznane`.

## Cykl życia, powtórzenia i odwołanie

- Prawidłowa przyjęta ramka tworzy alarm zawierający wszystkie przesłane kody powiatów i odnośnik do ramki źródłowej w Monitorze ruchu.
- Ten sam nadawca, grupa i identyfikator APRS oznaczają powtórzenie tej samej wiadomości ostrzegawczej. Powtórzenia aktualizują liczniki i czas ostatniego odbioru zamiast tworzyć duplikat.
- Nowy identyfikator wiadomości nie ma w tej otoczce wspólnego logicznego ID zdarzenia NWS, dlatego APRSBox traktuje go jako osobny alarm nawet przy identycznym zdarzeniu i powiatach.
- Rozwiązany czas `DDHHMMz` dezaktywuje alarm w chwili wygaśnięcia. Ramki i historia pozostają zapisane.
- Historyczna rodzina APRS obejmuje `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` i `NWS-CANCL`. APRSBox ma dedykowaną geometrię powiatów USA tylko dla `NWS-WARN` i nie interpretuje `NWS-CANCL` jako odwołania istniejącego alarmu.
- Brakujący lub błędny czas wygaśnięcia może pozostawić alarm aktywny aż do ręcznego usunięcia. Przy uszkodzonej ramce należy sprawdzić widok szczegółów.

## Czego brakuje względem oficjalnych danych NWS

Oficjalne usługi NWS dystrybuują w CAP v1.2 watches, warnings, advisories i podobne produkty. Rekordy mogą zawierać nagłówek, opis, instrukcje, pilność, ważność, pewność, czasy obowiązywania, strefy UGC, poligony oraz stan zdarzenia VTEC.

Zwarta otoczka NWS-WARN w APRSBox przenosi tylko wygaśnięcie, token zdarzenia i poziomu, kody powiatów, nadawcę oraz ID wiadomości APRS. Nie da się z niej odtworzyć pominiętych instrukcji, poligonów, pewności, akcji VTEC, oficjalnych identyfikatorów ani relacji aktualizacji. Gdy jest dostępny, do decyzji operacyjnych należy używać powiązanego oficjalnego produktu NWS.

## Zaufanie i bezpieczne użycie

Adres `NWS-WARN` nie dowodzi, że nadawcą jest National Weather Service. APRS i APRS-IS nie uwierzytelniają kryptograficznie tej otoczki, a APRSBox nie ma obecnie listy zaufanych nadawców dla grupy.

Ramkę należy traktować jako dodatkową informację sytuacyjną. Ostrzeżenia o dużym wpływie trzeba potwierdzać w oficjalnym serwisie NWS, szczególnie gdy callsign źródła jest nieznany, mapowanie poziomu nieudokumentowane, czas wygaśnięcia błędny albo brakuje geometrii powiatu.

## Źródła

- [TAPR APRS Protocol Reference — adres biuletynu NWS i brak ACK](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- Dołączony historyczny dokument pogodowy APRS `APRS-SPEC/WX.TXT`, definiujący rodzinę `NWS-WARN`, `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` i `NWS-CANCL`.
- [Dyrektywa NOAA/NWS dotycząca Universal Geographic Code](https://www.weather.gov/media/directives/010_pdfs_archived/pd01017002b.pdf).
- [Zbiór GIS powiatów USA NOAA/NWS](https://www.weather.gov/gis/Counties).
- [Dokumentacja usługi alertów NWS CAP](https://www.weather.gov/documentation/services-web-alerts).
- [Dokumentacja NWS VTEC](https://www.weather.gov/vtec/).

[Wróć do ustawień alarmów APRS](settings_alarms.pl.md)
