# Filtro de tipo de paquete APRS

Este filtro trabaja sobre lo que el decodificador APRSBox reconoce como grupo o tipo de paquete APRS.

Selectores mas comunes:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Significado practico:

- `message` tambien cubre ACK/REJ, bulletin y announcement,
- `weather` significa solo tramas weather-only,
- una posicion con datos meteorologicos sigue contando como `position`,
- por compatibilidad, tambien funcionan selectores antiguos como `M`, `S`, `O` y `W`, ademas de otros codigos crudos devueltos por el parser.

Como funciona:

- en modo `allow`, la trama pasa solo si el grupo o tipo decodificado coincide con la lista,
- en modo `deny`, la trama cae solo si el grupo o tipo decodificado coincide con la lista,
- si el parser no puede determinar grupo/tipo, `allow` rechaza y `deny` deja pasar.

Usalo cuando:

- posiciones, objetos, mensajes o meteorologia deben ir por rutas distintas,
- una regla debe limitarse a una sola clase de trafico.

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
