# Configuration backup

panelvam APRSBox GUI configuration snapshot UTF-8 `JSON` formatDaq export restore je.

## De' ngaSbogh

Snapshot selected global settings, map sources, TNC APRS-IS interfaces, station WX, routing flows rules je, APRS objects items je, bulletins, band-condition reference stations je ngaS.

Runtime traffic, event logs, message history, user accounts, tables latlh unsupported je ngaSbe'.

File callsignmey, APRS-IS connection De', paths, endpoints, operational configuration latlh je ngaSlaH. De' pegh rur yIpol.

## Export import je

- `Export configuration backup` snapshot current download.
- `Import configuration backup` format version je validate, ghIq supported configuration tables transaction wa'Daq replace.
- Validation pagh database check QaghDI' import rollback.

Import current supported configuration overwrite. File latlh restorepa' state current yIexport. Import Qap pIq APRSBox services yItaghqa'; DockerDaq deployment tool lo'taHvIS container restart pagh recreate.
