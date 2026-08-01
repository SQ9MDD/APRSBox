# Fuentes del mapa

Este panel gestiona las fuentes de mosaicos disponibles en los mapas de APRSBox, su orden, la fuente predeterminada y la caché local opcional.

## Lista de fuentes

- Las flechas cambian el orden de las fuentes en el selector del mapa.
- La estrella convierte una fuente habilitada en predeterminada.
- El lápiz abre una fuente para editarla.
- La papelera elimina una fuente. No se puede eliminar la única fuente ni la predeterminada actual.
- La escoba borra los mosaicos almacenados localmente sin eliminar la configuración.

## Campos de la fuente

- `Nombre` es la etiqueta mostrada en el selector del mapa.
- `Plantilla de URL` debe ser una URL estándar de mosaicos Leaflet con `{z}`, `{x}` e `{y}`, por ejemplo `https://server/{z}/{x}/{y}.png`.
- `Atribución` contiene el crédito del proveedor que debe mostrarse en el mapa.
- `Zoom mínimo` y `Zoom máximo` limitan el intervalo de ampliación.
- `Notas` se guardan con la fuente para los administradores.
- `Habilitado` hace que la fuente esté disponible en los mapas.
- `Habilitar caché/proxy local` dirige las solicitudes a través de APRSBox y guarda localmente los mosaicos descargados.
- `Establecer como predeterminado` elige esta fuente cuando el mapa no tiene otra selección guardada.

Aquí solo se admiten proveedores estándar de mosaicos ráster Leaflet. Compruebe límites de uso, reglas de atribución y permiso para caché mediante proxy antes de habilitarlos. Un punto de partida es la [lista de proveedores de Switch2OSM](https://switch2osm.org/providers/#Allows-free-usage).
