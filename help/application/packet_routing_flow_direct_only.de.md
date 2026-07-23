# Filter für direkten RF-Empfang

Dieser Filter laesst nur direkt gehoerte Pakete durch.

Tatsaechliches Verhalten:

- er prueft nur, ob der Pfad bereits einen verbrauchten Hop mit `*` enthaelt,
- unverbrauchte Hops wie `WIDE1-1` stoeren ihn nicht,
- `...,WIDE1-1:` passiert,
- `...,SR5ABC*,WIDE1-1:` wird abgelehnt.

Verwende ihn, wenn:

- die Regel nur auf direkt gehoerte Stationen reagieren soll,
- bereits wiederholter Verkehr ignoriert werden soll,
- du Direktabdeckung getrennt untersuchen willst.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
