# Avisos NWS-WARN en APRSBox

`NWS-WARN` es el perfil de recepción específico de APRSBox para avisos compactos por condados de Estados Unidos dirigidos al grupo APRS `NWS-WARN`. Es una envoltura de retransmisión APRS, no una conexión directa con el National Weather Service ni un producto completo NWS CAP o VTEC.

APRSBox no descarga alertas de `api.weather.gov`; solo interpreta tramas APRS recibidas por una interfaz RF o APRS-IS configurada.

## Configuración

- Active las alarmas APRS y añada el grupo exacto `NWS-WARN`.
- Defina el umbral de Alertas para las categorías necesarias. Sin él, la trama permanece en el Monitor de tráfico pero no crea un registro NWS-WARN.
- Active umbrales de ventana solo para categorías que deban interrumpir al operador.
- Compruebe que el filtro APRS-IS automático contiene `g/NWS-WARN` y que la interfaz receptora está activa.

## Forma de paquete interpretada

```text
SOURCE>APRS,...::NWS-WARN :DDHHMMz,EVENTLEVEL,SSCnnn[,SSCnnn...]{MSGID
```

```text
NWSWX>APRS,TCPIP*::NWS-WARN :010200z,TORNADO3,TNC037,TNC189{N1001
```

El campo APRS de nueve caracteres contiene `NWS-WARN` rellenado con un espacio. Al ser un boletín de grupo, APRSBox nunca envía ACK.

## Campos interpretados

- `DDHHMMz` es día, hora y minuto de caducidad UTC. APRSBox elige el mes y año válidos más próximos a la recepción. Se requiere `z` o `Z` para la caducidad automática.
- `EVENTLEVEL` es la etiqueta del evento. El material APRS histórico define el tipo como texto libre; APRSBox además lee los dígitos finales como gravedad. Para umbrales y colores previsibles, use un código normalizado terminado en `1`, `2` o `3`, por ejemplo `TORNADO3`.
- `SSCnnn` es un Universal Geographic Code NWS en forma de condado. Varios condados separados por comas forman una alarma.
- `MSGID` es un identificador APRS alfanumérico de 1–5 caracteres. Sirve para deduplicar, es solo referencia y no solicita ACK.

El texto meteorológico APRS histórico describía también etiquetas basadas en nombres y un máximo de cinco campos. El perfil cartográfico actual de APRSBox espera códigos UGC estables para unirlos de forma fiable con la geometría.

## Códigos UGC de condado

El código aceptado en el mapa tiene seis caracteres:

```text
SS C nnn
```

- `SS` identifica un estado o territorio de EE. UU.
- `C` significa county, parish o independent city.
- `nnn` es la parte de condado de tres dígitos del identificador FIPS.
- `TNC037` identifica así Davidson County, Tennessee.

NWS también usa `Z` para zonas públicas de pronóstico y áreas marinas. APRSBox solo cartografía códigos de condado que coinciden con `[A-Z]{2}C[0-9]{3}`. `TNZ037` o `ANZ630` permanece guardado pero no se dibuja. Un código válido ausente de la geometría incluida, desconocido u obsoleto, también se omite del mapa.

Los límites de condado NWS cambian. Si un código oficial no se dibuja, compare la versión geométrica instalada en APRSBox con el conjunto GIS vigente de NWS.

## Gravedad y umbrales

APRSBox aplica la escala compartida:

```text
1 = amarillo
2 = naranja
3 = rojo
```

El sufijo numérico es una convención de transporte APRSBox/CAWF, no el modelo completo de gravedad NWS CAP ni un mapeo definido en la sintaxis APRS NWS histórica. El operador del retransmisor debe documentar cómo transforma el producto oficial en 1–3.

Si falta el sufijo o está fuera de 1–3, la gravedad es desconocida. Si la categoría está activa, APRSBox conserva la alarma y la geometría es gris. Los prefijos conocidos seleccionan la categoría; un nombre no reconocido usa `Otro / desconocido`.

## Ciclo de vida, repeticiones y cancelación

- Una trama aceptada crea una alarma con todos los códigos y un enlace a la trama de origen del Monitor de tráfico.
- El mismo remitente, grupo e ID APRS identifican una repetición. Se actualizan contadores y última recepción sin crear un duplicado.
- Un ID nuevo no comparte en esta envoltura un identificador lógico del evento NWS. APRSBox lo trata como alarma separada aunque evento y condados sean iguales.
- Un `DDHHMMz` resuelto desactiva la alarma al caducar; se conservan tramas e historial.
- La familia APRS histórica incluye `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` y `NWS-CANCL`. APRSBox solo tiene geometría dedicada de condados para `NWS-WARN` y no interpreta `NWS-CANCL` como cancelación de una alarma existente.
- Una caducidad ausente o inválida puede dejar la alarma activa hasta el borrado manual. Revise el detalle si la trama está dañada.

## Contenido perdido frente a los datos oficiales

Los servicios oficiales NWS distribuyen watches, warnings, advisories y productos similares en CAP v1.2. Pueden incluir titular, descripción, instrucciones, urgencia, gravedad, certeza, tiempos, zonas UGC, polígonos y estado VTEC.

La envoltura compacta solo lleva caducidad, token de evento y nivel, códigos de condado, remitente e ID APRS. No puede reconstruir instrucciones, polígonos, certeza, acciones VTEC, identificadores oficiales ni relaciones de actualización omitidas. Para decisiones operativas use el producto NWS oficial vinculado cuando esté disponible.

## Confianza y uso seguro

El destino `NWS-WARN` no demuestra que el remitente sea el National Weather Service. APRS y APRS-IS no autentican criptográficamente esta envoltura y APRSBox no dispone actualmente de una lista de remitentes de confianza por grupo.

Trate la trama como información situacional secundaria. Verifique los avisos de gran impacto en un servicio oficial NWS, sobre todo si el indicativo es desconocido, el mapeo de nivel no está documentado, la caducidad es inválida o falta geometría.

## Fuentes

- [TAPR APRS Protocol Reference — dirección de boletines NWS y ausencia de ACK](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- Referencia meteorológica APRS histórica incluida `APRS-SPEC/WX.TXT`, con `NWS-WARN`, `NWS-WATCH`, `NWS-ADVIS`, `NWS-TEST` y `NWS-CANCL`.
- [Directiva NOAA/NWS sobre Universal Geographic Code](https://www.weather.gov/media/directives/010_pdfs_archived/pd01017002b.pdf).
- [Conjunto GIS NOAA/NWS U.S. Counties](https://www.weather.gov/gis/Counties).
- [Documentación del servicio de alertas NWS CAP](https://www.weather.gov/documentation/services-web-alerts).
- [Documentación NWS VTEC](https://www.weather.gov/vtec/).

[Volver a la configuración de alarmas APRS](settings_alarms.es.md)
