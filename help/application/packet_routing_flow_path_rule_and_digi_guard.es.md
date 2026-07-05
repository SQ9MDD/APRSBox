# Regla de trayectoria y protección DIGI

Es el bloque clave para flujos que terminan en `TX RF`. Primero hace la proteccion DIGI y despues reescribe la ruta.

La parte de proteccion rechaza:

- tramas third-party,
- mensajes APRS dirigidos a la `My station` local,
- queries APRS dirigidas a la `My station` local,
- mensajes APRS dirigidos a la estacion `WX` local,
- queries APRS dirigidas a la estacion `WX` local,
- tramas donde la estacion local ya aparece como hop consumido, por ejemplo `MYCALL-SSID*`.

Solo despues analiza la ruta:

- si la ruta esta vacia, la trama se rechaza,
- si todos los hops ya estan consumidos, la trama se rechaza,
- solo se revisa el primer hop aun no consumido,
- los hops siguientes no se miran hasta resolver ese primero.

Campos de configuracion:

- `Paths (TRACE / traced)`:
  Si el primer hop no consumido coincide con esta lista, APRSBox lo consume e inserta el indicativo local desde `My settings`.
- `Paths (NO TRACE / not traced)`:
  Si el primer hop no consumido coincide con esta lista, APRSBox reduce ese hop en su lugar sin insertar el indicativo digi local.

Que puedes escribir:

- `TRACE`: un hop completo como `WIDE1-1`, `WIDE2-1`, `WIDE2-2` o un alias de familia como `WIDE`,
- `NO TRACE`: un hop completo como `SP1-1`, `SP2-1`, `SP2-2`, un alias de familia como `SP` o tu propio `CALLSIGN-SSID`.

Reescrituras tipicas:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `SP1-1` -> `SP1*`,
- NO TRACE `SP2-1` -> `SP2*`,
- NO TRACE `SP2-2` -> `SP2-1`,
- si el hop no tiene forma `N-N`, NO TRACE solo anade `*`.

Entradas tipicas de arranque:

- `TRACE`: `WIDE`, `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: `SP`, `SP1-1`, `SP2-1`, `SP2-2`, tu propio `CALLSIGN-SSID` de `My settings`.

Por que suele anadirse el propio indicativo a `NO TRACE`:

- para consumir paquetes dirigidos expresamente a tu indicativo sin insertarlo otra vez en la ruta,
- para manejar hops locales explicitos que no deben dejar traza,
- para reducir hops locales de la familia `SP` sin insertar tu propio indicativo en la ruta.

Notas importantes:

- si TRACE coincide pero no esta configurado el indicativo local, la trama se rechaza,
- si el primer hop no consumido no coincide ni con TRACE ni con NO TRACE, la trama se rechaza.

Esquema tipico:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

## Navegación

[Volver a la referencia de la regla Packet Flow](packet_routing_flow.es.md)
