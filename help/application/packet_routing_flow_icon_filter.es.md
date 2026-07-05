# Filtro de icono

Este filtro compara exactamente el simbolo APRS en formato `table+code`.

Como funciona:

- la coincidencia es exacta y no usa wildcard,
- compara exactamente el valor de simbolo devuelto por el parser de APRSBox,
- en modo `allow`, si no coincide se rechaza,
- en modo `deny`, si no coincide se deja pasar,
- si el simbolo no puede decodificarse, `allow` rechaza y `deny` deja pasar.

Ejemplos:

- `/>`,
- `\\l`.

Usalo cuando:

- ciertas clases de simbolo deben tener su propia ruta,
- el significado del simbolo importa mas que el tipo de paquete.

## Navegacion

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
