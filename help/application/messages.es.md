# Mensajes APRS

Esta pestaña se usa para conversaciones APRS guardadas localmente en la base SQLite. La lista de la izquierda muestra los corresponsales, y el panel de la derecha muestra el hilo seleccionado y el formulario de envío.

## Conversaciones

- `Start new conversation` acepta un indicativo APRS en formato `CALL` o `CALL-SSID`.
- El indicativo base puede tener hasta 6 caracteres, con un SSID opcional `0-15`, por ejemplo `SP9XYZ-7`.
- También se permiten algunos destinos de servicio APRS, como `EMAIL`, `SMSGTE`, `WXBOT`, `WHO-IS`, `QRU` o `CQ`.
- Abrir una conversación marca como leídos los mensajes entrantes de ese hilo.
- El icono `Messages` del menú lateral cambia cuando hay mensajes sin leer.

La fila de conversación también muestra si la estación se escuchó recientemente. El estado verde indica tráfico reciente, el estado de advertencia indica tráfico algo más antiguo, y la ausencia de entrada indica que no hay una trama reciente en la historia local de tráfico.

## Configuración de mensajes

El bloque `Configuración de mensajes` se encuentra debajo del panel de conversaciones:

- `Ruta predeterminada` se usa para conversaciones nuevas, mensajes de grupo y respuestas APRS automáticas.
- `Recibir mensajes para cualquier SSID de mi indicativo` permite mostrar mensajes dirigidos a otros SSID del mismo indicativo base. Solo el `CALL-SSID` configurado exactamente recibe un `ACK` o una respuesta automática.
- `Grupos de destino` define las direcciones compartidas de mensajes que recibe APRSBox.

En el primer uso, mientras todavía no se haya guardado una configuración de grupos, la lista contiene `ALL`, `QST` y `CQ`. Si el usuario elimina estos valores y guarda el campo vacío, la lista permanece vacía.

Los grupos se introducen en un solo campo y se separan con comas, por ejemplo `CQ, QST, ALL, WAW, BEM`. Se eliminan los espacios alrededor de los nombres, las letras se convierten a mayúsculas y se descartan los duplicados. Cada nombre debe contener entre `1` y `9` caracteres de `A-Z` o `0-9`. Se rechazan entradas vacías, caracteres especiales, espacios internos y direcciones que comiencen por `BLN`.

## Conversaciones de grupo

- Una conversación de grupo solo se crea para un destinatario presente en la lista guardada `Grupos de destino`.
- Un mensaje dirigido a un grupo no definido, como `BEM`, se ignora: no crea conversación, entrada en el historial, estado sin leer, notificación ni `ACK`.
- La clave de la conversación es la dirección del grupo, por ejemplo `WAW`, y no el indicativo del remitente. Los mensajes de varias estaciones aparecen en el mismo hilo cronológico `WAW`.
- El remitente real, por ejemplo `SQ5WLA-9`, se muestra encima de cada burbuja de grupo. Un mensaje propio se etiqueta como `Tú · CALL-SSID`.
- Un mensaje enviado por APRSBox a un grupo se transmite una vez, sin número de mensaje, sin esperar un `ACK` y sin reintentos automáticos.
- APRSBox nunca confirma un mensaje de grupo, aunque el equipo transmisor haya incluido un número de mensaje.
- Eliminar un grupo de la configuración detiene la recepción de mensajes nuevos dirigidos a ese grupo, pero no borra el historial existente.

Un grupo no es una estación, por lo que su hilo no muestra el estado “escuchado recientemente”. Las direcciones de boletines `BLN...` se gestionan por separado y no pueden añadirse como grupos de mensajes normales.

## Envío

- El texto del mensaje APRS está limitado a `67` caracteres ASCII imprimibles.
- Los caracteres nacionales y de control se bloquean porque el formato clásico de mensaje APRS es un campo ASCII corto.
- El campo `Path` define la ruta RF para la transmisión. Si queda vacío, se usa la `Ruta predeterminada` de la configuración de mensajes.
- La ruta se recuerda por conversación y también puede ser usada por los ACK automáticos.

Un mensaje normal de una conversación directa recibe un número de mensaje APRS y espera `ACK` o `REJ` de la estación remota. Los mensajes de grupo siguen las reglas sin ACK ni reintentos descritas anteriormente.

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

Los mensajes y consultas numerados entrantes solo se confirman automáticamente con una trama `ack` cuando están dirigidos exactamente al `CALL-SSID` local configurado. Los mensajes de grupo y los dirigidos a otro SSID del indicativo local no se confirman ni generan respuestas automáticas.
