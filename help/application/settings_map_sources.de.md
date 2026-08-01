# Kartenquellen

Dieses Panel verwaltet die Kachelquellen der APRSBox-Karten, ihre Reihenfolge, die Standardquelle und den optionalen lokalen Cache.

## Quellenliste

- Die Pfeile ändern die Reihenfolge im Kartenauswahlfeld.
- Der Stern macht eine aktivierte Quelle zur Standardquelle.
- Der Stift öffnet eine Quelle zur Bearbeitung.
- Der Papierkorb löscht eine Quelle. Die einzige Quelle und die aktuelle Standardquelle können nicht gelöscht werden.
- Der Besen leert lokal gespeicherte Kacheln, ohne die Quellenkonfiguration zu löschen.

## Quellenfelder

- `Name` ist die Bezeichnung in der Kartenauswahl.
- `URL-Vorlage` muss eine übliche Leaflet-Kachel-URL mit `{z}`, `{x}` und `{y}` sein, zum Beispiel `https://server/{z}/{x}/{y}.png`.
- `Namensnennung` enthält den auf der Karte erforderlichen Quellenhinweis.
- `Min. Zoom` und `Max. Zoom` begrenzen den verfügbaren Zoombereich.
- `Notizen` werden für Administratoren bei der Quelle gespeichert.
- `Aktiviert` stellt die Quelle auf Karten bereit.
- `Lokalen Cache/Proxy aktivieren` leitet Kachelanfragen über APRSBox und speichert heruntergeladene Kacheln lokal.
- `Als Standard festlegen` wählt diese Quelle, wenn keine andere Kartenauswahl gespeichert ist.

Hier werden nur übliche Leaflet-Rasterkachelanbieter unterstützt. Prüfen Sie vor der Aktivierung Nutzungsgrenzen, Namensnennung und die Erlaubnis für Proxy-Caching. Ein Ausgangspunkt ist die [Anbieterliste von Switch2OSM](https://switch2osm.org/providers/#Allows-free-usage).
