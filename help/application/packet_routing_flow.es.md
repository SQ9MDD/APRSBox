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
- `APRS-IS -> RF Guard -> TX RF` - reenvía de forma segura paquetes de red permitidos explícitamente a un TNC físico con política default-deny.
- `... -> Agujero negro` - diagnóstico, pruebas y validación de reglas sin reenvío.

## Cómo construir una regla

1. Elige la fuente.
2. Elige el destino.
3. Añade solo los bloques necesarios para ese camino.
4. Guarda la regla y revisa el registro de ejecución.

## Bloques de fuente

- [Receptor RF](packet_routing_flow_receiver_rf.es.md)
- [TX local](packet_routing_flow_local_tx.es.md)
- [APRS-IS como origen y RF Guard](packet_routing_flow_rf_guard.es.md)

## Bloques de filtros y reglas

- [Filtro estricto](packet_routing_flow_strict_filter.es.md)
- [Regla de trayectoria y protección DIGI](packet_routing_flow_path_rule_and_digi_guard.es.md)
- [Filtro duplicado (retraso viscoso)](packet_routing_flow_duplicate_filter.es.md)
- [Solo directo](packet_routing_flow_direct_only.es.md)
- [Filtro DIGI](packet_routing_flow_digi_filter.es.md)
- [Filtro de indicativo](packet_routing_flow_callsign_filter.es.md)
- [Filtro de tipo de paquete](packet_routing_flow_packet_type_filter.es.md)
- [Filtro de icono](packet_routing_flow_icon_filter.es.md)
- [Filtro de distancia](packet_routing_flow_distance_filter.es.md)
- [Filtro de limite de ritmo](packet_routing_flow_rate_limit_filter.es.md)

## Bloques de destino

- [TX RF](packet_routing_flow_tx_rf.es.md)
- [TX APRS-IS](packet_routing_flow_tx_aprsis.es.md)
- [Agujero negro](packet_routing_flow_black_hole.es.md)

## Notas rápidas

- `TX APRS-IS` requiere el bloque `Filtro estricto`.
- `TX RF` requiere el bloque `Regla de trayectoria y protección DIGI`.
- `TX local` solo puede terminar en `TX APRS-IS` o `Agujero negro`.
- Un origen `APRS-IS` recibe automáticamente el `RF Guard` obligatorio; sin reglas allow no se reenvía ningún paquete.
