# Duplikatfilter (viscous-delay)

Dieser Block laesst den Frame nicht sofort durch. Der erste Frame mit einem bestimmten Fingerprint wird bis zum Ende des Horfensters zurueckgehalten.

Tatsaechliches Verhalten:

- der Fingerprint besteht aus `source callsign + info field`,
- der Pfad spielt beim Duplikatvergleich keine Rolle,
- der erste Frame wartet bis zum Ende des Fensters,
- erscheint waehrenddessen ein zweiter Frame mit demselben Fingerprint, werden beide verworfen,
- erscheint kein Duplikat, laeuft der erste Frame erst nach Ablauf des Timers weiter.

Praktische Folgen:

- zwei Frames derselben Station mit identischer Nutzlast, aber unterschiedlichem Pfad, zaehlen trotzdem als Duplikat,
- dies ist echtes viscous-delay: erst warten, dann entscheiden,
- er darf nur einmal vorkommen und sollte der erste Filter eines RF-Wiederholpfads sein.

Verwende ihn, wenn:

- mehrere Digis dieselbe Quellstation horen koennen,
- unnoetige Wiederholungen ohne sofortiges TX reduziert werden sollen.

## Navigation

[Zurück zur Packet-Flow-Regelreferenz](packet_routing_flow.de.md)
