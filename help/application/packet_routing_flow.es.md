# Packet Flow - referencia detallada

Este archivo de ayuda corresponde al editor `Packet Flow`, que se abre al entrar en una regla concreta desde la lista `Packet Routing`.

Reune la estructura detallada de la regla, los casos de uso mas comunes, el orden de pasos, los bloques de filtro, los bloques de destino y varios esquemas listos para usar.

## Que hace esta pantalla

Una regla de routing define que debe hacer APRSBox con un paquete despues de recibirlo o generarlo localmente.

Cada regla tiene:

- una fuente,
- cero o mas bloques de filtro o regla en medio,
- un destino final.

Los paquetes siempre avanzan de arriba hacia abajo. Si un bloque rechaza el paquete, los pasos siguientes ya no se ejecutan.

## Como leer y construir una regla

La forma mas simple de pensar una regla es:

1. Por donde entra el paquete.
2. Que condiciones debe cumplir.
3. A donde debe terminar.

Orden recomendado:

1. Elegir la fuente.
2. Elegir el destino.
3. Anadir solo los filtros realmente necesarios.
4. Guardar la regla y revisar el log de ejecucion.

## Casos de uso mas comunes

### `Receptor RF -> TX APRS-IS`

Es la ruta clasica de iGate.

Esquema minimo:

```text
Receptor RF -> Filtro estricto -> TX APRS-IS
```

Usalo cuando:

- el trafico RF escuchado localmente debe reenviarse a APRS-IS,
- distintos puertos RF deben tener reglas distintas para el uplink a Internet,
- quieres separar la entrada RF del trafico generado localmente.

Notas importantes:

- `Filtro estricto` es obligatorio,
- no toda trama recibida por RF debe entrar en APRS-IS,
- esta es una ruta de uplink, no una ruta de digi.

### `Receptor RF -> TX RF`

Es la ruta clasica de digipeater.

Esquema minimo:

```text
Receptor RF -> Regla de trayectoria y protección DIGI -> TX RF
```

Esquema mas habitual:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

Usalo cuando:

- quieres repetir trafico APRS por RF,
- estas construyendo un digi local,
- quieres hacer cross-band o reenvio entre puertos RF,
- quieres dejar pasar solo cierto trafico despues de filtros adicionales.

Notas importantes:

- `Regla de trayectoria y protección DIGI` es obligatoria,
- `Filtro duplicado (retraso viscoso)` suele ser un buen primer paso,
- esta es la ruta donde mas importa proteger el canal RF.

### `TX local -> TX APRS-IS`

Esta ruta es para tramas generadas por APRSBox.

Esquema:

```text
TX local -> Filtro estricto -> TX APRS-IS
```

Usalo cuando:

- beacons, estado, meteorologia, objetos, boletines o mensajes deben ir a APRS-IS,
- el trafico generado por la aplicacion necesita salida hacia Internet APRS.

Notas importantes:

- `TX local` no es trafico recibido por RF,
- es un flujo interno separado,
- `Filtro estricto` sigue siendo obligatorio.

### `Receptor RF -> Agujero negro`

Es una ruta de prueba y diagnostico.

Esquemas:

```text
Receptor RF -> Agujero negro
```

o:

```text
Receptor RF -> Solo directo -> Agujero negro
```

Usalo cuando:

- quieres probar filtros sin reenviar nada,
- quieres observar un puerto RF concreto,
- quieres validar una regla antes de activar TX RF o TX APRS-IS.

### `TX local -> Agujero negro`

Es una ruta de diagnostico para trafico generado internamente.

Usalo cuando:

- quieres ver que esta generando APRSBox,
- quieres probar objetos, estado, meteorologia o boletines sin reenviarlos.

## Bloques de fuente

### `Receptor RF`

Es la fuente para paquetes recibidos por el modem de radio seleccionado.

Usalo cuando:

- la regla debe reaccionar al trafico que llega del aire,
- varios receptores RF necesitan logica de routing separada.

En la practica:

- toda regla `Receptor RF -> ...` empieza aqui,
- el modem elegido decide que entrada puede entrar en la regla.

### `TX local`

Es la fuente para tramas generadas localmente por APRSBox.

Incluye:

- beacons,
- paquetes de estado,
- meteorologia,
- objetos,
- items,
- boletines,
- mensajes.

No incluye:

- trafico recibido por RF,
- trafico ya digipeatado,
- trafico ordinario de entrada desde TNC.

En la practica:

- es el flujo interno de transmision de la aplicacion,
- `TX local` solo puede llevar a `TX APRS-IS` o `Agujero negro`.

## Bloques de filtros y reglas

### `Filtro estricto`

Es el bloque de seguridad del sistema para reglas que terminan en `TX APRS-IS`.

Para tramas que llegan desde `Receptor RF`:

- revisa toda la ruta externa,
- rechaza la trama si la ruta contiene `TCPIP`, `TCPXX`, `NOGATE` o `RFONLY`,
- valida la encapsulacion third-party,
- si la third-party es valida, revisa tambien la ruta interna para los mismos tokens bloqueados.

Para `TX local` es mas estricto:

- la trama debe estar marcada en metadatos como trafico APRSBox generado localmente,
- la encapsulacion third-party se rechaza,
- cualquier construccion `q..` en la ruta se rechaza,
- `TCPIP`, `TCPXX`, `NOGATE` y `RFONLY` siguen bloqueados.

Notas importantes:

- con `TX APRS-IS` este filtro es obligatorio,
- no sustituye la logica digi RF,
- si falla el parseo TNC2, la trama se rechaza.

Casos tipicos:

- `Receptor RF -> Filtro estricto -> TX APRS-IS`,
- `TX local -> Filtro estricto -> TX APRS-IS`.

### `Regla de trayectoria y protección DIGI`

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
  Si el primer hop no consumido coincide con esta lista, el hop solo se marca como consumido, sin insertar el indicativo local.

Que puedes escribir:

- un hop completo como `WIDE1-1`, `WIDE2-1`, `WIDE2-2` o `SP2-2`,
- un alias de familia como `WIDE`; entonces coinciden miembros como `WIDE1-1` y `WIDE2-2`.

Reescrituras tipicas:

- TRACE `WIDE1-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-1` -> `MYCALL-SSID*`,
- TRACE `WIDE2-2` -> `MYCALL-SSID*,WIDE2-1`,
- NO TRACE `WIDE2-2` -> `WIDE2-2*,WIDE2-1`,
- NO TRACE `SP2-2` -> `SP2-2*,SP2-1`,
- si el hop no tiene forma `N-N`, NO TRACE solo anade `*`.

Entradas tipicas de arranque:

- `TRACE`: `WIDE1-1`, `WIDE2-1`, `WIDE2-2`,
- `NO TRACE`: tu propio `CALLSIGN-SSID` de `My settings` y excepciones locales permitidas por la politica de red.

Por que suele anadirse el propio indicativo a `NO TRACE`:

- para consumir paquetes dirigidos expresamente a tu indicativo sin insertarlo otra vez en la ruta,
- para manejar hops locales explicitos que no deben dejar traza.

Notas importantes:

- si TRACE coincide pero no esta configurado el indicativo local, la trama se rechaza,
- si el primer hop no consumido no coincide ni con TRACE ni con NO TRACE, la trama se rechaza.

Esquema tipico:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

### `Filtro duplicado (retraso viscoso)`

Este bloque no deja pasar la trama inmediatamente. La primera trama con una huella dada queda retenida hasta que termine la ventana de escucha.

Comportamiento real:

- la huella se construye con `source callsign + info field`,
- la ruta no participa en la comparacion de duplicados,
- la primera trama espera hasta el final de la ventana,
- si durante esa ventana aparece otra trama con la misma huella, ambas se descartan,
- si no aparece duplicado, la primera trama continua solo al expirar el temporizador.

Consecuencias practicas:

- dos tramas de la misma estacion con el mismo payload pero distinta ruta siguen contando como duplicado,
- es un verdadero viscous-delay: primero espera y despues decide,
- solo puede aparecer una vez y debe ser el primer filtro de un flujo RF.

Usalo cuando:

- varios digis pueden escuchar la misma estacion origen,
- quieres reducir repeticiones innecesarias sin transmitir de inmediato.

### `Solo directo`

Este filtro deja pasar solo paquetes escuchados directamente.

Comportamiento real:

- solo comprueba si la ruta ya contiene algun hop consumido marcado con `*`,
- no le importan los hops aun no consumidos como `WIDE1-1`,
- `...,WIDE1-1:` pasa,
- `...,SR5ABC*,WIDE1-1:` se rechaza.

Usalo cuando:

- la regla debe reaccionar solo a estaciones oidas en directo,
- el trafico ya repetido debe ignorarse,
- quieres revisar por separado la cobertura directa.

### `Filtro DIGI`

Este filtro no mira toda la ruta ni revisa hops aun no consumidos. Solo analiza los hops ya marcados con `*`, quitando antes esa estrella.

Comportamiento real:

- de `SR5BCD-2*,WIDE1-1` solo ve `SR5BCD-2`,
- de `WIDE1-1` no ve nada, porque todavia no hay hops consumidos,
- los patrones se comparan con los hops consumidos; el wildcard `*` puede usarse en cualquier posicion,
- `allow` deja pasar solo si al menos un hop consumido coincide,
- `deny` rechaza solo si al menos un hop consumido coincide.

Consecuencias practicas:

- una lista `allow` vacia rechaza todo,
- una lista `deny` vacia deja pasar todo,
- `*` en `deny` bloquea toda trama ya digipeateada,
- `*` en `deny` no bloquea tramas realmente directas, porque no hay hop consumido que comparar.

Ejemplos:

- ruta `SR5BCD-2*,WIDE1-1` con patron `SR5BCD*` -> match,
- ruta `SR5ABC*,WIDE1-1` con `deny: *` -> drop,
- ruta `WIDE1-1` con `deny: *` -> pass.

Usalo cuando:

- solo debe pasar trafico que vino por digis concretos,
- quieres excluir trafico ya repetido por estaciones intermedias determinadas.

### `Filtro de indicativo`

Este filtro comprueba solo el indicativo de origen. No analiza la ruta, los hops digi ni el destino.

Como funciona:

- sin `*`, la coincidencia es exacta,
- `SQ9MDD` no coincide con `SQ9MDD-4`,
- `*` puede usarse en cualquier posicion,
- `allow` funciona como lista blanca,
- `deny` funciona como lista negra.

Consecuencias practicas:

- una lista `allow` vacia rechaza todo,
- una lista `deny` vacia deja pasar todo.

Ejemplos:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Usalo cuando:

- quieres separar trafico de club, pruebas, servicio u operador,
- quieres bloquear o aislar una fuente conocida.

### `Filtro de tipo de paquete`

Este filtro trabaja sobre lo que el decodificador APRSBox reconoce como grupo o tipo de paquete APRS.

Selectores mas comunes:

- `position`,
- `object`,
- `item`,
- `message`,
- `status`,
- `weather`,
- `telemetry`,
- `query`.

Significado practico:

- `message` tambien cubre ACK/REJ, bulletin y announcement,
- `weather` significa solo tramas weather-only,
- una posicion con datos meteorologicos sigue contando como `position`,
- por compatibilidad, tambien funcionan selectores antiguos como `M`, `S`, `O` y `W`, ademas de otros codigos crudos devueltos por el parser.

Como funciona:

- en modo `allow`, la trama pasa solo si el grupo o tipo decodificado coincide con la lista,
- en modo `deny`, la trama cae solo si el grupo o tipo decodificado coincide con la lista,
- si el parser no puede determinar grupo/tipo, `allow` rechaza y `deny` deja pasar.

Usalo cuando:

- posiciones, objetos, mensajes o meteorologia deben ir por rutas distintas,
- una regla debe limitarse a una sola clase de trafico.

### `Filtro de icono`

Este filtro compara exactamente el simbolo APRS en formato `table+code`.

Como funciona:

- la coincidencia es exacta y no usa wildcard,
- compara exactamente el valor de simbolo devuelto por el parser de APRSBox,
- en modo `allow`, si no coincide se rechaza,
- en modo `deny`, si no coincide se deja pasar,
- si el simbolo no puede decodificarse, `allow` rechaza y `deny` deja pasar.

Ejemplos:

- `/>`,
- `\\l`.

Usalo cuando:

- ciertas clases de simbolo deben tener su propia ruta,
- el significado del simbolo importa mas que el tipo de paquete.

### `Filtro de distancia`

Este filtro deja pasar una trama solo cuando la posicion decodificada cae dentro de al menos una zona configurada.

Como funciona:

- se pueden definir de 1 a 3 zonas,
- cada zona tiene centro y radio,
- las zonas se evalúan con logica OR,
- si no hay ninguna zona valida, el filtro se omite,
- si la trama no tiene posicion decodificable, el filtro se omite,
- solo una trama con posicion fuera de todas las zonas se rechaza.

Usalo cuando:

- quieres limitar trafico a un area geografica,
- quieres routing local segun zona de cobertura o de evento.

### `Filtro de limite de ritmo`

Este filtro no cuenta paquetes por minuto. Es una compuerta temporal simple basada en el indicativo de origen.

Formato de regla:

```text
CALL_OR_PATTERN - LIMIT
```

Ejemplos:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
SQ9MDD - 20s
* - 20s
```

Como funciona:

- actua solo sobre el indicativo de origen,
- la primera trama que coincide siempre pasa,
- la siguiente trama de la misma fuente bajo la misma regla coincidente se bloquea hasta que expire el limite,
- el temporizador solo se actualiza con tramas que realmente pasaron,
- si ninguna regla coincide con la fuente, el filtro no bloquea nada y la trama sigue.

Como se comparan los patrones:

- `SQ9MDD-7` sin wildcard coincide solo con ese SSID exacto,
- `SQ9MDD` sin wildcard y sin SSID coincide con ese indicativo con cualquier SSID,
- `SQ*` funciona como wildcard,
- si coinciden varias reglas, runtime elige la mas especifica; en empate gana la linea anterior.

Limites del formato:

- `LIMIT` puede escribirse como `30`, `30s` o `30S`,
- el rango permitido es de 5 a 300 segundos,
- el paso es de 5 segundos.

Usalo cuando:

- estaciones muy activas generan demasiado trafico,
- una ruta RF necesita control suave sin bloquear completamente la fuente.

## Bloques de destino

### `TX RF`

Este destino envia el paquete por el modem de radio seleccionado.

Usalo para:

- rutas digi locales,
- cross-band,
- reenvio entre puertos RF.

Esquema tipico:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

### `TX APRS-IS`

Este destino envia el paquete a APRS-IS.

Usalo para:

- uplink de iGate,
- trafico generado localmente por APRSBox que debe llegar a APRS-IS.

Limitacion importante:

- este destino siempre mantiene el `Filtro estricto` obligatorio.

### `Agujero negro`

Este es un destino de diagnostico. El paquete termina alli y no se reenvia mas lejos.

Usalo para:

- pruebas,
- observacion de trafico,
- validacion de filtros antes de activar la transmision.

## Restricciones del editor

- Una regla siempre tiene una fuente y un destino.
- `TX local` solo puede llevar a `TX APRS-IS` o `Agujero negro`.
- `TX APRS-IS` siempre mantiene el `Filtro estricto` obligatorio.
- `TX RF` requiere una `Regla de trayectoria y protección DIGI` activa.
- `Filtro duplicado (retraso viscoso)` solo puede aparecer una vez.
- `Filtro de distancia` solo puede aparecer una vez.
- `Filtro de limite de ritmo` esta pensado para flujos que terminan en `TX RF`.

## Esquemas listos para usar

### iGate RF simple

```text
Receptor RF -> Filtro estricto -> TX APRS-IS
```

### Digi RF clasico

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

### Digi solo para estaciones directas

```text
Receptor RF -> Solo directo -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y protección DIGI -> TX RF
```

### Trafico generado localmente hacia APRS-IS

```text
TX local -> Filtro estricto -> TX APRS-IS
```

### Diagnostico sin reenvio

```text
Receptor RF -> Agujero negro
```

## Buenas practicas

- Elige primero fuente y destino, y despues construye las condiciones.
- Para `TX RF`, piensa antes en proteger el canal que en ampliar cobertura.
- Para `TX APRS-IS`, asegurate de que solo llegue al lado de Internet el trafico adecuado.
- Durante las pruebas, empieza con `Agujero negro`.
- Despues de guardar, usa el log de ejecucion para ver exactamente que paso acepto o rechazo el paquete.
