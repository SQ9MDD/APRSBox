# DIGI-Filter

Dieser Filter betrachtet nicht den gesamten Pfad und nicht die noch unverbrauchten Hops. Er untersucht nur Hops, die bereits mit `*` markiert sind, nachdem dieses Zeichen entfernt wurde.

Tatsaechliches Verhalten:

- aus `SR5BCD-2*,WIDE1-1` sieht er nur `SR5BCD-2`,
- aus `WIDE1-1` sieht er nichts, weil noch kein Hop verbraucht wurde,
- Muster werden gegen verbrauchte Hops gepruft; `*` darf an beliebiger Stelle stehen,
- `allow` laesst nur durch, wenn mindestens ein verbrauchter Hop passt,
- `deny` lehnt nur ab, wenn mindestens ein verbrauchter Hop passt.

Praktische Folgen:

- eine leere `allow`-Liste lehnt alles ab,
- eine leere `deny`-Liste laesst alles durch,
- `*` in `deny` blockiert jeden bereits digipeateten Frame,
- `*` in `deny` blockiert keine echten Direct-Frames, weil es dort keinen verbrauchten Hop zum Pruefen gibt.

Beispiele:

- Pfad `SR5BCD-2*,WIDE1-1` plus Muster `SR5BCD*` -> Treffer,
- Pfad `SR5ABC*,WIDE1-1` plus `deny: *` -> Drop,
- Pfad `WIDE1-1` plus `deny: *` -> Pass.

Verwende ihn, wenn:

- nur Verkehr ueber ausgewaehlte Digis passieren soll,
- bereits von bestimmten Zwischenstationen wiederholter Verkehr ausgeschlossen werden soll.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
