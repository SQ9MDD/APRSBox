# WX

La pestaña WX configura la estación meteorológica local de APRSBox. Los datos se leen desde fuentes HTTP, se normalizan al formato APRS complete WX y se transmiten como una trama meteorológica local.

## Orden de configuración

- Configura el indicativo de la estación en `My Settings`.
- Elige un `WX SSID` separado para la estación meteorológica.
- Añade una fuente en `WX data sources`.
- Prueba la fuente o ejecuta `Discover source`.
- Asigna fuentes e identificadores en `WX data mapping`.
- Ejecuta lecturas de prueba para los parámetros obligatorios.
- Activa `Enable WX`, guarda la configuración y revisa `WX TX Log`.

## Global WX configuration

- `Callsign` se lee desde `My Settings` y no se edita en esta pestaña.
- `WX SSID` crea el indicativo de la estación meteorológica, por ejemplo `SQ9XYZ-13`. El SSID usado por la estación principal no está disponible para WX.
- `Interface` selecciona el TNC usado para la trama WX, o la opción que envía por todas las interfaces activas.
- `Path` define la ruta APRS de la trama WX. Un campo vacío o `RFONLY` se trata como transmisión directa sin digipeaters.
- La ruta vacía y `RFONLY` permiten intervalos más cortos. Una ruta con digipeaters, como `WIDE2-2`, limita la lista a intervalos más largos.
- `Latitude` y `Longitude` definen la posición de la estación meteorológica. `Get location` permite elegir el punto en el mapa.
- `Refresh / TX interval` controla el ciclo de lectura de datos y planificación de transmisión WX.
- `Allow cached values on failure` permite reutilizar el último valor correcto cuando la fuente no responde temporalmente.
- `Default max cache age (s)` define durante cuánto tiempo un valor de cache sigue siendo utilizable.

`Refresh now` lee los mapeos configurados y actualiza la cache. `Send now` guarda la configuración del formulario, realiza un refresh manual y después pone la trama WX en la cola de transmisión.

## WX data mapping

El mapeo conecta un parámetro APRS WX con una fuente y un identificador dentro de esa fuente.

Los parámetros obligatorios para la trama WX básica son:

- `Wind direction` en grados,
- `Wind speed` en mph,
- `Temperature` en grados Fahrenheit.

Los parámetros opcionales incluyen racha de viento, lluvia de la última hora, lluvia de 24 horas, lluvia desde medianoche, humedad, presión, nieve, luminosidad, contador bruto de lluvia, altura de agua, voltaje de batería y radiación.

`Raw value` y `Normalized` muestran el valor leído de la fuente y el valor convertido a la unidad APRS. `LIVE` significa una lectura nueva, `CACHED` significa que se usó el último valor correcto, y `MISSING`, `STALE` o `ERROR` indican que hay que revisar la fuente, el identificador o la unidad.

## WX data sources

- `Home Assistant` usa la API de Home Assistant y requiere `Bearer token`.
- `Domoticz` usa la API de Domoticz y admite sin autenticación o `Basic auth`.
- `Base URL` debe apuntar a la URL principal del sistema, por ejemplo `http://127.0.0.1:8123`.
- `Timeout (s)` limita cuánto espera APRSBox la respuesta de la fuente.
- `Verify TLS certificate` debería permanecer activado para certificados HTTPS válidos.
- `Enable source` decide si la fuente puede usarse para lecturas.

El icono de prueba verifica la conexión con la fuente. El icono de discovery carga entidades o dispositivos detectados, lo que ayuda a introducir el `Identifier` correcto en el mapeo.

## WX TX Log

El log muestra los trabajos WX recientes: hora, tipo, estado, interfaz, intentos, error y vista previa de la trama TNC2. Si una trama no se transmite, revisa primero los mapeos obligatorios, la posición, que WX esté activado, el TNC activo y el mensaje de error del log.
