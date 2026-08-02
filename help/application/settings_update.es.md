# Actualización de la aplicación

Este panel comprueba la versión instalada de APRSBox y, en instalaciones compatibles, actualiza la aplicación desde el canal seleccionado.

## Canal de actualización

El canal identifica la rama de origen usada para comprobar versiones y actualizar. Un canal distinto del estable puede contener cambios incompletos o incompatibles; el aviso permanece visible mientras esté seleccionado.

`Guardar canal de actualización` cambia el origen de futuras comprobaciones y actualizaciones. Guardarlo no actualiza por sí solo la aplicación.

## Acciones

- `Comprobar versión` compara la versión instalada con el canal seleccionado sin modificar la instalación.
- `Actualizar aplicación` descarga el código de ese canal, ejecuta la inicialización de la base de datos y reinicia `aprsbox-core` y `aprsbox-web` al finalizar.
- La interfaz puede perder temporalmente la conexión durante el reinicio. El diálogo de progreso sigue la tarea en segundo plano e intenta reconectar.

## Instalaciones Docker

Dentro de Docker, la comparación de versiones es solo informativa y las acciones de actualización del host están deshabilitadas. Actualice APRSBox descargando la imagen necesaria y recreando el contenedor con la herramienta de despliegue utilizada.

Solo administradores y operadores pueden cambiar el canal o iniciar una actualización.
