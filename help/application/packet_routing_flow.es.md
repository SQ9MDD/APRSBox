# Referencia detallada de bloques de routing

Este documento describe los bloques disponibles en el editor de una sola regla de routing. Cada regla tiene una fuente, cero o mas filtros en medio y un destino.

## Como se evalua una regla

Los paquetes avanzan de arriba hacia abajo.

1. El paquete entra por la fuente.
2. Pasa por cada bloque de filtro o regla en orden.
3. Si algun bloque rechaza el paquete, los pasos siguientes ya no se ejecutan.
4. Si el paquete pasa todos los pasos, llega al destino.

## Bloques de fuente

### `Receiver RF`

Entrada para paquetes recibidos por un modem de radio concreto.

Usalo cuando la regla deba manejar trafico que llega desde RF.

### `Local TX`

Entrada para tramas generadas localmente por APRSBox.

Incluye:

- beacons,
- estado,
- meteorologia,
- objetos,
- items,
- boletines,
- mensajes.

No incluye trafico recibido por RF ni trafico ya digipeatado.

## Bloques de filtros y reglas

### `Strict Filter`

Es el filtro de seguridad del sistema para reglas con salida a APRS-IS.

Hace lo siguiente:

- rechaza paquetes con `TCPIP` o `TCPXX`,
- rechaza paquetes marcados `NOGATE` o `RFONLY`,
- valida tramas third-party,
- bloquea rutas internas o externas malformadas.

Usalo:

- como guardia obligatorio para `TX APRS-IS`,
- para mantener seguro y correcto el envio a APRS-IS.

### `Path rule and DIGI guard`

Es el bloque central para reglas `RF -> RF`.

Hace lo siguiente:

- analiza la ruta digi,
- decide si la estacion local todavia debe repetir el paquete,
- bloquea mensajes y consultas dirigidos localmente,
- bloquea trafico third-party que no debe repetirse,
- bloquea tramas ya repetidas por esta misma estacion.

Usalo:

- en cualquier regla de retransmision RF,
- como bloque principal de comportamiento digi y control de ruta.

### `Duplicate Filter (viscous-delay)`

Este bloque abre una ventana corta de escucha y comprueba si otro digi ya repitio la misma trama.

Si la respuesta es si:

- el paquete se descarta.

Si no:

- el paquete continua cuando termina la ventana.

Usalo:

- en rutas digi RF donde importa reducir duplicados,
- como primer filtro en una regla RF tipica.

### `Direct Only`

Deja pasar solo paquetes escuchados directamente, sin ningun hop digi ya consumido.

Usalo:

- cuando la regla debe reaccionar solo a estaciones escuchadas localmente,
- cuando quieres ignorar trafico ya repetido.

### `DIGI Filter`

Comprueba que digipeaters ya aparecen en la ruta consumida.

Modos:

- `allow` deja pasar solo paquetes coincidentes,
- `deny` rechaza paquetes coincidentes.

Usalo:

- para aceptar trafico solo de ciertas cadenas digi,
- para bloquear paquetes que ya pasaron por digis concretos.

### `Callsign Filter`

Comprueba el indicativo de origen del paquete.

Modos:

- `allow` deja pasar solo los indicativos coincidentes,
- `deny` rechaza los indicativos coincidentes.

Usalo:

- para listas blancas y listas negras,
- para separar trafico de club, servicio o pruebas.

### `Packet Type Filter`

Trabaja sobre los grupos principales de paquetes APRS.

Grupos soportados:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Usalo:

- para tratar distinto posiciones, mensajes, meteorologia u objetos,
- para limitar una regla a una sola clase de trafico.

### `Icon Filter`

Comprueba el simbolo APRS.

Usalo:

- para dejar pasar o bloquear ciertos tipos de icono,
- para crear rutas separadas para trafico movil, meteorologico o de objetos especiales.

### `Distance Filter`

Deja pasar un paquete solo cuando su posicion decodificada cae dentro de al menos una zona configurada.

Propiedades:

- se pueden definir de 1 a 3 zonas,
- cada zona tiene centro y radio,
- los paquetes sin posicion decodificable no se rechazan automaticamente por este filtro.

Usalo:

- para limitar trafico a un area geografica concreta,
- para crear zonas locales de digi o gate.

### `Rate Limit Filter`

Limita con que frecuencia pueden continuar los paquetes de un indicativo o patron de indicativo.

Hace lo siguiente:

- mide el tiempo desde el ultimo paquete aceptado para cada regla coincidente,
- bloquea el siguiente paquete si llega antes de que expire el limite configurado.

Usalo:

- para calmar estaciones muy activas,
- para proteger RF de rafagas repetidas,
- para reducir trafico sin bloquear completamente una fuente.

## Bloques de destino

### `TX RF`

Envia el paquete por el modem de radio seleccionado.

Usalo para:

- rutas digi locales,
- cross-band,
- reenvio entre puertos RF.

### `TX APRS-IS`

Envia el paquete a APRS-IS.

Usalo para:

- subida de iGate,
- envio a APRS-IS de trafico generado localmente por la aplicacion.

Este destino esta restringido por el sistema al `Strict Filter` obligatorio.

### `Black Hole`

Registra la ejecucion sin reenviar el paquete mas lejos.

Usalo para:

- diagnostico,
- pruebas,
- observacion del comportamiento de filtros.

## Restricciones del editor

- Una regla siempre tiene una fuente y un destino.
- `Local TX` solo puede llevar a `TX APRS-IS` o `Black Hole`.
- `TX APRS-IS` siempre mantiene el `Strict Filter` obligatorio.
- `TX RF` requiere un `Path rule and DIGI guard` activo.
- `Duplicate Filter` puede aparecer solo una vez.
- `Distance Filter` puede aparecer solo una vez.
- `Rate Limit Filter` esta pensado para flujos que terminan en `TX RF`.

## Buenas practicas

- Elige primero fuente y destino, y despues anade filtros.
- Para `RF -> RF`, piensa antes en proteger el canal que en ampliar cobertura.
- Para `RF -> APRS-IS`, asegurate de que solo llegue al lado de Internet el trafico apropiado.
- Empieza las pruebas con `Black Hole` cuando quieras verificar la logica sin transmitir.
- Despues de guardar, usa el log de ejecucion para ver exactamente en que paso el paquete paso o fue rechazado.
