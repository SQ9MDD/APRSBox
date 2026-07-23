# APRS-IS como origen y RF Guard

Un flow `APRS-IS -> RF` reenvia paquetes APRS-IS seleccionados a una interfaz de radio fisica bajo control estricto. El destino solo puede ser un TNC fisico activo con TX. APRS-IS y las interfaces RX-only no pueden ser destinos.

## Orden obligatorio

`APRS-IS source -> RF Guard -> filtro default-deny de indicativo + radio -> TX RF`

`RF Guard` se añade automaticamente al seleccionar un origen APRS-IS. No se puede eliminar, desactivar, evitar ni duplicar. Backend y runtime aplican la proteccion incluso si los datos guardados se modifican manualmente.

## Filtro default-deny de indicativo y radio

El filtro contiene solo una lista de indicativos de origen y un radio. Ambas condiciones usan `AND`: el origen del paquete debe coincidir exactamente con un indicativo configurado y su posicion decodificada debe estar dentro del radio medido desde las coordenadas de `My Station`.

La coincidencia es estricta e incluye el SSID. `SQ9MDD` solo coincide con `SQ9MDD`; `SQ9MDD-1` solo coincide con `SQ9MDD-1`. No se admiten comodines. Introduzca un indicativo por linea.

Una configuracion vacia es un `default deny` valido. Tambien se deniegan los paquetes sin posicion decodificada y todos los paquetes cuando faltan coordenadas validas en `My Station`.

## Proteccion RF

El guard aplica siempre validacion APRS y q-construct, prevencion de bucles, bloqueo de `NOGATE`, `RFONLY` y `TCPXX`, normalizacion de duplicados entre RF y APRS-IS, viscous delay, segunda comprobacion de duplicados, rate limits, encapsulacion third-party y limite AX.25. `TCPIP` por si solo no se bloquea; la ruta de Internet se elimina antes de TX.

Los valores predeterminados son `5 s` de viscous delay, `6 paquetes/min` con burst `3` por flow, `2 paquetes/min` con burst `2` por indicativo de origen y una ventana de duplicados de `30 s`. Los pending viven solo en memoria, se cancelan al recibir la misma copia por RF local y no se recuperan tras reiniciar.

El payload original se conserva. Se usa la ruta RF de salida configurada; vacia significa transmision directa. Los paquetes aceptados entran en la cola RF/KISS existente. Contadores separados APRS-IS-to-RF evitan alterar las estadisticas DIGI y RX fisico del TNC.

## Navegacion

[Volver a Packet Flow](packet_routing_flow.es.md)
