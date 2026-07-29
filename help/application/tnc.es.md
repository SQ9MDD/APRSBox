# Interfaces

La pestaña Interfaces configura las conexiones de entrada y salida de APRSBox. Las interfaces de radio pueden recibir KISS/TNC2, transmitir tramas outbound y compartir opcionalmente un puerto KISS en la LAN. La conexión APRS-IS admite tanto recepción como transmisión controlada por `Packet Routing`.

## Lista de interfaces

La tabla muestra las interfaces configuradas. Haz clic en una fila para editarla.

- `Status` muestra el estado de configuración y runtime, por ejemplo conectado, error o desactivado.
- `Control TX` muestra el bloqueo TX de un TNC físico. Para APRS-IS, el icono de routing muestra si existe un flow activo que termina en `TX APRS-IS`.
- `LAN` muestra si APRSBox expone un proxy KISS/TNC para clientes LAN.

Desactivar una interfaz detiene su recepción. Desactivar una interfaz de radio también impide que el servicio outbound la use. Para APRS-IS, `Activar recepción APRS-IS` controla solo la recepción; un flow activo con destino `TX APRS-IS` puede mantener abierta la misma conexión y enviar datos por ella.

## Tipos de interfaz

- `TCP` conecta con un TNC o software que expone KISS por TCP. `Ruta / Dirección / Filtro` normalmente tiene formato `host:port`, por ejemplo `127.0.0.1:8001`.
- `SERIALL` usa un puerto serie local, por ejemplo `/dev/ttyUSB0` o `/dev/ttyACM0`, y requiere un `Baud Rate` válido.
- `OpenWebRX MQTT (RX only)` recibe paquetes desde OpenWebRX MQTT. Este tipo es solo RX: TX queda bloqueado y el proxy LAN se desactiva.
- `APRS-IS (RX/TX)` contiene la configuración completa de la conexión APRS-IS directamente en el formulario de la interfaz. Recibe líneas TNC2 que coinciden con el filtro del servidor y envía por la misma conexión las tramas aceptadas por un flow `Receiver RF -> TX APRS-IS` o `Local TX -> TX APRS-IS`. No usa KISS. Solo puede existir una interfaz APRSIS.

Para OpenWebRX MQTT, el campo de dirección debe ser una URL `mqtt://` o `mqtts://` con el topic en la ruta, por ejemplo `mqtt://user:pass@127.0.0.1:1883/openwebrx/aprs`.

Para APRSIS, `Filtro de recepción APRS-IS` es el filtro del servidor APRS-IS. Las interfaces nuevas usan `m/20` por defecto; se puede introducir otro filtro válido como `r/52.23/21.01/50`. El servidor, el puerto, el login y el passcode se guardan desde el mismo formulario. La pestaña separada `Ajustes iGATE` ya no se usa.

## Campos de configuración

- `Name` aparece en logs, listas de interfaces y selectores TX.
- `Band` describe la banda de la interfaz.
- `Enabled` activa una interfaz física en el runtime de APRSBox. Para APRS-IS, `Activar recepción APRS-IS` activa solo la recepción; TX se controla de forma independiente mediante flows que terminan en `TX APRS-IS`.
- `Block TX on this interface` permite recibir tráfico, pero bloquea la transmisión outbound.
- `TX Min Gap (s)` define la pausa mínima entre transmisiones en este TNC. El rango permitido es de `0.2` a `1.2` segundos.
- `RX Silence Reconnect Timeout (s)` se aplica a interfaces serie. Tras una ausencia de RX más larga que este valor, el broker serie puede forzar una reconexión. `0` desactiva este watchdog.

`Baud Rate` se usa solo para `SERIALL`. Para APRSIS se ocultan los campos propios de un TNC físico: ajustes seriales, bloqueo/pacing de TX RF y proxy LAN. Esto no bloquea la transmisión a APRS-IS, que se controla mediante `Packet Routing`.

El formulario de la interfaz APRSIS también contiene:

- `Servidor` y `Puerto` — la dirección del servidor APRS-IS, por defecto `rotate.aprs2.net:14580`.
- `Indicativo de inicio de sesión / indicativo-SSID` — puede dejarse vacío para usar la identidad de `Mi estación`.
- `Código de acceso` — puede dejarse vacío para que APRSBox derive el passcode APRS-IS estándar del indicativo de login.
- `Filtro de recepción APRS-IS` — controla el tráfico recibido del servidor, pero no limita las tramas enviadas por `Packet Routing`.

Debajo del formulario APRSIS, el estado actual de la conexión y el diagnóstico desplegable muestran los flows activos, el último error y los contadores TX. Un passcode APRS-IS no es una contraseña de cuenta, sino el código estándar derivado del indicativo.

## Routing iGate y seguridad APRS-IS

- `Receiver RF -> TX APRS-IS` crea el uplink iGate clásico desde radio hacia APRS-IS.
- `Local TX -> TX APRS-IS` envía a APRS-IS las tramas generadas por APRSBox, incluidas baliza, estado, meteorología, objetos, items, boletines y mensajes.

Ambos modos requieren un login APRS-IS verificado. `pass -1` identifica un cliente no verificado de solo recepción y no permite enviar tramas recibidas por RF. Para los uplinks RF, APRSBox usa `qAO` cuando el TNC receptor no tiene una ruta de retorno TX utilizable, o `qAR` cuando el TNC permite TX y un flow activo `APRS-IS -> RF` proporciona el retorno de mensajes. Las tramas generadas localmente usan `TCPIP*`.

El destino `TX APRS-IS` incluye un filtro de seguridad del sistema que rechaza, entre otros casos, tramas con `TCPIP` / `TCPXX`, `NOGATE` / `RFONLY` y encapsulación third-party incorrecta. Consulta [Packet Routing](packet_routing.es.md) para construir los flows en detalle.

## Expose Port

`Expose Port` expone la conexión TNC a través de APRSBox como puerto TCP para clientes LAN. APRSBox reenvía tramas entre el TNC físico y los clientes.

- `Allow TX from remote clients` permite que los clientes LAN envíen tramas al TNC. Si está desactivado, los clientes solo reciben.
- `Bind Address` define la dirección de escucha. `0.0.0.0` significa todas las interfaces de red.
- `Port` es el puerto TCP expuesto por APRSBox. Se admiten hasta 3 clientes simultáneos.
- `Whitelist` limita el acceso a direcciones IPv4 o redes CIDR. Escribe un elemento por línea; también se aceptan comas.

No actives TX remoto en una red no confiable. Si expones el puerto fuera de la máquina local, configura una whitelist.

## Cuándo usar varias interfaces

Varias interfaces activas pueden funcionar en paralelo. El tráfico recibido se maneja por interfaz, mientras que la transmisión de radio depende del selector usado en cada pestaña. El tráfico recibido mediante APRS-IS aparece en el historial, los detalles de estación y el mapa, pero se excluye de todas las estadísticas de APRSBox.

Si solo necesitas entrada desde OpenWebRX, usa `OpenWebRX MQTT (RX only)`. Si necesitas RX/TX completo por radio, usa `TCP` o `SERIALL`. Para recibir y/o transmitir por la red APRS-IS, usa `APRS-IS (RX/TX)` y los flows adecuados de `Packet Routing`.
