# Stationsbereitschaft

Diese Karte ist eine einfache Checkliste für die erste Inbetriebnahme. Sie zeigt fehlende Konfiguration, prüft aber weder Antennenqualität und Funkreichweite noch, ob andere Stationen deine Frames hören.

## Vor dem Start — drei Begriffe

- **RF** bezeichnet Funkverkehr, der über ein TNC empfangen oder gesendet wird.
- **APRS-IS** ist das APRS-Netzwerk im Internet.
- Ein **Flow** ist eine Routingregel „Quelle → Ziel“, zum Beispiel `Receiver RF → TX APRS-IS`.

Führe die Schritte der Reihe nach aus. Schnittstellen erzeugen die Quellen und Ziele, die später in `Meine Station` und `Packet Routing` verwendet werden.

## Empfohlene Reihenfolge

### 1. Schnittstellen

Öffne zuerst `Schnittstellen` und füge Folgendes hinzu:

- mindestens eine aktive Funkschnittstelle `TCP` oder `SERIALL`; `OpenWebRX MQTT` kann nur empfangen,
- eine Schnittstelle `APRS-IS (RX/TX)`, wenn die Station Daten von APRS-IS empfangen oder dorthin senden soll.

Prüfe, ob die Schnittstellen aktiviert sind, TX am physischen TNC nicht unbeabsichtigt blockiert ist und APRS-IS den verbundenen Zustand erreicht.

**Nach diesem Schritt:** `Funkschnittstellen` und `APRS-IS-Verbindung` sollten grün sein. Sind nur einige konfigurierte Funkschnittstellen aktiv, ist der Funkstatus dunkelgelb. Keine aktive Funkschnittstelle ergibt Rot.

[Hilfe zu Schnittstellen](tnc.de.md)

### 2. Meine Station

Konfiguriere danach `Meine Station`:

- Rufzeichen und SSID,
- Koordinaten und APRS-Symbol,
- Beacon-Kommentar, Intervall und Pfad,
- TX-Ziel: eine Funkschnittstelle, alle aktiven Schnittstellen oder `Internal TX`,
- automatische Beacon-Aussendung, falls periodische Beacons gewünscht sind.

`Internal TX` erzeugt einen Frame innerhalb von APRSBox, sendet ihn aber nicht an ein physisches TNC. Wähle dieses Ziel, wenn ausschließlich das Routing den weiteren Weg bestimmen soll. Eine Funkschnittstelle oder alle aktiven Schnittstellen senden die Bake über RF.

**Nach diesem Schritt:** `Bake definiert` sollte grün sein. Eine definierte Bake allein gelangt noch nicht zu APRS-IS; diesen Weg steuert der Flow aus Schritt 3.

[Hilfe zu Meine Station](station.de.md)

### 3. Packet Routing

Öffne zuletzt `Packet Routing` und lege die zur Stationsrolle passenden aktiven Flows an.

Für eine vollständig grüne Karte prüft APRSBox:

- `Local TX → TX APRS-IS` — lokal erzeugte Beacons, Status, Wetter, Objekte, Items, Bulletins und Nachrichten direkt zu APRS-IS,
- `Receiver RF → TX APRS-IS` für jeden aktiven RF-Eingang — den klassischen iGate-Uplink,
- `APRS-IS → TX RF` für jede aktive TX-fähige Schnittstelle — den geschützten Rückweg geeigneter APRS-IS-Nachrichten,
- `Receiver RF → TX RF` zwischen den erforderlichen aktiven Schnittstellen — Digi- oder Cross-Band-Betrieb entsprechend dem Stationskonzept.

[Hilfe zu Packet Routing](packet_routing.de.md)

**Nach diesem Schritt:** `Local TX → APRS-IS` und die benötigten Felder jeder aktiven Schnittstelle sollten grün sein. Vergleiche eine fehlende Richtung auf der Karte mit der Liste oben.

## Eigene Frames und APRS-IS

Ein über die eigene Funkschnittstelle gesendeter Frame wird nicht automatisch direkt zu APRS-IS hochgeladen. Er kann dort erscheinen, wenn ihn ein eigener oder externer RF-iGate empfängt; das hängt jedoch von RF-Reichweite, Filtern und Verfügbarkeit des Gateways ab.

Sollen eigene Frames unabhängig von einem RF-iGate zu APRS-IS gelangen, erstelle einen aktiven Flow `Local TX → TX APRS-IS`. Das gilt sowohl für Frames an `Internal TX` als auch für eigene Frames, die gleichzeitig über eine Funkschnittstelle gesendet werden.

Dieser Weg ist getrennt von `Receiver RF → TX APRS-IS`: `Local TX` verarbeitet von APRSBox erzeugte Frames, `Receiver RF` tatsächlich per Funk empfangene Frames. Lege keinen Flow vom Funkausgang an; lokal erzeugte Frames verwenden im Routing immer `Local TX` als Quelle.

## Farben

- grün — erforderliches Element aktiv oder Flow vorhanden,
- dunkelgelb — Konfiguration unvollständig oder Flow fehlt,
- rot — keine aktive Schnittstelle oder Verbindungsfehler,
- grau — Schnittstelle deaktiviert oder Richtung nicht anwendbar.

Wenn eine Rolle wie Digi oder `APRS-IS → RF` absichtlich nicht verwendet wird, kann das Feld eine Warnung behalten. Das ist kein Runtime-Fehler, sondern die Abweichung von der vollständigen Bereitschaftsmatrix.
