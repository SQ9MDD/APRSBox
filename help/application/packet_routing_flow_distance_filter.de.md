# Positionszonenfilter

Dieser Filter laesst einen Frame nur durch, wenn die decodierte Position in mindestens einer konfigurierten Zone liegt.

So arbeitet er:

- es koennen 1 bis 3 Zonen definiert werden,
- jede Zone hat Mittelpunkt und Radius,
- die Zonen arbeiten mit OR-Logik,
- die GUI verlangt 1 bis 3 vollständige Mittelpunkt+Radius-Zonen; nur fehlerhafte Altdaten ohne gültige Zone werden übersprungen,
- wenn der Frame keine decodierbare Position hat, wird der Filter uebersprungen,
- nur ein Frame mit Position ausserhalb aller Zonen wird abgelehnt.

Verwende ihn, wenn:

- Verkehr auf ein geografisches Gebiet begrenzt werden soll,
- lokales Routing von Abdeckung oder Veranstaltungsgebiet abhaengen soll.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
