# Mi estación

Esta pestaña configura la estación principal de APRSBox: indicativo, beacon de posición, APRS Status separado, símbolo del mapa y envío manual de tramas locales.

## Position Beacon

El beacon de posición es una trama APRS con la posición de la estación local. Lo usan los mapas, otras estaciones y las reglas de enrutamiento `Local TX`.

- `Callsign` es el indicativo principal sin SSID.
- `SSID` selecciona el sufijo del indicativo, por ejemplo `SQ9XYZ-4`.
- `Interface` selecciona el TNC transmisor, todas las interfaces activas o `Internal TX`.
- `Beacon Comment` se incluye en la trama de posición y tiene un límite corto de ASCII imprimible.
- `Beacon at every` define el intervalo automático del beacon o el modo `Proportional Path`.
- `Beacon Path` define la ruta RF, por ejemplo un campo vacío para transmisión local o `WIDE2-1`.
- `Get location` define las coordenadas desde el mapa.
- `Symbol Table`, `Symbol Code` y `Overlay` seleccionan el símbolo APRS mostrado en los mapas.
- `Enable automatic beacon transmission every selected interval` activa el envío periódico del beacon.

`Send beacon` guarda el formulario actual y pone inmediatamente una trama de beacon en la cola.

## Ruta y carga del canal

APRSBox muestra una advertencia cuando la ruta y el intervalo seleccionados pueden crear demasiada carga en el canal RF.

- Ruta vacía, `DIRECT` o sin ruta amplia significa transmisión local.
- Una ruta de un salto normalmente debería usar un intervalo más largo.
- Una ruta de dos saltos, como `WIDE2-2`, requiere más cuidado.
- `Proportional Path` envía tramas locales frecuentes y tramas con ruta completa menos frecuentes para reducir el tráfico del canal.

Si quieres entender como funcionan las rutas APRS en si, consulta:

[Rutas APRS en la practica](../protocoll/aprs_paths.es.md)

Si la aplicación pide confirmación al guardar, ese ajuste puede aumentar significativamente el tráfico RF.

## PHG Generator

El icono de calculadora junto a `Beacon Comment` crea un código `PHG` a partir de potencia, altura de antena, ganancia y dirección de antena. El código generado se inserta al principio del comentario del beacon.

PHG es útil sobre todo para estaciones fijas, repetidores, gateways y digipeaters. Una estación móvil normal normalmente no lo necesita.

## APRS Status

`APRS Status` es una trama separada con identificador de datos `>`. No sustituye el comentario del beacon de posición.

- `Status Text` es el texto de estado y tiene su propio límite de longitud.
- `APRS Status at every` define el intervalo periódico del status.
- `Enable periodic APRS Status transmission` activa el envío automático de status.

`Send status` guarda el formulario actual y pone una trama de status en la cola. Si el status está activado, el texto no puede estar vacío.

## Internal TX

`Internal TX` no transmite directamente por un TNC físico. Las tramas se generan localmente y pueden ser procesadas por reglas de `Packet Routing`, por ejemplo `Local TX -> TX APRS-IS`.

Si no hay una regla activa `Local TX -> TX APRS-IS`, Internal TX se comporta como un agujero negro local: la trama se crea dentro de APRSBox, pero no sale del sistema.

## Station TX Log

El log muestra los trabajos recientes de beacon y status: hora, tipo, estado, interfaz, intentos, error y vista previa de la trama TNC2. Una fila tachada significa que el trabajo se registró, pero la transmisión se omitió, por ejemplo porque el TNC estaba desactivado o bloqueado para TX.
