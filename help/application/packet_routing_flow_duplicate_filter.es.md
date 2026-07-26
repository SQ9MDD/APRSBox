# Filtro RF de retardo de duplicados

Este bloque no deja pasar la trama inmediatamente. La primera trama con una huella dada queda retenida hasta que termine la ventana de escucha.

Comportamiento real:

- la ventana de escucha puede ajustarse entre `2` y `7` segundos,
- la huella se construye con `source callsign + info field`,
- la ruta no participa en la comparacion de duplicados,
- la primera trama espera hasta el final de la ventana,
- si durante esa ventana aparece otra trama con la misma huella, ambas se descartan,
- si no aparece duplicado, la primera trama continua solo al expirar el temporizador.

Consecuencias practicas:

- dos tramas de la misma estacion con el mismo payload pero distinta ruta siguen contando como duplicado,
- es un verdadero viscous-delay: primero espera y despues decide,
- solo puede aparecer una vez y debe ser el primer filtro de un flujo RF.

Usalo cuando:

- varios digis pueden escuchar la misma estacion origen,
- quieres reducir repeticiones innecesarias sin transmitir de inmediato.

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
