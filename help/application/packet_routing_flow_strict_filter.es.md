# Regla de seguridad de enlace APRS-IS

Es el bloque de seguridad del sistema para reglas que terminan en `TX APRS-IS`.

Para tramas que llegan desde `Receptor RF`:

- revisa toda la ruta externa,
- rechaza la trama si la ruta contiene `TCPIP`, `TCPXX`, `NOGATE` o `RFONLY`,
- valida la encapsulacion third-party,
- si la third-party es valida, revisa tambien la ruta interna para los mismos tokens bloqueados.

Para `TX local` es mas estricto:

- la trama debe estar marcada en metadatos como trafico APRSBox generado localmente,
- la encapsulacion third-party se rechaza,
- cualquier construccion `q..` en la ruta se rechaza,
- `TCPIP`, `TCPXX`, `NOGATE` y `RFONLY` siguen bloqueados.

Notas importantes:

- con `TX APRS-IS` esta regla es obligatoria,
- no sustituye la logica digi RF,
- si falla el parseo TNC2, la trama se rechaza.

Casos tipicos:

- `Receptor RF -> Regla de seguridad de enlace APRS-IS -> TX APRS-IS`,
- `TX local -> Regla de seguridad de enlace APRS-IS -> TX APRS-IS`.

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
