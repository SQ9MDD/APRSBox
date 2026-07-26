# Filtro de tasa de transmisión

Este filtro no cuenta paquetes por minuto. Es una compuerta temporal que puede limitar por separado cada indicativo de origen coincidente o todos los orígenes globalmente.

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
- los patrones de indicativo normales mantienen un temporizador separado por origen,
- `*` por sí solo es especial: mantiene un único temporizador global compartido por todos los orígenes del filtro,
- la siguiente trama cubierta por el mismo temporizador se bloquea hasta que expire el límite,
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

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
