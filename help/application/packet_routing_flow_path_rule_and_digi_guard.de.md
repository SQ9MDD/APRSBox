# Pfadregel und DIGI-Schutz

Dies ist der zentrale Block fur Flows, die in `TX RF` enden. Er fuehrt zuerst den DIGI-Schutz aus und danach die Pfad-Umschreibung.

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
  Wenn der erste unverbrauchte Hop zu dieser Liste passt, wird der Hop nur als verbraucht markiert, ohne das lokale Digi-Rufzeichen einzutragen.

Was eingetragen werden kann:

- ein voller Hop wie `WIDE1-1`, `WIDE2-1`, `WIDE2-2` oder `SP2-2`,
- ein Familienalias wie `WIDE`; dann passen Mitglieder wie `WIDE1-1` und `WIDE2-2`.

Typische Umschreibungen:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `WIDE2-2` -> `WIDE2-2*,WIDE2-1`,
- NO TRACE `SP2-2` -> `SP2-2*,SP2-1`,
- wenn der Hop nicht im Format `N-N` ist, fuegt NO TRACE nur `*` hinzu.

Typische Starteintraege:

- `TRACE`: `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: das eigene `CALLSIGN-SSID` aus `My settings` plus lokale Ausnahmen gemaess Netzpolitik.

Warum das eigene Rufzeichen oft in `NO TRACE` steht:

- um Pakete zu verbrauchen, die direkt an das eigene Rufzeichen adressiert sind, ohne es erneut in den Pfad einzutragen,
- um explizite lokale Hops ohne TRACE-Spur zu behandeln.

Wichtige Hinweise:

- wenn TRACE passt, aber das lokale Rufzeichen nicht konfiguriert ist, wird der Frame abgelehnt,
- wenn der erste unverbrauchte Hop weder zu TRACE noch zu NO TRACE passt, wird der Frame abgelehnt.

Typische Form:

```text
Empfänger RF -> Duplikatfilter (viscous-delay) -> Pfadregel und DIGI-Schutz -> TX RF
```

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
