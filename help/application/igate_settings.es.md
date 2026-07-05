# Ajustes iGate

Esta pantalla configura la conexión de APRSBox con APRS-IS y muestra el estado de ejecución del uplink. No es un interruptor separado para activar iGate. El tráfico llega a APRS-IS mediante flujos activos de `Packet Routing` que terminan en el destino `TX APRS-IS`.

## Cuándo usarlo

- `Receptor RF -> TX APRS-IS` crea el uplink iGate clásico desde la radio hacia APRS-IS.
- `TX local -> TX APRS-IS` envía a APRS-IS tramas generadas localmente por APRSBox, como baliza, estado, meteorología, objetos, items, boletines y mensajes.

La guía detallada para crear estas rutas está aquí:

[Packet Routing](packet_routing.es.md)

## Campos de configuración

- `Server` es el host APRS-IS. El valor predeterminado es `rotate.aprs2.net`.
- `Port` es el puerto del servidor APRS-IS. Un valor habitual es `14580`.
- `Login callsign / callsign-SSID` puede dejarse vacío. Entonces la aplicación usa el indicativo de la estación local.
- `Passcode` puede dejarse vacío. Entonces la aplicación calcula el passcode APRS-IS estándar para el indicativo de login.

El passcode APRS-IS no es una contraseña de cuenta. Es el código estándar calculado desde el indicativo y requerido por los servidores APRS-IS para enviar tramas.

## Diagnóstico

El panel de estado muestra la conexión actual, login, flujos APRSIS activos, último error y contadores de tramas enviadas o descartadas antes del TX APRS-IS.

El destino `TX APRS-IS` usa un filtro de seguridad del sistema. Rechaza, entre otras cosas, tramas con tokens `TCPIP` / `TCPXX`, tramas con `NOGATE` / `RFONLY` y encapsulación third-party incorrecta.
