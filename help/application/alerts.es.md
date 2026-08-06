# Alarmas de emergencia APRS

La pestaña `Alarmas` muestra alarmas lógicas creadas a partir de tramas APRS de emergencia recibidas. Las tramas posteriores del mismo indicativo de origen completo actualizan una sola alarma y su historial.

- Al hacer clic en una fila se abre el modal con la trama de emergencia más reciente.
- El botón de detalles de la alarma abre el registro completo y el historial de tramas relacionadas.
- Silenciar no detiene las actualizaciones de la alarma ni el contador de tramas.
- Eliminar una alarma no borra las tramas originales del monitor de tráfico.

## Sonido de alarma en el navegador

Los navegadores pueden bloquear de forma predeterminada la reproducción automática de audio. En ese caso el modal de alarma aparece correctamente, pero el sonido comienza solo después de hacer clic en la página.

En el ordenador que muestra APRSBox:

1. Abre los permisos del sitio junto a la barra de direcciones.
2. Busca el ajuste `Reproducción automática`.
3. Selecciona `Permitir audio y vídeo` o la opción equivalente que permita sonido.
4. Recarga la pestaña de APRSBox.

Este permiso debe configurarse en el navegador del ordenador de visualización. El servidor APRSBox puede ejecutarse en otro dispositivo.

Comprueba también que la pestaña, el navegador y el sistema operativo no estén silenciados y que esté seleccionada la salida de audio correcta.

Después de permitir la reproducción automática, una trama de emergencia no silenciada abre el modal e inicia el sonido sin un clic adicional. Una alarma silenciada continúa actualizándose, pero permanece en silencio de forma intencionada.

## Silenciar

Las alarmas pueden silenciarse durante `1 hora`, `4 horas`, `24 horas` o indefinidamente. Cuando termina un silencio temporal, solo una trama de emergencia posterior puede abrir el modal e iniciar el sonido.

## Eliminar

La eliminación borra el registro lógico de la alarma y sus relaciones. Las tramas originales permanecen en el monitor de tráfico. La siguiente trama de emergencia de ese origen crea una alarma nueva.
