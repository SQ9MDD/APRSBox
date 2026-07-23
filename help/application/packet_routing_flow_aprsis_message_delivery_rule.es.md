# Regla de entrega de mensajes APRS-IS

Esta regla obligatoria del sistema proporciona la ruta de mensajes de un iGate bidireccional en el flujo restringido `APRS-IS → RF`. Se ejecuta después de la seguridad de entrada y antes de la regla de indicativo y radio.

## Tráfico que puede reenviar

La regla puede autorizar mensajes, `ack`, `rej` y consultas dirigidas a un indicativo local exacto con SSID, además del siguiente paquete de posición del remitente cuyo mensaje se haya puesto correctamente en la cola de RF.

Los boletines, mensajes de grupo, definiciones de telemetría y consultas generales no forman parte del tráfico de mensajes obligatorio.

## Destinatario local

El destinatario debe haberse escuchado recientemente por una fuente RF local configurada. El SSID forma parte de la coincidencia. El mensaje se rechaza si el destinatario es demasiado antiguo, necesitó demasiados saltos DIGI consumidos, fue visto recientemente como estación de Internet o el remitente fue escuchado en la misma cobertura RF local.

## Configuración

- **Fuentes locales de escucha RF**: un nombre de interfaz por línea; vacío usa la interfaz RF de destino.
- **Validez de escucha local**: de 5 a 60 minutos; valor predeterminado 60.
- **Máximo de saltos DIGI consumidos**: de 0 a 2; valor predeterminado 0 para recepción directa.

Un mensaje autorizado omite la regla de indicativo y radio, pero no la seguridad TX, el control de duplicados, los límites de velocidad, la encapsulación de terceros ni el límite AX.25.

[Regla APRS-IS de indicativo y radio](packet_routing_flow_aprsis_callsign_radius_rule.es.md)

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
