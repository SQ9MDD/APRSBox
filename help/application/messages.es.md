# Mensajes APRS

Esta pestaña se usa para conversaciones APRS guardadas localmente en la base SQLite. La lista de la izquierda muestra los corresponsales, y el panel de la derecha muestra el hilo seleccionado y el formulario de envío.

## Conversaciones

- `Start new conversation` acepta un indicativo APRS en formato `CALL` o `CALL-SSID`.
- El indicativo base puede tener hasta 6 caracteres, con un SSID opcional `0-15`, por ejemplo `SP9XYZ-7`.
- También se permiten algunos destinos de servicio APRS, como `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` o `CQ`.
- Abrir una conversación marca como leídos los mensajes entrantes de ese hilo.
- El icono `Messages` del menú lateral cambia cuando hay mensajes sin leer.

La fila de conversación también muestra si la estación se escuchó recientemente. El estado verde indica tráfico reciente, el estado de advertencia indica tráfico algo más antiguo, y la ausencia de entrada indica que no hay una trama reciente en la historia local de tráfico.

## Envío

- El texto del mensaje APRS está limitado a `67` caracteres ASCII imprimibles.
- Los caracteres nacionales y de control se bloquean porque el formato clásico de mensaje APRS es un campo ASCII corto.
- El campo `Path` define la ruta RF para la transmisión. Si queda vacío, se usa la ruta predeterminada de la estación desde los ajustes de baliza.
- La ruta se recuerda por conversación y también puede ser usada por los ACK automáticos.

Un mensaje normal recibe un número de mensaje APRS y espera `ACK` o `REJ` de la estación remota.

## Estados

- `Queued` significa que el mensaje espera en la cola outbound.
- `Sent` significa que la trama fue transmitida.
- `Sent X/Y` muestra el número de intento y el límite de intentos de un mensaje numerado.
- `ACK` significa que la estación remota confirmó el mensaje.
- `Rejected (REJ)` significa que la estación remota lo rechazó.
- `No ACK` significa que no se recibió confirmación después de la ventana de reintentos.

Para mensajes normales, APRSBox programa reintentos automáticos en intentos posteriores. Tras agotar los intentos, un mensaje fallido puede enviarse otra vez manualmente con el botón `No ACK`.

## Consultas APRS

Si el texto empieza por `?`, el mensaje se trata como una consulta APRS. Esas tramas se envían sin número de mensaje y no usan la misma ventana automática de ACK/reintento que los mensajes normales.

APRSBox reconoce y responde automáticamente a consultas entrantes:

- `?APRS`,
- `?APRSP`,
- `?APRSS`,
- `?APRSD`,
- `?DX`,
- `?APRSV`,
- `?VER`.

Los mensajes y consultas numerados entrantes se confirman automáticamente con una trama `ack`.
