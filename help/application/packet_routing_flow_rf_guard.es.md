# APRS-IS como origen y RF Guard

Un flow `APRS-IS -> RF` reenvia paquetes APRS-IS seleccionados a una interfaz de radio fisica bajo control estricto. El destino solo puede ser un TNC fisico activo con TX. APRS-IS y las interfaces RX-only no pueden ser destinos.

## Orden obligatorio

`APRS-IS source -> RF Guard -> reglas allow explicitas -> TX RF`

`RF Guard` se añade automaticamente al seleccionar un origen APRS-IS. No se puede eliminar, desactivar, evitar ni duplicar. Backend y runtime aplican la proteccion incluso si los datos guardados se modifican manualmente.

## Reglas allow explicitas

Todas las reglas son inclusivas. Las condiciones de una regla usan `AND` y las reglas separadas usan `OR`. Las condiciones reutilizan datos del parser y filtros existentes: tipo de paquete, indicativo de origen, destination, destinatario del mensaje, nombre de objeto, simbolo y area de distancia.

Una lista vacia es una configuracion `default deny` valida: el flow se puede guardar y activar, pero no reenvia ningun paquete.

## Proteccion RF

El guard aplica siempre validacion APRS y q-construct, prevencion de bucles, bloqueo de `NOGATE`, `RFONLY` y `TCPXX`, normalizacion de duplicados entre RF y APRS-IS, viscous delay, segunda comprobacion de duplicados, rate limits, encapsulacion third-party y limite AX.25. `TCPIP` por si solo no se bloquea; la ruta de Internet se elimina antes de TX.

Los valores predeterminados son `5 s` de viscous delay, `6 paquetes/min` con burst `3` por flow, `2 paquetes/min` con burst `2` por indicativo de origen y una ventana de duplicados de `30 s`. Los pending viven solo en memoria, se cancelan al recibir la misma copia por RF local y no se recuperan tras reiniciar.

El payload original se conserva. Se usa la ruta RF de salida configurada; vacia significa transmision directa. Los paquetes aceptados entran en la cola RF/KISS existente. Contadores separados APRS-IS-to-RF evitan alterar las estadisticas DIGI y RX fisico del TNC.

## Navegacion

[Volver a Packet Flow](packet_routing_flow.es.md)
