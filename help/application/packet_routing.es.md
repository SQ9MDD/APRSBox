# Reglas de enrutamiento de paquetes

Esta pantalla muestra las reglas que APRSBox usa para mover paquetes APRS entre entradas y salidas. Una regla tiene una fuente, filtros opcionales y un destino.

Las reglas se evaluan de arriba hacia abajo. El orden de la lista importa cuando varias reglas describen trafico parecido.

## Para que sirve el enrutamiento

El enrutamiento define que debe hacer APRSBox con un paquete despues de recibirlo por RF o generarlo localmente.

Usos comunes:

- reenviar tramas recibidas por RF hacia APRS-IS,
- hacer digipeating hacia una salida RF,
- enviar tramas generadas localmente por APRSBox hacia APRS-IS,
- registrar trafico sin transmitirlo,
- descartar trafico que no debe continuar.

## Casos habituales

### `RF -> APRS-IS`

Es el caso tipico de iGate. APRSBox recibe una trama por radio y la envia a APRS-IS despues del filtro obligatorio del sistema.

Se usa cuando:

- quieres publicar en APRS-IS trafico escuchado localmente por RF,
- quieres que distintos puertos RF alimenten APRS-IS con reglas separadas,
- quieres separar claramente la recepcion RF de la subida a Internet.

### `RF -> RF`

Es el caso clasico de digipeater. Una trama entra por RF y vuelve a salir por RF despues de pasar los filtros configurados.

Se usa cuando:

- estas construyendo un digi local,
- quieres hacer cross-band o reenvio entre puertos RF,
- quieres repetir solo ciertos tipos de trafico, zonas, rutas o indicativos.

### `Local TX -> APRS-IS`

Este camino es para tramas creadas por APRSBox, como beacon, estado, meteorologia, objetos, items, boletines y mensajes.

Se usa cuando:

- quieres subir a APRS-IS el trafico generado por la aplicacion,
- quieres enviar objetos, boletines o mensajes sin una ruta RF,
- quieres separar la logica de transmision local de la logica del trafico RF entrante.

### `RF -> Black Hole` o `Local TX -> Black Hole`

Es un camino de diagnostico. El paquete pasa por la regla, pero no se transmite mas lejos.

Se usa cuando:

- quieres probar una regla sin riesgo,
- quieres observar como pasan los paquetes por los filtros,
- quieres registrar trafico sin transmitirlo.

### `RF -> Action Drop`

Es un camino de bloqueo. La regla termina con un descarte intencional.

Se usa cuando:

- quieres cortar trafico no deseado en una regla explicita,
- quieres una ruta de rechazo separada en lugar de mezclar toda la logica en una sola regla,
- quieres que la politica de filtrado sea facil de leer.

## Fuentes y destinos

`Receiver RF` significa paquetes recibidos por un modem de radio configurado.

`Local TX` significa tramas generadas por APRSBox, como beacon, estado, meteorologia, objetos, items, boletines y mensajes.

Los destinos disponibles incluyen `TX RF`, `TX APRS-IS`, `Black Hole` para solo registrar, y `Action Drop` para terminar la regla descartando el paquete.

`Local TX` solo puede dirigirse a APRS-IS o al registro.

## Filtros

Los filtros se ejecutan en orden. Si un filtro rechaza un paquete, los pasos siguientes no se ejecutan.

Filtros utiles:

- `Strict Filter` rechaza `TCPIP`, `TCPXX`, `NOGATE`, `RFONLY` y tramas third-party invalidas.
- `Path rule and DIGI guard` maneja la ruta digi y bloquea tramas que esta estacion no debe repetir.
- `Duplicate Filter` aplica una ventana corta de viscous-delay.
- `Direct Only` acepta solo paquetes escuchados directamente.
- Los filtros de indicativo, digi, tipo de paquete, icono, distancia y limite de tasa reducen el trafico antes de transmitir.

Para una referencia detallada bloque por bloque, consulta:

[Referencia detallada de bloques de routing](packet_routing_flow.es.md)

## Protecciones del sistema

Las reglas `TX APRS-IS` estan restringidas a un `Strict Filter` obligatorio.

Las reglas `TX RF` requieren un paso activo `Path rule and DIGI guard`.

Solo una regla activa puede manejar la misma pareja fuente-destino al mismo tiempo.
