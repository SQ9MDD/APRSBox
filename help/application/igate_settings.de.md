# iGate-Einstellungen

Diese Seite konfiguriert die APRSBox-Verbindung zu APRS-IS und zeigt den Laufzeitstatus des Uplinks. Sie ist kein eigener iGate-Einschalter. Verkehr wird durch aktive `Packet Routing`-Abläufe an APRS-IS gesendet, die mit dem Ziel `TX APRS-IS` enden.

## Wann diese Seite genutzt wird

- `Empfänger RF -> TX APRS-IS` erstellt den klassischen iGate-Uplink vom Funkkanal zu APRS-IS.
- `Local TX -> TX APRS-IS` sendet lokal von APRSBox erzeugte Frames an APRS-IS, zum Beispiel Beacon, Status, Wetter, Objekte, Items, Bulletins und Nachrichten.

Eine detaillierte Anleitung zum Aufbau dieser Pfade gibt es hier:

[Packet Routing](packet_routing.de.md)

## Konfigurationsfelder

- `Server` ist der APRS-IS-Host. Der Standardwert ist `rotate.aprs2.net`.
- `Port` ist der Port des APRS-IS-Servers. Ein typischer Wert ist `14580`.
- `Login callsign / callsign-SSID` kann leer bleiben. Dann nutzt die Anwendung das Rufzeichen der lokalen Station.
- `Passcode` kann leer bleiben. Dann berechnet die Anwendung den Standard-APRS-IS-Passcode für das Login-Rufzeichen.

Der APRS-IS-Passcode ist kein Kontopasswort. Er ist der standardisierte Code, der aus dem Rufzeichen berechnet wird und von APRS-IS-Servern zum Senden von Frames verlangt wird.

## Diagnose

Das Statuspanel zeigt die aktuelle Verbindung, das Login, aktive APRSIS-Abläufe, den letzten Fehler sowie Zähler für gesendete und vor APRS-IS TX verworfene Frames.

Das Ziel `TX APRS-IS` nutzt einen Systemsicherheitsfilter. Er verwirft unter anderem Frames mit `TCPIP`- / `TCPXX`-Tokens, Frames mit `NOGATE` / `RFONLY` und fehlerhafte Third-Party-Encapsulation.
