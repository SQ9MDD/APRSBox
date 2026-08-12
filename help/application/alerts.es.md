# Alarmas de emergencia APRS

La pestaña `Alarmas` muestra alarmas lógicas creadas a partir de tramas APRS de emergencia nativas y mensajes de grupo CAWF o `NWS-WARN`. Todas aparecen en la misma lista y ofrecen detalles, historial de tramas, silencio y eliminación.

`NWS-WARN` sirve para recibir avisos meteorológicos compactos por condados de Estados Unidos. Los detalles incluyen, entre otros datos, el evento, el nivel, la caducidad y los códigos de área UGC; APRSBox resalta en el mapa los condados reconocidos. Es un perfil de solo recepción: APRSBox no puede enviar ni cancelar una alarma `NWS-WARN`. La configuración del grupo, el formato, los niveles, el mapeo de áreas y las limitaciones se explican en la [guía detallada de NWS-WARN](settings_alarms_nws_warn.es.md).

## Interpretación del código de evento y el nivel

Los detalles de la alarma mantienen visible el código original junto a su descripción. En CAWF, la descripción se obtiene del registro de eventos CAWF v1 y los niveles `1`, `2` y `3` significan amarillo, naranja y rojo. Un código fuera del registro o un nivel fuera de esa escala se marca como no reconocido.

En `NWS-WARN`, el nombre del evento es texto libre proporcionado por el remitente. APRSBox puede asignar un nombre reconocido a una categoría descriptiva, pero esto no sustituye al producto oficial de NWS. Un dígito final es el mapeo 1–3 elegido por el publicador del repetidor, no una gravedad oficial de NWS CAP. Consulta las guías de [CAWF](settings_alarms_cawf.es.md) y [NWS-WARN](settings_alarms_nws_warn.es.md).

- Al hacer clic en una fila se abre el modal con la trama de alarma más reciente.
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

Después de permitir la reproducción automática, una trama no silenciada que cumpla el umbral de ventana de alerta abre el modal e inicia el sonido sin un clic adicional. Esto también se aplica a `NWS-WARN` cuando su categoría y nivel cumplen el umbral configurado. Una alarma silenciada continúa actualizándose, pero permanece en silencio de forma intencionada.

## Silenciar

Las alarmas pueden silenciarse durante `1 hora`, `4 horas`, `24 horas` o indefinidamente. Cuando termina un silencio temporal, solo una trama posterior de esa alarma puede abrir el modal e iniciar el sonido.

## Eliminar

La eliminación borra el registro lógico de la alarma y sus relaciones. Las tramas originales permanecen en el monitor de tráfico. Una trama posterior que coincida puede volver a crear la alarma.
