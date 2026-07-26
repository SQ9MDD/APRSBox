# Regla APRS-IS de indicativo y radio

Esta regla obligatoria del sistema es la lista explícita de permitidos para el tráfico que no es de mensajes en el flujo restringido `APRS-IS → RF`. Aplica denegación predeterminada: un paquete solo continúa cuando tanto su indicativo de origen exacto como su posición decodificada coinciden con la configuración. Los mensajes dirigidos autorizados por la regla de entrega de mensajes anterior omiten esta regla.

## Condiciones

Las condiciones usan `AND`:

1. El origen del paquete coincide exactamente con un indicativo introducido en la lista.
2. La posición del paquete está dentro del radio configurado, medido desde las coordenadas de `My Station`.

Un indicativo coincidente sin una posición coincidente se rechaza. También se rechaza una posición dentro del radio si el indicativo de origen no está en la lista.

## Indicativos de origen

- Introduzca un indicativo por línea.
- La coincidencia no distingue mayúsculas de minúsculas, pero por lo demás es estricta e incluye el SSID.
- `SQ9MDD` solo coincide con `SQ9MDD`.
- `SQ9MDD-1` solo coincide con `SQ9MDD-1`.
- No se admiten comodines.
- El indicativo debe ser una dirección AX.25 válida: de 1 a 6 letras o dígitos con un SSID opcional de `0` a `15`.
- Se pueden configurar como máximo 50 indicativos.

## Radio

La GUI acepta un radio de `0,1` a `1000 km` en pasos de `0,1 km`. La distancia se calcula desde las coordenadas de la estación configuradas en `My Station`, no desde el módem receptor ni desde otro paquete.

El paquete se rechaza cuando:

- no se puede decodificar su posición APRS,
- `My Station` no tiene coordenadas válidas,
- su posición está fuera del radio.

## Configuración vacía o incompleta

La lista de indicativos y el radio deben rellenarse juntos o dejarse ambos vacíos. No se puede guardar una configuración con solo uno de estos campos.

Dejar ambos campos vacíos es válido y crea un flujo solo para mensajes: la regla deniega todo el tráfico ordinario, mientras que los mensajes y la posición asociada del remitente autorizados por la regla de entrega de mensajes siguen omitiéndola.

Use `Borrar indicativos y radio` para vaciar ambos campos a la vez y restaurar este modo.

## Ubicación

La regla se inserta y gestiona automáticamente después de `Regla de entrega de mensajes APRS-IS` y antes de `Regla de seguridad TX APRS-IS → RF`. No se puede eliminar, desactivar, duplicar ni mover. Tampoco se pueden añadir filtros opcionales a este flujo.

## Navegación

[Reglas de seguridad obligatorias APRS-IS → RF](packet_routing_flow_rf_guard.es.md)

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
