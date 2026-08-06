# Schnittstellen

Der Tab Schnittstellen konfiguriert APRSBox-Ein- und Ausgänge. Funkinterfaces können KISS/TNC2 empfangen, Outbound-Frames senden und optional einen KISS-Port im LAN bereitstellen. Die APRS-IS-Verbindung unterstützt sowohl Empfang als auch durch `Packet Routing` gesteuertes Senden.

## Schnittstellenliste

Die Tabelle zeigt konfigurierte Interfaces. Klicke eine Zeile an, um sie zu bearbeiten.

- `Status` zeigt Konfigurations- und Runtime-Status, zum Beispiel verbunden, Fehler oder deaktiviert.
- `TX-Steuerung` zeigt die TX-Sperre für ein physisches TNC. Bei APRS-IS zeigt das Routing-Symbol, ob ein aktiver Flow mit dem Ziel `TX APRS-IS` vorhanden ist.
- `LAN` zeigt, ob APRSBox einen KISS/TNC-Proxy für LAN-Clients bereitstellt.

Das Deaktivieren einer Schnittstelle stoppt ihren Empfang. Bei einer Funkschnittstelle wird außerdem die Verwendung durch den Outbound-Service gestoppt. Bei APRS-IS steuert `APRS-IS-Verbindung aktivieren` die gesamte gemeinsame RX/TX-Verbindung. Ist sie deaktiviert, bleiben aktive Flows mit dem Ziel `TX APRS-IS` konfiguriert, können aber nicht senden.

## Interface-Typen

- `TCP` verbindet sich mit einem TNC oder einer Software, die KISS über TCP bereitstellt. `Pfad / Adresse / Filter` hat normalerweise das Format `host:port`, zum Beispiel `127.0.0.1:8001`.
- `SERIALL` nutzt einen lokalen seriellen Port, zum Beispiel `/dev/ttyUSB0` oder `/dev/ttyACM0`, und benötigt eine gültige `Baud Rate`.
- `OpenWebRX MQTT (RX only)` empfängt Pakete von OpenWebRX MQTT. Dieser Typ ist nur für RX: TX wird blockiert und der LAN-Proxy deaktiviert.
- `APRS-IS (RX/TX)` enthält die vollständige APRS-IS-Verbindungskonfiguration direkt im Schnittstellenformular. Es empfängt TNC2-Zeilen gemäß Serverfilter und sendet Frames, die ein Flow `Receiver RF -> TX APRS-IS` oder `Local TX -> TX APRS-IS` zulässt, über dieselbe Verbindung. KISS wird nicht verwendet. Es darf nur eine APRSIS-Schnittstelle geben.

Für OpenWebRX MQTT sollte das Adressfeld eine `mqtt://`- oder `mqtts://`-URL mit Topic im Pfad sein, zum Beispiel `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

Für APRSIS ist `APRS-IS-Empfangsfilter` der APRS-IS-Serverfilter. Neue Schnittstellen verwenden standardmäßig `m/20`; ein anderer gültiger Filter wie `r/52.23/21.01/50` kann eingegeben werden. Server, Port, Login und Passcode werden im selben Formular gespeichert. Der separate Tab `iGATE-Einstellungen` wird nicht mehr verwendet.

## Konfigurationsfelder

- `Name` erscheint in Logs, Interface-Listen und TX-Auswahlen.
- `Band` beschreibt das Band des Interfaces.
- `Enabled` aktiviert ein physisches Interface im APRSBox-Runtime. Bei APRS-IS aktiviert `APRS-IS-Verbindung aktivieren` die gemeinsame Verbindung für Empfang und Senden; Flows mit dem Ziel `TX APRS-IS` bestimmen weiterhin, welche Frames gesendet werden dürfen.
- `Block TX on this interface` erlaubt Empfang, blockiert aber Outbound-Sendungen.
- `TX Min Gap (s)` setzt die minimale Pause zwischen Sendungen auf diesem TNC. Erlaubt sind `0.2` bis `1.2` Sekunden.
- `RX Silence Reconnect Timeout (s)` gilt für serielle Interfaces. Nach längerer RX-Stille kann der serielle Broker einen Reconnect erzwingen. `0` deaktiviert diesen Watchdog.

`Baud Rate` wird nur für `SERIALL` verwendet. Für APRSIS werden die nur für physische TNCs relevanten Felder ausgeblendet: serielle Einstellungen, RF-TX-Sperre/Pacing und LAN-Proxy. Das Senden zu APRS-IS erfordert sowohl eine aktivierte Verbindung als auch einen passenden `Packet Routing`-Flow.

Quelle und Ziel APRS-IS sind im `Packet Routing`-Editor nur verfügbar, wenn eine APRSIS-Schnittstelle definiert ist. Ohne diese Schnittstelle kann ein Flow mit APRS-IS-Bezug auch nicht gespeichert oder erneut aktiviert werden.

Das APRSIS-Schnittstellenformular enthält außerdem:

- `Server` und `Port` — die APRS-IS-Serveradresse, standardmäßig `rotate.aprs2.net:14580`.
- `Login-Rufzeichen / Rufzeichen-SSID` — kann leer bleiben, um die Identität aus `Meine Station` zu verwenden.
- `Passcode` — kann leer bleiben, damit APRSBox den standardmäßigen APRS-IS-Passcode aus dem Login-Rufzeichen ableitet.
- `APRS-IS-Empfangsfilter` — steuert den vom Server empfangenen Verkehr, beschränkt jedoch nicht die von `Packet Routing` gesendeten Frames.

Unter dem APRSIS-Formular zeigen der aktuelle Verbindungsstatus und die aufklappbare Diagnose aktive Flows, den letzten Fehler und TX-Zähler. Ein APRS-IS-Passcode ist kein Kontopasswort, sondern der aus dem Rufzeichen abgeleitete Standardcode.

## iGate-Routing und APRS-IS-Sicherheit

- `Receiver RF -> TX APRS-IS` erstellt den klassischen iGate-Uplink vom Funkkanal zu APRS-IS.
- `Local TX -> TX APRS-IS` sendet von APRSBox erzeugte Frames an APRS-IS, darunter Beacon, Status, Wetter, Objekte, Items, Bulletins und Nachrichten.

Beide Modi benötigen ein verifiziertes APRS-IS-Login. `pass -1` kennzeichnet einen nicht verifizierten, reinen Empfangsclient und erlaubt nicht das Senden von über RF empfangenen Frames. Für RF-Uplinks verwendet APRSBox `qAO`, wenn das empfangende TNC keinen nutzbaren TX-Rückweg besitzt, oder `qAR`, wenn das TNC TX erlaubt und ein aktiver Flow `APRS-IS -> RF` den Nachrichtenrückweg bereitstellt. Lokal erzeugte Frames verwenden `TCPIP*`.

Das Ziel `TX APRS-IS` besitzt einen System-Sicherheitsfilter, der unter anderem Frames mit `TCPIP` / `TCPXX`, `NOGATE` / `RFONLY` sowie fehlerhafter Third-Party-Kapselung verwirft. Details zum Aufbau der Flows enthält [Packet Routing](packet_routing.de.md).

## Expose Port

`Expose Port` stellt die TNC-Verbindung über APRSBox als TCP-Port für LAN-Clients bereit. APRSBox leitet Frames zwischen physischem TNC und Clients weiter.

- `Allow TX from remote clients` erlaubt LAN-Clients das Senden von Frames an den TNC. Wenn deaktiviert, können Clients nur empfangen.
- `Bind Address` definiert die Listen-Adresse. `0.0.0.0` bedeutet alle Netzwerkinterfaces.
- `Port` ist der von APRSBox bereitgestellte TCP-Port. Bis zu 3 gleichzeitige Clients werden unterstützt.
- `Whitelist` beschränkt den Zugriff auf IPv4-Adressen oder CIDR-Netze. Ein Eintrag pro Zeile; Kommas werden ebenfalls akzeptiert.

Aktiviere Remote-TX nicht in einem nicht vertrauenswürdigen Netzwerk. Wenn du den Port über die lokale Maschine hinaus bereitstellst, konfiguriere eine Whitelist.

## Wann mehrere Schnittstellen sinnvoll sind

Mehrere aktive Schnittstellen können parallel laufen. Empfangener Traffic wird pro Schnittstelle behandelt, während Funksendungen von der Auswahl in der jeweiligen Ansicht abhängen. Über APRS-IS empfangener Traffic ist im Verlauf, in Stationsdetails und auf der Karte sichtbar, wird aber aus allen APRSBox-Statistiken ausgeschlossen.

Wenn du nur Eingangsdaten von OpenWebRX brauchst, nutze `OpenWebRX MQTT (RX only)`. Wenn du vollständiges Funk-RX/TX brauchst, nutze `TCP` oder `SERIALL`. Für Empfang und/oder Senden über das APRS-IS-Netz nutze `APRS-IS (RX/TX)` und die passenden `Packet Routing`-Flows.
