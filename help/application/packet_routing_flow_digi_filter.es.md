# Filtro DIGI

Este filtro no mira toda la ruta ni revisa hops aun no consumidos. Solo analiza los hops ya marcados con `*`, quitando antes esa estrella.

Comportamiento real:

- de `SR5BCD-2*,WIDE1-1` solo ve `SR5BCD-2`,
- de `WIDE1-1` no ve nada, porque todavia no hay hops consumidos,
- los patrones se comparan con los hops consumidos; el wildcard `*` puede usarse en cualquier posicion,
- `allow` deja pasar solo si al menos un hop consumido coincide,
- `deny` rechaza solo si al menos un hop consumido coincide.

Consecuencias practicas:

- una lista `allow` vacia rechaza todo,
- una lista `deny` vacia deja pasar todo,
- `*` en `deny` bloquea toda trama ya digipeateada,
- `*` en `deny` no bloquea tramas realmente directas, porque no hay hop consumido que comparar.

Ejemplos:

- ruta `SR5BCD-2*,WIDE1-1` con patron `SR5BCD*` -> match,
- ruta `SR5ABC*,WIDE1-1` con `deny: *` -> drop,
- ruta `WIDE1-1` con `deny: *` -> pass.

Usalo cuando:

- solo debe pasar trafico que vino por digis concretos,
- quieres excluir trafico ya repetido por estaciones intermedias determinadas.

## Navegacion

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
