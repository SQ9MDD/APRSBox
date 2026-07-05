# Filtro de limite de ritmo

Este filtro no cuenta paquetes por minuto. Es una compuerta temporal simple basada en el indicativo de origen.

Formato de regla:

```text
CALL_OR_PATTERN - LIMIT
```

Ejemplos:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

Como funciona:

- actua solo sobre el indicativo de origen,
- la primera trama que coincide siempre pasa,
- la siguiente trama de la misma fuente bajo la misma regla coincidente se bloquea hasta que expire el limite,
- el temporizador solo se actualiza con tramas que realmente pasaron,
- si ninguna regla coincide con la fuente, el filtro no bloquea nada y la trama sigue.

Como se comparan los patrones:

- `SQ9MDD-7` sin wildcard coincide solo con ese SSID exacto,
- `SQ9MDD` sin wildcard y sin SSID coincide con ese indicativo con cualquier SSID,
- `SQ*` funciona como wildcard,
- si coinciden varias reglas, runtime elige la mas especifica; en empate gana la linea anterior.

Limites del formato:

- `LIMIT` puede escribirse como `30`, `30s` o `30S`,
- el rango permitido es de 5 a 300 segundos,
- el paso es de 5 segundos.

Usalo cuando:

- estaciones muy activas generan demasiado trafico,
- una ruta RF necesita control suave sin bloquear completamente la fuente.

## Navegacion

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
