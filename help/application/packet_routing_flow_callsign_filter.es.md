# Filtro de indicativo de origen

Este filtro comprueba solo el indicativo de origen. No analiza la ruta, los hops digi ni el destino.

Como funciona:

- sin `*`, la coincidencia es exacta,
- `SQ9MDD` no coincide con `SQ9MDD-4`,
- `*` puede usarse en cualquier posicion,
- `allow` funciona como lista blanca,
- `deny` funciona como lista negra.

Consecuencias practicas:

- una lista `allow` vacia rechaza todo,
- una lista `deny` vacia deja pasar todo.

Ejemplos:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Usalo cuando:

- quieres separar trafico de club, pruebas, servicio u operador,
- quieres bloquear o aislar una fuente conocida.

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
