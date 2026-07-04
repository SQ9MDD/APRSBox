# Packet-Routing-Regeln

Diese Seite zeigt die Regeln, mit denen APRSBox APRS-Pakete zwischen Eingangen und Ausgangen weiterleitet. Eine Regel hat eine Quelle, optionale Filter in der Mitte und ein Ziel.

Die Regeln werden von oben nach unten ausgewertet. Die Reihenfolge in der Liste ist wichtig, besonders wenn mehrere Regeln ahnlichen Verkehr beschreiben.

## Typische Verwendung

- per RF empfangene Frames zu APRS-IS weiterleiten,
- RF-Verkehr zu einem RF-Ausgang digipeaten,
- lokal von APRSBox erzeugte Frames zu APRS-IS senden,
- ausgewahlten Verkehr nur protokollieren,
- Verkehr verwerfen, der nicht weiterlaufen soll.

## Quellen und Ziele

`Receiver RF` bedeutet Pakete, die von einem konfigurierten Funkmodem empfangen wurden.

`Local TX` bedeutet Frames, die APRSBox selbst erzeugt, zum Beispiel Beacon, Status, Wetter, Objekte, Items, Bulletins und Nachrichten.

Ziele sind `TX RF`, `TX APRS-IS`, `Black Hole` fur reine Protokollierung und `Action Drop` zum Verwerfen am Ende der Regel.

`Local TX` kann nur zu APRS-IS oder zur reinen Protokollierung geroutet werden.

## Filter

Filter laufen der Reihe nach. Wenn ein Paket durch einen Filter abgelehnt wird, werden die weiteren Schritte nicht ausgefuhrt.

Wichtige Filter:

- `Strict Filter` lehnt `TCPIP`, `TCPXX`, `NOGATE`, `RFONLY` und ungultige Third-Party-Pakete ab.
- `Path rule and DIGI guard` verarbeitet den Digi-Pfad und blockiert Frames, die diese Station nicht wiederholen soll.
- `Duplicate Filter` stellt ein kurzes Viscous-Delay-Fenster bereit.
- `Direct Only` lasst nur direkt gehorte Pakete durch.
- Callsign-, Digi-, Pakettyp-, Icon-, Distanz- und Rate-Limit-Filter begrenzen den Verkehr vor der Aussendung.

## Systemschutz

`TX APRS-IS`-Regeln sind auf einen verpflichtenden `Strict Filter` beschrankt.

`TX RF`-Regeln erfordern einen aktiven Schritt `Path rule and DIGI guard`.

Nur eine aktive Regel kann zur gleichen Zeit dasselbe Quelle-Ziel-Paar bedienen.
