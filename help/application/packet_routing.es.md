# Reglas de enrutamiento de paquetes

Esta pantalla muestra la lista de reglas que controlan el flujo de paquetes APRS dentro de APRSBox.

En este nivel gestionas principalmente:

- que reglas existen,
- el orden de las reglas,
- cuales estan activas,
- que regla quieres abrir para editar.

## Para que sirve esta pestana

La pestana `Packet Routing` sirve para gestionar la logica del trafico entre las entradas y salidas de APRSBox.

Usos mas comunes:

- reenviar paquetes desde `Receptor RF` hacia `TX APRS-IS`,
- construir reglas de digipeater como `Receptor RF -> TX RF`,
- enrutar trafico generado localmente con `TX local -> TX APRS-IS`,
- crear rutas de diagnostico que terminan en `Agujero negro`,
- separar varias entradas RF en distintos escenarios de routing.

## Como leer la lista de reglas

Cada fila muestra:

- el orden de la regla,
- el nombre y la descripcion,
- la fuente de entrada,
- el destino final,
- el estado activo o inactivo.

El orden de las reglas importa a nivel operativo, por eso conviene mantener la lista clara.

## Escenarios tipicos

### `Receptor RF -> TX APRS-IS`

Se usa cuando el trafico RF recibido localmente debe reenviarse a APRS-IS.

### `Receptor RF -> TX RF`

Se usa cuando APRSBox debe actuar como digi y repetir trafico por RF.

### `TX local -> TX APRS-IS`

Se usa cuando objetos, estado, meteorologia, boletines u otras tramas generadas por APRSBox deben enviarse a APRS-IS.

### `Receptor RF -> Agujero negro`

Se usa para pruebas y observacion de trafico sin reenviarlo.

## Donde esta la descripcion detallada

La descripcion completa de bloques, filtros, campos de configuracion y esquemas listos se encuentra en la ayuda de `Packet Flow`:

[Referencia detallada de Packet Flow](packet_routing_flow.es.md)
