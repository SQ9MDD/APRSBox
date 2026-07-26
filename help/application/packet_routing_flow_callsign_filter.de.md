# Quellrufzeichenfilter

Dieser Filter prueft nur das Quellrufzeichen. Pfad, Digi-Hops und Ziel spielen keine Rolle.

So arbeitet er:

- ohne `*` ist der Treffer exakt,
- `SQ9MDD` passt nicht zu `SQ9MDD-4`,
- `*` darf an beliebiger Stelle stehen,
- `allow` arbeitet wie eine Allowlist,
- `deny` arbeitet wie eine Blocklist.

Praktische Folgen:

- eine leere `allow`-Liste lehnt alles ab,
- eine leere `deny`-Liste laesst alles durch.

Beispiele:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Verwende ihn, wenn:

- Club-, Test-, Service- oder Operatorverkehr getrennt werden soll,
- eine bekannte Quelle blockiert oder isoliert werden soll.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
