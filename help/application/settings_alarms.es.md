# Configuración de alarmas APRS

Este panel controla la recepción de alarmas, su traslado a la lista de Alertas, las ventanas emergentes de emergencia y el filtro APRS-IS automático para grupos de alarma.

## Interruptor principal y grupos

- `Habilitar alarmas APRS` activa o desactiva el procesamiento de alarmas.
- `Grupos de alarma` acepta uno o más nombres de grupo APRS separados por comas.
- Los grupos guardados se añaden a los grupos efectivos de recepción RF y al filtro automático de grupos APRS-IS.

El resumen situado bajo el formulario muestra los grupos RF efectivos y el filtro automático exacto generado por la configuración guardada.

## Umbrales por tipo de evento

Cada categoría tiene dos umbrales independientes:

- `Alertas` controla el traslado desde Mensajes a la lista de Alertas.
- `Ventana de alerta` controla la ventana emergente de estilo emergencia.
- Un valor numérico acepta esa gravedad y todas las superiores.
- `Desactivado` deshabilita la categoría en esa columna.

Los niveles de gravedad desconocidos se conservan por seguridad en lugar de descartarse silenciosamente.

La visibilidad de alarmas en el mapa se gestiona directamente desde el panel de alarmas de la página Mapa. Estos ajustes no sustituyen ese control.
