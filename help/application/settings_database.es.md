# Mantenimiento de la base de datos

Este panel informa del estado del almacenamiento SQLite y ofrece tareas manuales de limpieza. Los registros de eventos se recortan automáticamente después de medianoche; `VACUUM` y el reinicio del historial de ejecución siguen siendo manuales.

## Diagnóstico

- Los tamaños de archivo, WAL y SHM muestran el espacio físico usado por SQLite.
- `Tamaño asignado`, `Espacio recuperable` y `Geometría de páginas` se calculan a partir de las páginas SQLite.
- `Comprobación de integridad` es el resultado de `PRAGMA quick_check`. Investigue cualquier resultado distinto de `ok` antes del mantenimiento.
- `Recomendación de VACUUM` compara el espacio recuperable con el umbral mostrado.
- La lista de tablas de ejecución y el total de filas muestran el alcance exacto actual del reinicio.

## Ejecutar VACUUM

`VACUUM` reconstruye el archivo SQLite para devolver al sistema de archivos las páginas no utilizadas. Puede tardar y bloquear temporalmente la base de datos. Todas las interfaces TNC deben estar deshabilitadas antes de ejecutarlo.

## Reiniciar registros/datos de ejecución

El reinicio borra historial operativo como registros de eventos, tráfico recibido, estado de ejecución del enrutamiento, estadísticas APRS-IS, caché WX, estado del radar y agregados de condiciones de banda.

No elimina la configuración TNC ni de enrutamiento, los ajustes de estación y WX, el contenido APRS, las fuentes de mapas, usuarios ni el historial de mensajes APRS. Todas las interfaces TNC deben estar deshabilitadas antes del reinicio.
