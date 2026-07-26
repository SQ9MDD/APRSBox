# Schnittstellen

Der Tab Schnittstellen konfiguriert APRSBox-Eingänge. Funkinterfaces können KISS/TNC2 empfangen, Outbound-Frames senden und optional einen KISS-Port im LAN bereitstellen. APRS-IS kann als reiner Empfangseingang aktiviert werden.

## Schnittstellenliste

Die Tabelle zeigt konfigurierte Interfaces. Klicke eine Zeile an, um sie zu bearbeiten.

- `Status` zeigt Konfigurations- und Runtime-Status, zum Beispiel verbunden, Fehler oder deaktiviert.
- `TX Block` zeigt, ob Senden über dieses Interface blockiert ist.
- `LAN` zeigt, ob APRSBox einen KISS/TNC-Proxy für LAN-Clients bereitstellt.

Das Deaktivieren einer Schnittstelle stoppt ihren Empfang. Bei einer Funkschnittstelle wird außerdem die Verwendung durch den Outbound-Service gestoppt.

## Interface-Typen

- `TCP` verbindet sich mit einem TNC oder einer Software, die KISS über TCP bereitstellt. `Pfad / Adresse / Filter` hat normalerweise das Format `host:port`, zum Beispiel `127.0.0.1:8001`.
- `SERIALL` nutzt einen lokalen seriellen Port, zum Beispiel `/dev/ttyUSB0` oder `/dev/ttyACM0`, und benötigt eine gültige `Baud Rate`.
- `OpenWebRX MQTT (RX only)` empfängt Pakete von OpenWebRX MQTT. Dieser Typ ist nur für RX: TX wird blockiert und der LAN-Proxy deaktiviert.
- `APRSIS` empfängt TNC2-Zeilen über die vorhandene, in den iGate-Einstellungen konfigurierte APRS-IS-Verbindung. KISS wird nicht verwendet; diese Schnittstelle ist nur für Empfang vorgesehen. Es darf nur eine APRSIS-Schnittstelle geben.

Für OpenWebRX MQTT sollte das Adressfeld eine `mqtt://`- oder `mqtts://`-URL mit Topic im Pfad sein, zum Beispiel `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

Für APRSIS ist `Pfad / Adresse / Filter` der APRS-IS-Serverfilter. Neue Schnittstellen verwenden standardmäßig `m/20`; ein anderer gültiger Filter wie `r/52.23/21.01/50` kann eingegeben werden. Server, Port, Rufzeichen und Passcode stammen weiterhin aus den iGate-Einstellungen.

## Konfigurationsfelder

- `Name` erscheint in Logs, Interface-Listen und TX-Auswahlen.
- `Band` beschreibt das Band des Interfaces.
- `Enabled` aktiviert das Interface in der APRSBox-Runtime.
- `Block TX on this interface` erlaubt Empfang, blockiert aber Outbound-Sendungen.
- `TX Min Gap (s)` setzt die minimale Pause zwischen Sendungen auf diesem TNC. Erlaubt sind `0.2` bis `1.2` Sekunden.
- `RX Silence Reconnect Timeout (s)` gilt für serielle Interfaces. Nach längerer RX-Stille kann der serielle Broker einen Reconnect erzwingen. `0` deaktiviert diesen Watchdog.

`Baud Rate` wird nur für `SERIALL` verwendet. Für APRSIS werden Felder für seriellen Port, TX und LAN-Proxy ausgeblendet.

## Expose Port

`Expose Port` stellt die TNC-Verbindung über APRSBox als TCP-Port für LAN-Clients bereit. APRSBox leitet Frames zwischen physischem TNC und Clients weiter.

- `Allow TX from remote clients` erlaubt LAN-Clients das Senden von Frames an den TNC. Wenn deaktiviert, können Clients nur empfangen.
- `Bind Address` definiert die Listen-Adresse. `0.0.0.0` bedeutet alle Netzwerkinterfaces.
- `Port` ist der von APRSBox bereitgestellte TCP-Port. Bis zu 3 gleichzeitige Clients werden unterstützt.
- `Whitelist` beschränkt den Zugriff auf IPv4-Adressen oder CIDR-Netze. Ein Eintrag pro Zeile; Kommas werden ebenfalls akzeptiert.

Aktiviere Remote-TX nicht in einem nicht vertrauenswürdigen Netzwerk. Wenn du den Port über die lokale Maschine hinaus bereitstellst, konfiguriere eine Whitelist.

## Wann mehrere Schnittstellen sinnvoll sind

Mehrere aktive Schnittstellen können parallel laufen. Empfangener Traffic wird pro Schnittstelle behandelt, während Funksendungen von der Auswahl in der jeweiligen Ansicht abhängen. Über APRS-IS empfangener Traffic ist im Verlauf, in Stationsdetails und auf der Karte sichtbar, wird aber aus allen APRSBox-Statistiken ausgeschlossen.

Wenn du nur Eingangsdaten von OpenWebRX brauchst, nutze `OpenWebRX MQTT (RX only)`. Wenn du vollständiges Funk-RX/TX brauchst, nutze `TCP` oder `SERIALL`.
