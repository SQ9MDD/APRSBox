# Reglas de enrutamiento de paquetes

Este es el archivo completo de ayuda para `Packet Routing` y `Packet Flow`. Reune el objetivo de la pantalla, los casos de uso mas comunes, el orden de la regla, los bloques de filtro y destino, y varios esquemas listos para usar.

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
Receptor RF -> Regla de trayectoria y guardia DIGI -> TX RF
```

Esquema mas habitual:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y guardia DIGI -> TX RF
```

Usalo cuando:

- quieres repetir trafico APRS por RF,
- estas construyendo un digi local,
- quieres hacer cross-band o reenvio entre puertos RF,
- quieres dejar pasar solo cierto trafico despues de filtros adicionales.

Notas importantes:

- `Regla de trayectoria y guardia DIGI` es obligatoria,
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

Hace lo siguiente:

- rechaza paquetes con `TCPIP` o `TCPXX`,
- rechaza paquetes marcados `NOGATE` o `RFONLY`,
- valida tramas third-party,
- valida la ruta externa e interna del trafico third-party,
- evita que trafico inadecuado llegue a APRS-IS.

Usalo:

- siempre con `TX APRS-IS`,
- nunca como sustituto del control de trayectoria de un digi RF.

Casos tipicos:

- `Receptor RF -> Filtro estricto -> TX APRS-IS`,
- `TX local -> Filtro estricto -> TX APRS-IS`.

### `Regla de trayectoria y guardia DIGI`

Es el bloque mas importante para flujos que terminan en `TX RF`.

Hace lo siguiente:

- analiza la ruta digi,
- decide si la estacion local todavia debe repetir el paquete,
- bloquea mensajes y consultas APRS dirigidos localmente,
- bloquea trafico third-party que no debe repetirse,
- bloquea tramas ya repetidas por la misma estacion local.

Por que es obligatorio:

- sin este bloque, una regla RF no tiene proteccion digi basica,
- este bloque aporta la logica principal de trayectoria para repetir con seguridad en el aire.

Campos de configuracion:

- `Paths (TRACE / traced)`:
  Alias o saltos explicitos que deben consumirse insertando el indicativo del digi local en la ruta.
- `Paths (NO TRACE / not traced)`:
  Alias o saltos explicitos que deben consumirse sin insertar el indicativo del digi local.

En la practica:

- `WIDE1-1` suele configurarse como traced,
- la lista no-trace depende de la politica local de red,
- este bloque suele estar cerca del final de la cadena, justo antes de `TX RF`.

Esquema tipico:

```text
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y guardia DIGI -> TX RF
```

### `Filtro duplicado (retraso viscoso)`

Este bloque abre una ventana corta de escucha cuando la trama entra en el flujo.

Hace lo siguiente:

- espera durante la ventana configurada,
- comprueba si otro digi ya repitio la misma trama,
- descarta la trama si detecta una repeticion duplicada,
- la deja seguir si no escucha esa repeticion.

Comportamiento importante:

- solo puede aparecer una vez,
- debe ser el primer filtro en un flujo de retransmision RF,
- es especialmente util en reglas digi clasicas.

Usalo cuando:

- quieres reducir duplicados,
- varios digis pueden escuchar la misma estacion origen.

### `Solo directo`

Este filtro deja pasar solo paquetes escuchados directamente.

Eso significa:

- la ruta no puede contener ningun hop digi ya consumido,
- si la ruta contiene elementos consumidos marcados con `*`, la trama se rechaza.

Usalo cuando:

- la regla debe reaccionar solo a estaciones escuchadas localmente,
- el trafico ya repetido debe ignorarse,
- quieres inspeccionar por separado la cobertura directa.

### `Filtro DIGI`

Este filtro examina los hops digi ya consumidos en la ruta.

Como funciona:

- solo compara hops ya consumidos,
- los patrones admiten `*`,
- `allow` deja pasar solo paquetes coincidentes,
- `deny` rechaza paquetes coincidentes.

Ejemplos:

- `SR5ABC`,
- `SR5*`,
- `*`.

Usalo cuando:

- solo debe pasar trafico procedente de ciertas cadenas digi,
- quieres excluir trafico que ya paso por digis concretos.

### `Filtro de indicativo`

Este filtro compara el indicativo de origen.

Como funciona:

- opera sobre el indicativo fuente del paquete,
- admite wildcard `*`,
- `allow` funciona como lista blanca,
- `deny` funciona como lista negra.

Ejemplos:

- `SQ9MDD`,
- `SQ9MDD*`,
- `SP*`.

Usalo cuando:

- quieres separar trafico de club, pruebas, servicio u operador,
- quieres bloquear o aislar una fuente conocida.

### `Filtro de tipo de paquete`

Este filtro trabaja sobre los grupos de paquetes APRS.

Valores aceptados:

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
- `weather` significa tramas weather-only,
- una posicion con datos meteorologicos sigue contando como `position`.

Usalo cuando:

- posiciones, objetos, mensajes o meteorologia deben ir por rutas distintas,
- una regla debe limitarse a una sola clase de trafico.

### `Filtro de icono`

Este filtro compara el simbolo APRS en formato `table+code`.

Ejemplos:

- `/>`,
- `\\l`.

Usalo cuando:

- ciertas clases de simbolo deben tener su propia ruta,
- el significado del simbolo importa mas que el tipo de paquete.

### `Filtro de distancia`

Este filtro deja pasar un paquete solo cuando su posicion decodificada cae dentro de al menos una zona configurada.

Como funciona:

- se pueden definir de 1 a 3 zonas,
- cada zona tiene centro y radio,
- las zonas se evalúan con logica OR,
- los paquetes sin posicion decodificable no se rechazan automaticamente.

Usalo cuando:

- quieres limitar trafico a un area geografica,
- quieres routing local segun zona de cobertura o de evento.

### `Filtro de limite de ritmo`

Este filtro limita con que frecuencia pueden continuar paquetes de un indicativo o patron de indicativo.

Formato de regla:

```text
CALL_OR_PATTERN - LIMIT
```

Ejemplos:

```text
SQ9MDD-7 - 30s
SQ2IDB* - 10s
* - 20s
```

Como funciona:

- mide el tiempo desde la ultima trama aceptada para cada patron coincidente,
- bloquea la siguiente trama si llega antes de que expire el limite.

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
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y guardia DIGI -> TX RF
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
- `TX RF` requiere una `Regla de trayectoria y guardia DIGI` activa.
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
Receptor RF -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y guardia DIGI -> TX RF
```

### Digi solo para estaciones directas

```text
Receptor RF -> Solo directo -> Filtro duplicado (retraso viscoso) -> Regla de trayectoria y guardia DIGI -> TX RF
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
