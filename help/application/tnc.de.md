# TNC

Der TNC-Tab konfiguriert Funkinterfaces, die APRSBox für KISS/TNC2-Empfang, Outbound-Sendungen und optionales KISS-Port-Sharing im LAN verwendet.

## TNC-Liste

Die Tabelle zeigt konfigurierte Interfaces. Klicke eine Zeile an, um sie zu bearbeiten.

- `Status` zeigt Konfigurations- und Runtime-Status, zum Beispiel verbunden, Fehler oder deaktiviert.
- `TX Block` zeigt, ob Senden über dieses Interface blockiert ist.
- `LAN` zeigt, ob APRSBox einen KISS/TNC-Proxy für LAN-Clients bereitstellt.

Das Deaktivieren eines TNC verhindert, dass Traffic-Monitor und Outbound-Service ihn verwenden. Beacon, WX, Objekte, Bulletins und Nachrichten können weiterhin auf dieses Interface zeigen, aber die Sendung wird je nach Kontext übersprungen oder schlägt fehl.

## Interface-Typen

- `TCP` verbindet sich mit einem TNC oder einer Software, die KISS über TCP bereitstellt. `Path / Adress` hat normalerweise das Format `host:port`, zum Beispiel `127.0.0.1:8001`.
- `SERIALL` nutzt einen lokalen seriellen Port, zum Beispiel `/dev/ttyUSB0` oder `/dev/ttyACM0`, und benötigt eine gültige `Baud Rate`.
- `OpenWebRX MQTT (RX only)` empfängt Pakete von OpenWebRX MQTT. Dieser Typ ist nur für RX: TX wird blockiert und der LAN-Proxy deaktiviert.

Für OpenWebRX MQTT sollte das Adressfeld eine `mqtt://`- oder `mqtts://`-URL mit Topic im Pfad sein, zum Beispiel `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

## Konfigurationsfelder

- `Name` erscheint in Logs, Interface-Listen und TX-Auswahlen.
- `Band` beschreibt das Band des Interfaces.
- `Enabled` aktiviert das Interface in der APRSBox-Runtime.
- `Block TX on this interface` erlaubt Empfang, blockiert aber Outbound-Sendungen.
- `TX Min Gap (s)` setzt die minimale Pause zwischen Sendungen auf diesem TNC. Erlaubt sind `0.2` bis `1.2` Sekunden.
- `RX Silence Reconnect Timeout (s)` gilt für serielle Interfaces. Nach längerer RX-Stille kann der serielle Broker einen Reconnect erzwingen. `0` deaktiviert diesen Watchdog.

`Baud Rate` wird nur für `SERIALL` verwendet. Für `TCP` und `OpenWebRX MQTT` wird sie ignoriert.

## Expose Port

`Expose Port` stellt die TNC-Verbindung über APRSBox als TCP-Port für LAN-Clients bereit. APRSBox leitet Frames zwischen physischem TNC und Clients weiter.

- `Allow TX from remote clients` erlaubt LAN-Clients das Senden von Frames an den TNC. Wenn deaktiviert, können Clients nur empfangen.
- `Bind Address` definiert die Listen-Adresse. `0.0.0.0` bedeutet alle Netzwerkinterfaces.
- `Port` ist der von APRSBox bereitgestellte TCP-Port. Bis zu 3 gleichzeitige Clients werden unterstützt.
- `Whitelist` beschränkt den Zugriff auf IPv4-Adressen oder CIDR-Netze. Ein Eintrag pro Zeile; Kommas werden ebenfalls akzeptiert.

Aktiviere Remote-TX nicht in einem nicht vertrauenswürdigen Netzwerk. Wenn du den Port über die lokale Maschine hinaus bereitstellst, konfiguriere eine Whitelist.

## Wann mehrere TNCs sinnvoll sind

Mehrere aktive TNCs können parallel laufen. Empfangener Traffic wird pro Interface behandelt, während Sendungen von der Auswahl in der jeweiligen Ansicht abhängen, zum Beispiel `My Station`, `WX`, Objekte, Bulletins, Nachrichten oder `Packet Routing`-Regeln.

Wenn du nur Eingangsdaten von OpenWebRX brauchst, nutze `OpenWebRX MQTT (RX only)`. Wenn du vollständiges Funk-RX/TX brauchst, nutze `TCP` oder `SERIALL`.
