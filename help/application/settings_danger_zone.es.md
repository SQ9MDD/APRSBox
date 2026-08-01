# Zona de peligro

Estas acciones afectan a servicios en ejecución o a todo el host. Solo están disponibles para administradores y operadores y se deshabilitan dentro de Docker.

## Reiniciar servicios

Reinicia `aprsbox-core` y `aprsbox-web`. El procesamiento de radio y web se pausa, y el navegador puede perder brevemente la conexión.

## Reiniciar el host

Reinicia el sistema operativo. Todos los servicios APRSBox y el acceso remoto se interrumpen. El diálogo de confirmación exige el texto exacto `REBOOT`.

## Apagar el host

Apaga el sistema operativo. El acceso remoto se interrumpe y puede ser necesario acceso físico o fuera de banda para volver a encender el equipo. El diálogo de confirmación exige el texto exacto `POWER OFF`.

En Docker, reinicie o recree el contenedor mediante Docker o la plataforma de despliegue en lugar de usar estas acciones del host.
