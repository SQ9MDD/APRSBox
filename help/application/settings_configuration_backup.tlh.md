# Configuration backup

panelvam APRSBox GUI configuration snapshot UTF-8 `JSON` formatDaq export restore je.

## De' ngaSbogh

Snapshot v2 global settings, message notification settings je, map sources, TNC APRS-IS interfaces, station WX, notification transports radar rules je, routing flows rules je, APRS objects items je, bulletins je ngaS.

Runtime traffic, transport test results, notification radar state, event logs, message history, own APRS alerts, user accounts, tables latlh unsupported je ngaSbe'.

File callsignmey, APRS-IS connection De', paths, endpoints, webhook Telegram tokens je, operational configuration latlh je ngaSlaH. De' pegh rur yIpol.

## Export import je

- `Export configuration backup` snapshot current download.
- `Import configuration backup` format version je validate, ghIq supported configuration tables transaction wa'Daq replace.
- Validation pagh database check QaghDI' import rollback.
- Format v2 neH supported. Release ngo' chenmoHbogh file v1 importlaHbe'.

Import current supported configuration overwrite. File latlh restorepa' state current yIexport. Import Qap pIq APRSBox services yItaghqa'; DockerDaq deployment tool lo'taHvIS container restart pagh recreate.
