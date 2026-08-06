# Referencia de la regla Packet Flow

Esta página de ayuda es una guía corta sobre para qué sirve el editor `Packet Flow` y cuándo conviene usar los caminos típicos. La descripción detallada de cada bloque está enlazada más abajo.

## Qué hace esta pantalla

Una regla de enrutamiento le dice a APRSBox qué hacer con un paquete después de recibirlo o generarlo localmente.

Cada regla tiene una fuente, cero o más bloques intermedios y un destino final.

Los paquetes siempre avanzan de arriba hacia abajo. Si cualquier bloque rechaza un paquete, el resto de la regla ya no se ejecuta.

## Cuándo usar Packet Flow

- `Receptor RF -> TX APRS-IS` - subida clásica de iGate desde RF hacia APRS-IS.
- `Receptor RF -> TX RF` - camino clásico de digipeater en radio.
- `TX local -> TX APRS-IS` - tramas generadas localmente como balizas, meteo, objetos, items, boletines y mensajes.
- `Origen APRS-IS -> Regla de seguridad de entrada APRS-IS -> Regla APRS-IS de indicativo y radio -> Regla de seguridad TX APRS-IS → RF -> TX RF` - reenvía de forma segura paquetes de red permitidos explícitamente a un TNC físico.
- `... -> Agujero negro` - diagnóstico, pruebas y validación de reglas sin reenvío.

## Cómo construir una regla

1. Elige la fuente.
2. Elige el destino.
3. Añade solo los bloques necesarios para ese camino.
4. Guarda la regla y revisa el registro de ejecución.

El origen y el destino APRS-IS solo aparecen cuando hay una interfaz APRSIS definida en `Interfaces`. Su interruptor `Activar conexión APRS-IS` debe estar activo para que los flows puedan recibir o transmitir datos.

## Bloques de fuente

- [Receptor RF](packet_routing_flow_receiver_rf.es.md)
- [TX local](packet_routing_flow_local_tx.es.md)
- [Reglas de seguridad obligatorias APRS-IS → RF](packet_routing_flow_rf_guard.es.md)

## Bloques de filtros y reglas

- [Regla de seguridad de enlace APRS-IS](packet_routing_flow_strict_filter.es.md)
- [Regla de entrega de mensajes APRS-IS](packet_routing_flow_aprsis_message_delivery_rule.es.md)
- [Regla APRS-IS de indicativo y radio](packet_routing_flow_aprsis_callsign_radius_rule.es.md)
- [Regla de ruta de repetición RF](packet_routing_flow_path_rule_and_digi_guard.es.md)
- [Filtro RF de retardo de duplicados](packet_routing_flow_duplicate_filter.es.md)
- [Filtro de recepción RF directa](packet_routing_flow_direct_only.es.md)
- [Filtro DIGI](packet_routing_flow_digi_filter.es.md)
- [Filtro de indicativo de origen](packet_routing_flow_callsign_filter.es.md)
- [Filtro de tipo de paquete APRS](packet_routing_flow_packet_type_filter.es.md)
- [Filtro de símbolos APRS](packet_routing_flow_icon_filter.es.md)
- [Filtro de zonas de posición](packet_routing_flow_distance_filter.es.md)
- [Filtro de tasa de transmisión](packet_routing_flow_rate_limit_filter.es.md)

## Bloques de destino

- [TX RF](packet_routing_flow_tx_rf.es.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.es.md)
- [Agujero negro](packet_routing_flow_black_hole.es.md)

## Notas rápidas

- `TX APRS-IS` requiere la `Regla de seguridad de enlace APRS-IS`.
- La transmisión RF → RF requiere la `Regla de ruta de repetición RF`.
- `TX local` solo puede terminar en `TX APRS-IS` o `Agujero negro`.
- Un flujo `APRS-IS → RF` contiene exactamente cuatro reglas obligatorias del sistema. No se pueden añadir filtros opcionales. La regla de entrega puede admitir tráfico dirigido a una estación RF local escuchada recientemente; el resto requiere indicativo **y** radio, y una configuración vacía no reenvía otras tramas.
