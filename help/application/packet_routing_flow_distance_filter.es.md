# Filtro de distancia

Este filtro deja pasar una trama solo cuando la posicion decodificada cae dentro de al menos una zona configurada.

Como funciona:

- se pueden definir de 1 a 3 zonas,
- cada zona tiene centro y radio,
- las zonas se evalúan con logica OR,
- si no hay ninguna zona valida, el filtro se omite,
- si la trama no tiene posicion decodificable, el filtro se omite,
- solo una trama con posicion fuera de todas las zonas se rechaza.

Usalo cuando:

- quieres limitar trafico a un area geografica,
- quieres routing local segun zona de cobertura o de evento.

## Navegacion

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
