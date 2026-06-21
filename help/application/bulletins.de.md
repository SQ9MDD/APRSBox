# APRS-Bulletins und Ankündigungen

Dieser Bildschirm wird verwendet, um kurze APRS-Rundspruch-Nachrichten im Nachrichtenformat vorzubereiten. Bulletins und Ankündigungen sind keine privaten Nachrichten an eine einzelne Station.
Sie richten sich an mehrere Empfänger, etwa lokale Operatoren, Veranstaltungsteilnehmer, eine Vereinsgruppe oder Stationen in Reichweite.

## 1. Theorie

### Was ein APRS-Bulletin ist

Ein APRS-Bulletin ist eine kurze Textnachricht, die an mehrere Empfänger gesendet wird. Es kann Vereins-, Organisations-, technische, Wetter- oder andere Informationen enthalten, die während der lokalen Radioaktivität nützlich sind.

Ein Bulletin ist kein Textgespräch und sollte keine lange Beschreibung, eine Website oder eine private Nachricht an eine bestimmte Person ersetzen. Sein Zweck besteht darin, nützliche Informationen schnell weiterzugeben, wenn diese Informationen hier und jetzt wichtig sind.

Gute Verwendungsmöglichkeiten für Bulletins:

- Informationen über ein lokales Netz oder Treffen,
- eine Nachricht für Veranstaltungsteilnehmer,
- Vereinsinformationen,
- eine kurze Mitteilung über Repeater, digi, iGate oder den Betrieb der Feldstation,
- eine lokale technische Nachricht,
- eine kurze Wetter- oder Organisationsmitteilung.

Beispiele für gute Nachrichten:

```text
NET 19:00 local Repeater SR5XXX
HAMFEST parking on 145.550
WX alert: strong wind until 18 UTC
APRS test 12:00-14:00 local area
```

### Was eine APRS-Ankündigung ist

Eine Ankündigung ähnelt einem Bulletin, dient jedoch in der Regel eher der Information oder dient als Hinweis. In der Praxis kann es verwendet werden, um kurze Mitteilungen über Aktivitäten, Veranstaltungen oder wichtige lokale Informationen zu veröffentlichen.

Für den Benutzer ist der wichtigste Unterschied einfach:

```text
Bulletin        kurze Rundspruch-Information, meist mit einer Ziffer markiert
Ankündigung     kurze Information, mit einem Buchstaben gekennzeichnet
```

### Bulletin im Vergleich zu einer normalen APRS-Nachricht

Eine normale APRS-Nachricht ist an ein bestimmtes Stationsrufzeichen adressiert. Ein Bulletin oder eine Ankündigung ist an einen speziellen Empfänger vom Typ `BLN` gerichtet, sodass APRS-Clients es als Rundspruch-Nachricht erkennen können.

Ein Bulletin:

- ist keine private Nachricht,
- ist kein typischer Chat,
- sollte keine Antwort von einer bestimmten Station erfordern,
- sollte kurz und verständlich sein, ohne zusätzlichen Kontext.

## 2. APRS-Protokollkompatibilität

Bulletins und Ankündigungen werden als APRS-Frames im Nachrichtenformat gesendet. Sie unterscheiden sich von einer normalen Nachricht dadurch, dass das Adressatenfeld eine spezielle Kennung enthält, die mit `BLN` beginnt.

Typische Identifikatoren:

```text
BLN0       general bulletin number 0
BLN1       general bulletin number 1
BLNA       announcement marked with letter A
BLN0GRP    group bulletin, example with short group GRP
```

Das Adressatenfeld APRS hat eine begrenzte Länge, daher müssen der Code und der Gruppenname kurz bleiben. Es lohnt sich nicht, lange oder nicht standardmäßige Bezeichner zu erstellen.
da ältere Radios und einfache APRS-Clients diese möglicherweise nicht wie erwartet anzeigen.

Aus Gründen der Kompatibilität und Lesbarkeit verwenden Sie am besten:

```text
0-9    for general and group bulletins
A-Z    for announcements
```

Der Nachrichtentext sollte in die Grenzen einer kurzen APRS-Nachricht passen. Eine sichere Vorgehensweise besteht darin, maximal 67 Zeichen einzuhalten und druckbare ASCII zu verwenden.
Es lohnt sich, nationale Zeichen, Sonderzeichen und Formatierungen zu vermeiden, da einige Radios und ältere APRS-Clients diese möglicherweise nicht korrekt anzeigen.

## 3. Regeln für eine gute Nutzung

APRS wurde als System für aktuelle Betreiberinformationen konzipiert. Ein gutes Bulletin sollte die Frage beantworten: Sind diese Informationen für die Sender nützlich, die sie hier und jetzt empfangen?

Best Practices:

- schreibe kurz und konkret,
- Weitergabe von Informationen, die lokal oder betrieblich nützlich sind,
- eine einfache Sprache verwenden,
- Vermeiden Sie lange Beschreibungen,
- Vermeiden Sie es, zu oft zu wiederholen,
- Verwenden Sie Bulletins nicht als Werbung ohne Wert für lokale Operatoren.
- Senden Sie keine Inhalte, die besser auf einer Website, in E-Mails oder in einem Messenger platziert werden könnten.

Ein gutes APRS-Bulletin ist eine Kurznachricht mit aktuellem Wert für lokale Operatoren und kein Text, der nur an das Netzwerk gesendet wird, weil dies technisch möglich ist.

### Sendeintervall

Das Intervall sollte sinnvoll gewählt werden. Ein Bulletin soll den Nutzer an nützliche Informationen erinnern, aber den Funkkanal nicht ständig belegen.

Vermeiden Sie bei lokalen HF-Übertragungen sehr kurze Lücken. Wenn die Nachricht nicht dringend ist, ist es besser, sie seltener zu versenden.
Für Veranstaltungen und Feldaktivitäten besteht ein guter Ansatz darin, ein Aktivitätsfenster zu definieren und ein moderates Wiederholungsintervall zu verwenden.

### APRS-Pfad

Bei einfachen lokalen Übertragungen ist es am sichersten, den Pfad leer zu lassen oder Einstellungen zu verwenden, die der lokalen Praxis entsprechen.
Ein zu breiter Pfad kann den Funkkanal unnötig belasten und eine lokale Nachricht weiter als nötig verbreiten.

Wenn die Nachricht nur für APRS-IS bestimmt ist, spielt der HF-Pfad normalerweise keine Rolle.

### Gruppen

Eine Gruppe macht Sinn, wenn die Nachricht für eine bestimmte Gemeinde, Veranstaltung, einen Verein oder eine lokale Aktivität gedacht ist. Der Gruppenname sollte kurz, stabil und leicht zu erkennen sein.

Gute Gruppennamen:

```text
CLUB
FIELD
ARES
EVENT
SP5
```

Die APRS-Spezifikation besagt, dass eine Gruppen-Bulletin-Adresse aus `BLN`, einer einzelnen einzelnen Bulletin-ID, und einem bis zu 5 Zeichen langen Gruppennamen besteht, der mit Leerzeichen auf 5 Zeichen aufgefüllt ist.

## 4. Umgang mit Formularen

### Typ

Das Feld `Type` wählt die Art des Eintrags aus.

Typische Auswahl:

```text
Allgemeines Bulletin
Gruppenbulletin
Ankündigung
```

Der ausgewählte Typ bestimmt, wie der APRS-Adressat aufgebaut ist und was die unterstützenden Felder bedeuten.

### Code

Das Feld `Code` markiert ein Bulletin oder eine Ankündigung mit einem einzelnen Zeichen.

Empfohlene Verwendung:

```text
0-9    for bulletins
A-Z    for announcements
```

Beispiele:

```text
0    first bulletin
1    second bulletin
A    announcement A
B    announcement B
```

Ändern Sie den Code nicht unnötig, wenn es sich bei der Nachricht um eine Fortsetzung derselben Informationen handelt. Ein stabiler Code erleichtert es den Empfängern, zu erkennen, dass sie eine Aktualisierung desselben Bulletins oder derselben Ankündigung sehen.

### Gruppe

Das Feld `Group` wird hauptsächlich für Gruppenbulletins verwendet. Es hilft dabei, die Bedeutung der Nachricht auf eine bestimmte Zielgruppe oder Aktivität zu beschränken.

Die Gruppe sollte sein:

- kurz,
- lesbar,
- stabil,
- geschrieben mit einfachen ASCII-Zeichen.

Beispiel:

```text
EVENT
CLUB
SP5
```

### Nachrichtentext

Das Feld `Message Text` enthält die eigentliche APRS-Nachricht.

Der beste Nachrichtentext ist kurz, eindeutig und ohne zusätzlichen Kontext verständlich. Denken Sie daran, dass die Nachricht auf einem kleinen Radiobildschirm gelesen werden kann, nicht nur in einer komfortablen Desktop-Anwendung.

Empfehlungen:

- maximal 67 Zeichen,
- druckbare ASCII,
- keine nationalen Charaktere,
- keine langen Sätze,
- keine Formatierung,
- keine unnötigen Dekorationen.

Gutes Beispiel:

```text
NET 19:00 SR5XXX, check-ins welcome
```

Schwächeres Beispiel:

```text
Das heutige Treffen unserer Gruppe findet heute Abend statt. Details stehen auf der Website.
```

### Pfad

Das Feld `Path` definiert den APRS-Pfad, der für die HF-Übertragung verwendet wird.

Für einfache lokale Nachrichten ist es am besten, das Feld leer zu lassen oder nur den lokal akzeptierten Pfad zu verwenden.
Legen Sie keinen breiten Pfad fest, nur um die Botschaft so weit wie möglich zu verbreiten. Ein Bulletin soll dort ankommen, wo es für die Empfänger von Nutzen ist.

### Sendeintervall

Das Feld `Send Interval` definiert, wie oft die Nachricht erneut gesendet werden darf, während sie aktiv ist.

Dieses Feld entscheidet nicht selbst, wann die Nachricht übertragen werden darf. Das Intervall arbeitet mit dem Aktivierungsmodus und dem Zeitplan zusammen.

Beispiel:

```text
Send Interval: 30 minutes
Active from: 10:00 UTC
Active until: 14:00 UTC
```

Dies bedeutet, dass die Nachricht nur im Zeitfenster von 10:00 bis 14:00 Uhr UTC alle 30 Minuten gesendet werden darf.

### Aktivierung

Das Feld `Activation` definiert, wann der Eintrag aktiv ist.

Typische Modi:

```text
Manual        the entry is turned on and off manually
Scheduled     the entry has one defined activity window
Recurring     the entry returns regularly according to a repeating plan
```

### Aktiv von

Das Feld `Active from` definiert den Zeitpunkt, an dem der Eintrag in UTC aktiv wird.

Im geplanten Modus ist dies der Beginn eines Übertragungsfensters. Im wiederkehrenden Modus ist dies der erste Start des gesamten Zyklus.

### Aktiv bis

Das Feld `Active until` definiert den Zeitpunkt, an dem der Eintrag in UTC nicht mehr aktiv ist.

Im geplanten Modus ist dies das Ende eines Übertragungsfensters. Im manuellen Modus kann es als zusätzliche Gültigkeitsgrenze dienen.

### Aktiv für

Das Feld `Active for` definiert, wie lange ein einzelner Zyklus im wiederkehrenden Modus aktiv bleibt.

Beispiel:

```text
Active for: 3 hours
Repeat every: 7 days
```

Das bedeutet, dass die Meldung nach jedem Zyklusstart 3 Stunden lang aktiv bleibt.

### Wiederholen Sie alle

Das Feld `Repeat every` definiert die Lücke zwischen aufeinanderfolgenden Zyklusstarts.

Beispiel:

```text
Repeat every: 1
Repeat unit: week
```

Dies bedeutet einen Zyklus, der einmal pro Woche wiederholt wird.

### Einheit wiederholen

Das Feld `Repeat unit` definiert die von `Repeat every` verwendete Einheit.

Typische Einheiten:

```text
days
weeks
months
years
```

Denken Sie bei Monaten und Jahren daran, dass es sich um Kalendereinheiten handelt. Nicht jeder Monat hat die gleiche Anzahl an Tagen.

## 5. Anwendungsbeispiele

### Allgemeines Bulletin

Verwendung: eine kurze Nachricht an alle Empfänger.

```text
Type: Allgemeines Bulletin
Code: 0
Message Text: NET 19:00 SR5XXX, check-ins welcome
Send Interval: 30 minutes
```

Beispielbedeutung:

```text
Das lokale Netz beginnt um 19:00 auf Repeater SR5XXX.
```

### Gruppenbulletin

Verwendung: eine Nachricht für eine bestimmte Gruppe, ein bestimmtes Ereignis oder eine bestimmte Aktivität.

```text
Type: Gruppenbulletin
Code: 1
Group: EVENT
Message Text: EVENT parking on 145.550 simplex
Send Interval: 20 minutes
```

Beispielbedeutung:

```text
Teilnehmer der Veranstaltung finden dort Informationen zum Parkkanal.
```

### Bekanntmachung

Verwendung: eine kurze Mitteilung oder eine organisatorische Information.

```text
Type: Ankündigung
Code: A
Message Text: HAMFEST gates open 08:00 UTC
Send Interval: 60 minutes
```

Beispielbedeutung:

```text
Die Ankündigung informiert über die Öffnungszeit der Veranstaltung.
```

## 6. Worauf Sie achten sollten

Vermeiden:

- sehr lange Nachrichten,
- Nationalzeichen und Sondersymbole,
- zu oft wiederholen,
- ein breiter Pfad ohne klare Notwendigkeit,
- Meldungen, die nichts mit der örtlichen Betriebssituation zu tun haben,
- Inhalt, der eine normale Nachricht an einen bestimmten Sender sein sollte,
- Inhalte, die an eine Website, eine E-Mail oder einen Messenger weitergeleitet werden sollen.

Denken Sie daran, dass der Funkkanal APRS eine begrenzte Kapazität hat. Jede übermittelte Mitteilung soll für die Empfänger einen Sinn ergeben.

## 7. Kurzreferenz

```text
APRS bulletin       short broadcast message
APRS announcement   short notice or information
BLN                 special address used for bulletins and announcements
0-9                 recommended bulletin codes
A-Z                 recommended announcement codes
Group               short identifier of recipients or activity
67 characters       safe limit for message text
ASCII               safest character set
Interval            how often to repeat an active message
Activation          when the message may be transmitted
```

## 8. Hauptregel

Ein APRS-Bulletin sollte kurz, lokal nützlich und auf einfachen Geräten leicht lesbar sein.
Wenn eine Nachricht eine lange Erklärung, viele Sätze oder Links zu zusätzlichen Informationen erfordert, ist sie wahrscheinlich nicht als APRS-Bulletin geeignet.
