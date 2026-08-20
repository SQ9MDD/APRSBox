# HTTPS

Dieses Panel stellt die APRSBox-Weboberfläche von HTTP auf HTTPS um und verwaltet die vom Server verwendeten Dateien.

## Dateien vorbereiten

APRSBox benötigt ein zusammengehöriges Paar:

- ein PEM-Serverzertifikat als `aprsbox.crt`,
- einen privaten PEM-Schlüssel als `aprsbox.key`,
- optional eine CA-Kette als `aprsbox-ca-chain.crt`.

Die Dateien können mit den im Formular angegebenen Erweiterungen hochgeladen werden. APRSBox speichert sie unter festen Namen in `/opt/aprsbox/data/ssl`. Zertifikat und privater Schlüssel werden als Paar geprüft, bevor HTTPS aktiviert werden kann.

Die lokale PKI-Erzeugung und der Root-CA-Download sind derzeit deaktiviert. Erstellen Sie das Zertifikat vorerst mit einer externen CA oder einem eigenen PKI-Werkzeug und laden Sie es anschließend in diesem Panel hoch.

## mDNS-Hostname

Wenn der Host einen Namen über mDNS veröffentlicht, kann APRSBox zum Beispiel unter `https://aprsbox.local` erreichbar sein. Dazu muss mDNS auf dem Host laufen und vom Clientgerät unterstützt werden.

Das Zertifikat muss den verwendeten Namen, zum Beispiel `DNS:aprsbox.local`, im Feld Subject Alternative Name (SAN) enthalten. Ein Common Name allein genügt modernen Browsern nicht. Öffentliche Zertifizierungsstellen stellen üblicherweise keine Zertifikate für `.local`-Namen aus. Daher wird meist eine private CA verwendet und deren Root CA auf den Clientgeräten als vertrauenswürdig installiert.

## Zertifikate für IP-Adressen

Wird APRSBox als `https://192.168.1.20` geöffnet, muss genau diese Adresse als IP-Eintrag im SAN stehen, zum Beispiel `IP:192.168.1.20`. Ein Eintrag `DNS:192.168.1.20` ist nicht gleichwertig.

Für eine per DHCP vergebene Adresse empfiehlt sich eine Reservierung oder eine feste Adresse. Ändert sich die Adresse, passt das Zertifikat nicht mehr und muss neu ausgestellt werden. Ein Zertifikat kann mehrere DNS-Namen und IP-Adressen enthalten.

## HTTPS aktivieren

1. Zertifikat und passenden privaten Schlüssel hochladen. Die CA-Kette ist optional.
2. Die grünen Statussymbole prüfen.
3. `HTTPS aktivieren` auswählen.
4. `Speichern und neu starten` auswählen und den Neustart der Dienste abwarten.

Danach lauscht APRSBox auf Port `443`. Der normale HTTP-Server auf Port `8000` ist deaktiviert; Port `80` leitet Anfragen mit Status `308` zu HTTPS um.

Bei einer privaten CA kann der Browser eine Warnung anzeigen, bis deren Root CA auf dem Gerät als vertrauenswürdig installiert wurde.

## Dateien entfernen

Serverzertifikat und privater Schlüssel können bei aktivem HTTPS nicht entfernt werden. Deaktivieren Sie HTTPS zuerst und warten Sie, bis die Oberfläche unter `http://adresse:8000` erreichbar ist. Die CA-Kette kann unabhängig heruntergeladen oder entfernt werden.
