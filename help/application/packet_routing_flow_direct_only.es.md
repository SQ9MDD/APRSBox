# Filtro de recepción RF directa

Este filtro deja pasar solo paquetes escuchados directamente.

Comportamiento real:

- solo comprueba si la ruta ya contiene algun hop consumido marcado con `*`,
- no le importan los hops aun no consumidos como `WIDE1-1`,
- `...,WIDE1-1:` pasa,
- `...,SR5ABC*,WIDE1-1:` se rechaza.

Usalo cuando:

- la regla debe reaccionar solo a estaciones oidas en directo,
- el trafico ya repetido debe ignorarse,
- quieres revisar por separado la cobertura directa.

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
