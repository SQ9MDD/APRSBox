# Preparación de la estación

Esta tarjeta es una lista sencilla para la primera puesta en marcha. Muestra lo que falta en la configuración, pero no comprueba la calidad de la antena, la cobertura RF ni si otras estaciones reciben tus tramas.

## Antes de empezar — tres conceptos

- **RF** es el tráfico de radio recibido o transmitido mediante un TNC.
- **APRS-IS** es la red APRS en Internet.
- Un **flujo** es una regla de routing «origen → destino», por ejemplo `Receiver RF → TX APRS-IS`.

Completa los pasos en orden. Las interfaces crean los orígenes y destinos que después usarás en `Mi estación` y `Packet Routing`.

## Orden de configuración recomendado

### 1. Interfaces

Abre primero `Interfaces` y añade:

- al menos una interfaz de radio `TCP` o `SERIALL` activa; `OpenWebRX MQTT` es solo de recepción,
- una interfaz `APRS-IS (RX/TX)` cuando la estación deba recibir desde APRS-IS o enviar tramas a la red.

Comprueba que las interfaces estén habilitadas, que TX no esté bloqueado accidentalmente en el TNC físico y que APRS-IS alcance el estado conectado.

**Después de este paso:** `Interfaces de radio` y `Conexión APRS-IS` deberían estar en verde. Si solo están activas algunas interfaces de radio configuradas, el estado es amarillo oscuro. Ninguna interfaz de radio activa produce un estado rojo.

[Ayuda de Interfaces](tnc.es.md)

### 2. Mi estación

Después configura `Mi estación`:

- indicativo y SSID,
- coordenadas y símbolo APRS,
- comentario, intervalo y ruta de la baliza,
- destino TX: una interfaz de radio, todas las interfaces activas o `Internal TX`,
- transmisión automática cuando se necesiten balizas periódicas.

`Internal TX` crea una trama dentro de APRSBox, pero no la envía a un TNC físico. Elígelo cuando solo el routing deba decidir el destino. Seleccionar una interfaz de radio o todas las interfaces activas transmite la baliza por RF.

**Después de este paso:** `Baliza definida` debería estar en verde. Definir una baliza no basta para enviarla a APRS-IS; ese camino depende del flujo del paso 3.

[Ayuda de Mi estación](station.es.md)

### 3. Packet Routing

Por último, abre `Packet Routing` y añade los flujos activos necesarios para la función de la estación.

Para que toda la tarjeta quede verde, APRSBox comprueba:

- `Local TX → TX APRS-IS` — envía directamente a APRS-IS balizas, estado, meteorología, objetos, items, boletines y mensajes creados localmente,
- `Receiver RF → TX APRS-IS` para cada entrada RF activa — el uplink iGate clásico,
- `APRS-IS → TX RF` para cada interfaz activa con TX — el retorno protegido de mensajes APRS-IS que cumplan las reglas,
- `Receiver RF → TX RF` entre las interfaces activas requeridas — operación digi o cross-band según el diseño de la estación.

[Ayuda de Packet Routing](packet_routing.es.md)

**Después de este paso:** `Local TX → APRS-IS` y las celdas necesarias de cada interfaz activa deberían estar en verde. Compara cualquier dirección ausente de la tarjeta con la lista anterior.

## Tramas propias y APRS-IS

Una trama transmitida por la interfaz de radio propia no se sube automáticamente de forma directa a APRS-IS. Puede aparecer en la red si la recibe un iGate RF propio o externo, pero depende de la cobertura RF, los filtros y la disponibilidad de esa pasarela.

Para subir las tramas propias independientemente de un iGate RF, crea un flujo activo `Local TX → TX APRS-IS`. Se aplica tanto a una trama enviada a `Internal TX` como a una trama propia transmitida simultáneamente por una interfaz de radio.

Es una ruta separada de `Receiver RF → TX APRS-IS`: `Local TX` procesa tramas creadas por APRSBox y `Receiver RF` tramas realmente recibidas por radio. No crees un flujo desde la salida de radio; las tramas generadas localmente siempre usan `Local TX` como origen del routing.

## Significado de los colores

- verde — elemento requerido activo o flujo presente,
- amarillo oscuro — configuración parcial o flujo ausente,
- rojo — ninguna interfaz activa o error de conexión,
- gris — interfaz deshabilitada o dirección no aplicable.

Si no deseas ofrecer una función como digi o `APRS-IS → RF`, el campo correspondiente puede permanecer como advertencia. No significa un fallo de ejecución; muestra la diferencia respecto a la matriz de preparación completa.
