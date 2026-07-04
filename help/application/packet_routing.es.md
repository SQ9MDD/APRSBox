# Reglas de enrutamiento de paquetes

Esta pantalla muestra las reglas que APRSBox usa para mover paquetes APRS entre entradas y salidas. Una regla tiene una fuente, filtros opcionales y un destino.

Las reglas se evaluan de arriba hacia abajo. El orden de la lista importa cuando varias reglas describen trafico parecido.

## Usos comunes

- reenviar tramas recibidas por RF hacia APRS-IS,
- hacer digipeating hacia una salida RF,
- enviar tramas generadas localmente por APRSBox hacia APRS-IS,
- registrar trafico sin transmitirlo,
- descartar trafico que no debe continuar.

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

## Protecciones del sistema

Las reglas `TX APRS-IS` estan restringidas a un `Strict Filter` obligatorio.

Las reglas `TX RF` requieren un paso activo `Path rule and DIGI guard`.

Solo una regla activa puede manejar la misma pareja fuente-destino al mismo tiempo.
