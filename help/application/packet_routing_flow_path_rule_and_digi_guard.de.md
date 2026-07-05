# Pfadregel und DIGI-Schutz

Dies ist der zentrale Block fur Flows, die in `TX RF` enden. Er fuehrt zuerst den DIGI-Schutz aus und danach die Pfad-Umschreibung. Dieser Block sollte immer der letzte Block im Flow sein, weil er den Pfad veraendert und andere Filter stoeren kann.

Der Schutzteil lehnt ab:

- Third-Party-Frames,
- APRS-Nachrichten an lokale `My station`,
- APRS-Queries an lokale `My station`,
- APRS-Nachrichten an lokale `WX station`,
- APRS-Queries an lokale `WX station`,
- Frames, in denen die lokale Station bereits als verbrauchter Hop vorkommt, zum Beispiel `MYCALL-SSID*`.

Erst danach wird der Pfad bearbeitet:

- ist der Pfad leer, wird der Frame abgelehnt,
- sind alle Hops bereits verbraucht, wird der Frame abgelehnt,
- nur der erste noch nicht verbrauchte Hop wird gepruft,
- spaetere Hops bleiben unberuehrt, bis dieser erste Hop behandelt ist.

Konfigurationsfelder:

- `Paths (TRACE / traced)`:
  Wenn der erste unverbrauchte Hop zu dieser Liste passt, verbraucht APRSBox ihn und fuegt das lokale Digi-Rufzeichen aus `My settings` ein.
- `Paths (NO TRACE / not traced)`:
  Wenn der erste unverbrauchte Hop zu dieser Liste passt, reduziert APRSBox diesen Hop an Ort und Stelle, ohne das lokale Digi-Rufzeichen einzutragen.

Was eingetragen werden kann:

- jeder Eintrag steht in einer eigenen Zeile,
- `TRACE`: ein voller Hop wie `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: ein voller Hop wie `SP1-1`, `SP2-1`, `SP2-2` oder das eigene `CALLSIGN-SSID`.
- `WIDE2-2` passt nur zu `WIDE2-2`; es behandelt nicht `WIDE2-1` oder `WIDE1-1`,
- `SP2-2` passt nur zu `SP2-2`; es behandelt nicht `SP2-1` oder `SP1-1`,
- jeder unterstuetzte Pfad muss in einer eigenen Zeile stehen.

Typische Umschreibungen:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `SP1-1` -> `SP1*`,
- NO TRACE `SP2-1` -> `SP2*`,
- NO TRACE `SP2-2` -> `SP2-1`,
- wenn der Hop nicht im Format `N-N` ist, fuegt NO TRACE nur `*` hinzu.

Typische Starteintraege:

`TRACE`:

- `WIDE1-1` - nur Pfad `WIDE1-1`,
- `WIDE2-1` - nur Pfad `WIDE2-1`,
- `WIDE2-2` - nur Pfad `WIDE2-2`.

`NO TRACE`:

- `SP1-1` - nur Pfad `SP1-1`,
- `SP2-1` - nur Pfad `SP2-1`,
- `SP2-2` - nur Pfad `SP2-2`,
- `CALLSIGN-SSID` - eigener expliziter Hop, der ohne TRACE reduziert werden soll.

Warum das eigene Rufzeichen oft in `NO TRACE` steht:

- um Pakete zu verbrauchen, die direkt an das eigene Rufzeichen adressiert sind, ohne es erneut in den Pfad einzutragen,
- um explizite lokale Hops ohne TRACE-Spur zu behandeln,
- um lokale Hops der Familie `SP` zu reduzieren, ohne das eigene Rufzeichen in den Pfad einzutragen.

Wichtige Hinweise:

- wenn TRACE passt, aber das lokale Rufzeichen nicht konfiguriert ist, wird der Frame abgelehnt,
- wenn der erste unverbrauchte Hop weder zu TRACE noch zu NO TRACE passt, wird der Frame abgelehnt.

Typische Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
