# Distanzfilter

Dieser Filter laesst einen Frame nur durch, wenn die decodierte Position in mindestens einer konfigurierten Zone liegt.

So arbeitet er:

- es koennen 1 bis 3 Zonen definiert werden,
- jede Zone hat Mittelpunkt und Radius,
- die Zonen arbeiten mit OR-Logik,
- wenn keine gueltige Zone vorhanden ist, wird der Filter uebersprungen,
- wenn der Frame keine decodierbare Position hat, wird der Filter uebersprungen,
- nur ein Frame mit Position ausserhalb aller Zonen wird abgelehnt.

Verwende ihn, wenn:

- Verkehr auf ein geografisches Gebiet begrenzt werden soll,
- lokales Routing von Abdeckung oder Veranstaltungsgebiet abhaengen soll.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
