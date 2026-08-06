# Avisos CAWF en APRSBox

CAWF, Common APRS Warning Format, es una envoltura compacta e independiente del país para distribuir avisos públicos territoriales como mensajes de grupo APRS. Esta guía describe CAWF v1 según el borrador proporcionado y después identifica el comportamiento y los límites del receptor APRSBox.

CAWF es un formato de transporte. No sustituye a la fuente nacional autorizada, CAP ni al perfil NWS-WARN.

## Modelo desde la fuente hasta el receptor

- Un CAWF HUB territorial lee una fuente autorizada y adapta el evento, la gravedad y las áreas según un perfil nacional publicado.
- Transmite uno o varios mensajes APRS a un grupo de avisos. El patrón recomendado es `CC-WARN`, por ejemplo `PL-WARN`.
- APRSBox recibe el grupo por RF o por el filtro APRS-IS ampliado automáticamente, ensambla fragmentos, aplica umbrales, guarda la alarma y une los códigos de área con geometría GeoJSON local.
- Los grupos de aviso son destinos de difusión. APRSBox no envía ACK.

## Carga útil CAWF v1

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]{MESSAGE_ID
```

APRSBox también acepta y genera la extensión opcional de comentario:

```text
EXPIRY,EVENT_LEVEL,ALERT_ID,PART/TOTAL,AREA[,AREA...]|COMMENT{MESSAGE_ID
```

Ejemplo:

```text
012300z,TSTORM2,@3569,1/2,0609,1206,1409{A6474
```

Una carga conforme usa el orden fijo y tokens de protocolo ASCII en mayúsculas salvo la `z` minúscula literal. La extensión opcional de comentario de APRSBox empieza después de `|`, puede contener espacios y se translitera a ASCII seguro para APRS. La carga completa tiene un máximo de 67 caracteres incluido el identificador APRS.

## Campos

- `EXPIRY` tiene formato `DDHHMMz`: día, hora y minuto UTC. APRSBox resuelve mes y año como la aparición válida más próxima a la recepción. Un valor imposible o dañado no puede caducar automáticamente.
- `EVENT_LEVEL` combina el código de evento y el nivel final de un dígito, por ejemplo `TSTORM2`.
- `ALERT_ID` es `@` y cuatro caracteres hexadecimales mayúsculos. Todos los fragmentos de una alarma lógica lo comparten. Su ámbito es indicativo de origen más grupo más ID; no es globalmente único.
- `PART/TOTAL` comienza en `1/1`. Los números de parte son únicos, `PART` no supera `TOTAL` y todos los fragmentos deben declarar el mismo total.
- `AREA` contiene entre 1 y 8 letras mayúsculas, dígitos o guiones. Los ceros iniciales son significativos y el código debe coincidir exactamente con el identificador geométrico del perfil.
- `COMMENT` es texto opcional legible después de `|`, limitado a ASCII seguro para APRS. APRSBox calcula su capacidad con la carga generada completa y lo divide mediante el mecanismo multiparte CAWF habitual.
- `MESSAGE_ID` son cinco caracteres hexadecimales mayúsculos tras `{`. Identifica un fragmento, no la alarma completa. Una retransmisión idéntica conserva el ID; un fragmento cambiado necesita uno nuevo. No hay llave de cierre.

Para interoperabilidad, APRSBox acepta un identificador APRS alfanumérico algo más amplio, pero los emisores deben usar la forma estricta de CAWF v1.

## Gravedad y registro de eventos

CAWF v1 define niveles activos:

```text
1 = amarillo
2 = naranja
3 = rojo
```

El nivel `0` significa que no hay aviso activo y no debe transmitirse como CAWF activo. El nivel `4` está reservado. El perfil nacional debe documentar el mapeo desde la fuente autorizada a 1–3.

Registro inicial de eventos CAWF:

```text
TSTORM WIND RAIN FLOOD FFLOOD SNOW ICE HEAT COLD FOG
COASTAL AVALANC FIRE DUST OTHER
```

APRSBox conserva el código exacto y usa prefijos conocidos para elegir categoría e icono. Los códigos sin categoría propia permanecen visibles en `Otro / desconocido` y usan sus umbrales.

## Ensamblaje y duplicados

- Los fragmentos pueden llegar desordenados. APRSBox los agrupa por indicativo de origen, grupo de destino y `ALERT_ID`.
- El registro de Alertas contiene la unión de códigos de área únicos y muestra partes recibidas frente a declaradas.
- Pasa a `completa` después de recibir todas las partes desde 1 hasta `TOTAL`; antes es `incompleta`.
- Un fragmento repetido con el mismo ID APRS se relaciona con la alarma existente y se cuenta sin crear otra alarma lógica.
- El borrador CAWF recomienda abandonar un ensamblaje incompleto a los 15 minutos. APRSBox lo conserva actualmente hasta la caducidad normal o el borrado manual; por ello debe revisarse el estado de completitud.

## Ciclo de vida

- El primer fragmento activa o crea la alarma lógica si el umbral de Alertas lo permite.
- Los demás fragmentos y repeticiones exactas actualizan el mismo registro y mantienen enlaces a sus tramas del Monitor de tráfico.
- Reutilizar el mismo `ALERT_ID` actualiza el registro limitado a ese origen y grupo. El emisor debe evitar su reutilización durante al menos 48 horas después de caducar.
- En `EXPIRY`, APRSBox desactiva la alarma pero conserva tramas e historial.
- APRSBox cancela con la misma envoltura, `EVENT_LEVEL` igual a `CANCEL` y el mismo indicativo de origen, grupo, `ALERT_ID`, caducidad y código de área. El receptor limita la cancelación por origen, grupo e ID, de modo que otra estación no puede cancelar la alarma del emisor reutilizando su ID corto.

## Perfiles nacionales y geometría

Un perfil debe publicar operador del grupo, fuente autorizada, indicativos emisores, mapeos de eventos y gravedad, significado de códigos, versión geométrica, políticas de validez y repetición y vía de contacto.

Para un grupo `CC-WARN`, APRSBox busca GeoJSON local en el directorio del código de país de dos letras. La geometría debe ser `Polygon` o `MultiPolygon` WGS84 y su identificador debe coincidir exactamente con `AREA`. `PL-WARN` tiene un conjunto dedicado de distritos polacos.

Un código desconocido permanece en la alarma, pero se omite del mapa. Si varias alarmas activas afectan a la misma geometría, el nivel conocido más alto determina el color y se muestran todas las alarmas contribuyentes.

## Confianza y seguridad operativa

CAWF v1 no aporta autenticación criptográfica. El borrador recomienda una lista de emisores de confianza por grupo y documentación pública del operador y la fuente. APRSBox no aplica actualmente esa lista, de modo que cualquier remitente puede dirigirse a un grupo configurado.

APRS debe tratarse como canal secundario de conciencia situacional. Confirme los avisos de gran impacto con la agencia autorizada, especialmente si el remitente es inesperado, la alarma está incompleta, la caducidad es inválida o falta geometría. Recibir por APRS-IS prueba el transporte, no la autenticidad.

## Fuentes

- Archivos proporcionados `CAWF.md` y `CAWF-PL.md`, borrador CAWF v1.
- [TAPR APRS Protocol Reference — reglas de boletines NWS y mensajes](https://files.tapr.org/software_library/aprs/aprsspec/spec/aprs101g/APRS101g.pdf).
- [Documentación del servicio de alertas NWS CAP](https://www.weather.gov/documentation/services-web-alerts), usada para distinguir una alerta autorizada completa de su transporte APRS compacto.

[Volver a la configuración de alarmas APRS](settings_alarms.es.md)
