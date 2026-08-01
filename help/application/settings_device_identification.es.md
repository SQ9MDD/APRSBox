# Identificación de dispositivos APRS

APRSBox usa esta base para reconocer software y equipos APRS a partir de destinos `TOCALL` e identificadores Mic-E. El resultado aparece en los detalles de estación y las estadísticas de dispositivos.

## Fuente de datos activa

APRSBox prefiere una caché local válida. Si no existe, utiliza la copia incluida con la aplicación.

- `Estado` indica si está activa la caché o la copia incluida de respaldo.
- `Fuente activa` muestra el origen usado actualmente en las búsquedas.
- `Tiempo de generación` es la marca temporal incorporada al conjunto de identificación.
- `Última actualización correcta` registra la descarga completada más reciente.
- `Caché local` y `Caché local actualizada` describen el archivo descargado.
- `Último error de actualización` permanece visible después de un intento fallido.

## Actualización

`Actualizar ahora` descarga un conjunto nuevo, valida su estructura y solo después sustituye la caché local. Una descarga fallida no elimina la copia incluida utilizable ni una caché anterior válida.

La actualización requiere acceso a la red y solo puede iniciarla un administrador u operador.
