# Notificaciones

Esta pestaña configura las notificaciones externas enviadas por APRSBox. Las notificaciones funcionan en dos pasos: primero defines un transporte y después activas los tipos de evento que deben enviarse.

## Transportes

Un transporte define adónde APRSBox envía un evento.

- `Webhook` envía el evento como HTTP `POST` con cuerpo JSON a la URL configurada.
- `Telegram` envía un mensaje mediante un bot de Telegram al `Chat ID` configurado.
- Durante el envío normal de eventos, solo se usan los transportes marcados como `Enabled`.
- El botón de prueba envía un evento `APRSBox notification test` y guarda el resultado de la prueba del transporte.

Para webhooks puedes configurar `Secret header name` y `Secret token`. Si ambos campos están completos, APRSBox añade ese encabezado HTTP a la petición.

`Timeout` se cuenta en segundos. El rango permitido es de `1` a `60`, y el valor predeterminado es `5`.

Al editar un transporte existente, dejar vacío un campo secreto conserva el secreto actual sin cambios.

## Ajustes de notificaciones

- `Enable APRS message notifications` activa las notificaciones de mensajes APRS entrantes.
- `Include message content` controla si el texto del mensaje APRS se incluye en la notificación.
- `Enable radar notifications` activa las reglas de radar de estaciones.
- `Ignored radar patterns` excluye estaciones del procesamiento del radar. Los patrones pueden separarse con comas o saltos de línea. Se admite el comodín `*`.

Desactivar las notificaciones de radar borra el estado recordado de bloqueo de repetición y el log de eventos del radar.

## Reglas de radar

Una regla de radar detecta estaciones que coinciden con un patrón de indicativo y un límite opcional de distancia desde `My Station`.

- `Radar rule` es un indicativo o patrón de indicativo, por ejemplo `SQ6ODL-*`, `SR*` o `*`.
- `Distance (m)` es la distancia máxima desde las coordenadas de la estación local.
- El valor `0` significa que no hay límite de distancia.
- Si la distancia es mayor que `0`, una estación sin coordenadas conocidas no cumplirá la regla.

El radar envía una notificación solo cuando una estación entra en el rango de la regla. Mientras la estación permanece dentro del rango, las notificaciones repetidas se bloquean. El bloqueo se elimina solo cuando la estación sale del rango o su posición expira de los datos visibles.

La estación local y la estación meteorológica activa de APRSBox se omiten automáticamente.

## Log de eventos del radar

El log muestra cambios recientes del estado del radar: notificación enviada, bloqueo de repetición creado y bloqueo eliminado después de que la estación salga del rango.
