# Boletines y anuncios

Esta pantalla se utiliza para preparar tramas APRS en formato de mensaje para boletines y anuncios.

## Casos de uso

Los boletines y anuncios son utiles para informacion breve, por ejemplo:

- avisos de club y de operadores,
- mensajes organizativos cortos,
- recordatorios de eventos,
- avisos tecnicos o meteorologicos locales.

## Campos basicos

- `Tipo` selecciona el tipo de entrada, por ejemplo `Boletín general`, `Boletín de grupo` o `Anuncio`. Esto influye en como se construye el destinatario APRS y en que campos auxiliares son relevantes.
- `Código` identifica el boletin o anuncio con un solo caracter. Los boletines suelen usar digitos `0-9`, mientras que los anuncios usan letras `A-Z`, lo que facilita reconocer el tipo de mensaje en el lado receptor.
- `Grupo` asigna la entrada a un nombre corto de grupo, sobre todo para boletines de grupo. Este valor debe mantenerse corto, legible y estable porque pasa a formar parte del identificador visible para el receptor.
- `Texto del mensaje` contiene el texto real del comunicado enviado a la red APRS. Conviene escribir aqui un texto breve y claro para que pueda leerse comodamente en una radio o en un cliente APRS simple sin desplazamiento ni dudas de contexto.
- `Camino` define la ruta APRS si debe usarse en la transmision por RF. Para mensajes locales simples, dejar este campo vacio suele ser la opcion mas segura salvo que la practica local requiera una ruta concreta.
- `Intervalo de envío` define cada cuanto tiempo puede reenviarse la entrada. Este ajuste no decide cuando se permite transmitir, sino solo el intervalo entre emisiones repetidas mientras la entrada esta activa.
- `Modo de activación` selecciona el modo de activacion de la entrada. `Modo manual` significa activacion manual sin horario, `Programado` define una unica ventana continua de tiempo, y `Recurrente` se usa para un plan de actividad repetitivo.
- `Activo desde` define cuando la entrada pasa a estar activa en UTC. En modo `Programado` es el inicio de una sola ventana de actividad, mientras que en modo `Recurrente` es el primer momento de arranque de todo el ciclo.
- `Activo hasta` define cuando la entrada deja de estar activa en UTC. En modo `Programado` suele marcar el final de la ventana de transmision, mientras que en modo manual tambien puede usarse como limite adicional de validez.
- `Activo durante (horas)` define cuanto dura un ciclo activo individual en modo `Recurrente`. En otras palabras, fija la longitud de una ventana de transmision despues de cada inicio de ciclo.
- `Repetir cada` define cada cuanto se repite el ciclo en modo `Recurrente`. Junto con la unidad de repeticion, establece el intervalo entre inicios sucesivos de la ventana activa.
- `Unidad de repetición` define la unidad usada por `Repetir cada`, por ejemplo dias, semanas, meses o anos. Esto decide si la repeticion se calcula en pasos diarios o semanales simples, o en intervalos calendarios mas largos.

## Reglas practicas breves

- Use codigos `0-9` para boletines generales y de grupo.
- Use codigos `A-Z` para anuncios.
- Mantenga el campo de grupo corto y legible.
- Mantenga el texto del mensaje breve y concreto.
- El texto debe caber en 67 caracteres y usar ASCII imprimible.
- Para transmisiones locales simples, dejar la ruta vacia suele ser la opcion mas segura salvo que la practica local requiera otra cosa.
- En entradas con horario, conviene recordar que `Intervalo de envío` y `Modo de activación` trabajan juntos: el horario define cuando esta permitido transmitir y el intervalo define con que frecuencia se envia la entrada dentro de esa ventana.

## Notas

Los boletines APRS no son un buen lugar para descripciones largas. Los mensajes cortos y claros son mas faciles de leer en radios y clientes APRS simples.
