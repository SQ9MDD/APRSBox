# Configuración de alarmas APRS

Este panel configura el canal de solo recepción para alarmas enviadas como mensajes de grupo APRS. Determina qué destinos se tratan como alarmas, qué eventos llegan a la lista de Alertas, cuáles pueden abrir una ventana de emergencia y qué grupos se añaden al filtro de recepción APRS-IS.

## Configuración rápida

- Active `Alarmas APRS`.
- Introduzca destinos separados por comas, por ejemplo `PL-WARN, NWS-WARN`.
- Ajuste los umbrales `Alertas` y `Ventana de alerta` de cada categoría.
- Guarde y compruebe los grupos RF efectivos y el filtro APRS-IS automático mostrados bajo el formulario.

Un nombre de grupo puede contener entre 1 y 9 letras mayúsculas, dígitos o guiones. Las minúsculas se convierten, se eliminan duplicados y se rechazan las direcciones de boletín `BLN...`.

## Procesamiento de una trama recibida

- Solo entra en esta ruta un mensaje APRS dirigido a un grupo de alarma activado y configurado.
- El nombre del evento selecciona una categoría como tornado, tormenta, inundación, viento, calor u `Otro / desconocido`.
- Los dígitos finales del código de evento se interpretan como gravedad.
- `Alertas` decide si la trama crea o actualiza un registro en la lista de Alertas.
- `Ventana de alerta` decide de forma independiente si la primera trama de esa alarma puede abrir la ventana global.
- La capa de mapa tiene su propio control de visibilidad en la página Mapa y requiere una geometría local coincidente para cada código de área.

Un umbral numérico acepta ese nivel y los superiores. `Desactivado` inhabilita la categoría en esa columna. Una gravedad desconocida se conserva si la categoría está activa para no descartar silenciosamente formatos nuevos o dañados; no tiene clasificación amarilla, naranja o roja y se muestra en gris cuando existe geometría.

## Formatos de aviso admitidos

- [Guía detallada de CAWF](settings_alarms_cawf.es.md) — perfiles nacionales como `PL-WARN`, alarmas multipartes, geometría, ciclo de vida y confianza.
- [Guía detallada de NWS-WARN](settings_alarms_nws_warn.es.md) — formato estadounidense por condados, códigos UGC, cobertura cartográfica y límites de APRSBox.
- [Lista de Alertas, silencio y eliminación](alerts.es.md) — acciones del operador después de aceptar una alarma.

## Límites importantes

- El interruptor afecta a los grupos de alarma configurados. Las tramas nativas APRS emergency y Mic-E emergency utilizan el sistema compartido de Alertas de forma independiente.
- Los mensajes de grupos de alarma no aparecen en conversaciones normales, no activan los transportes habituales de notificación de mensajes y nunca reciben un APRS ACK.
- APRSBox no autentica actualmente a los emisores ni mantiene una lista de remitentes de confianza por grupo. Recibir una trama por APRS-IS no demuestra que sea oficial.
- Una caducidad `DDHHMMz` ausente o inválida no puede resolverse automáticamente. Ese registro puede seguir activo hasta que sea sustituido o eliminado manualmente.
