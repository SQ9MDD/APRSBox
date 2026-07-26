# Regla de entrega de mensajes APRS-IS

Esta regla obligatoria del sistema proporciona la ruta de mensajes de un iGate bidireccional en el flujo restringido `APRS-IS → RF`. Se ejecuta después de la seguridad de entrada y antes de la regla de indicativo y radio.

## Tráfico que puede reenviar

La regla puede autorizar mensajes, `ack`, `rej` y consultas dirigidas a un indicativo local exacto con SSID, además del siguiente paquete de posición del remitente cuyo mensaje se haya puesto correctamente en la cola de RF.

Los boletines, mensajes de grupo, definiciones de telemetría y consultas generales no forman parte del tráfico de mensajes obligatorio.

## Destinatario local

El destinatario debe haberse escuchado directamente durante los últimos 60 minutos por cualquier interfaz TNC activa en la que se permita transmitir por RF. El SSID forma parte de la coincidencia. El mensaje se rechaza si el destinatario no fue escuchado directamente en ese plazo, la interfaz está desactivada o tiene bloqueada la transmisión RF, el destinatario fue visto recientemente como estación de Internet o el remitente fue escuchado en la misma cobertura RF local.

## Configuración

Esta regla del sistema no tiene ajustes. APRSBox utiliza automáticamente todas las interfaces TNC activas capaces de transmitir y sin bloqueo de transmisión RF. Las interfaces desactivadas, solo de recepción o con TX bloqueado no se tienen en cuenta.

Un mensaje autorizado omite la regla de indicativo y radio, pero no la seguridad TX, el control de duplicados, los límites de velocidad, la encapsulación de terceros ni el límite AX.25.

[Regla APRS-IS de indicativo y radio](packet_routing_flow_aprsis_callsign_radius_rule.es.md)

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
