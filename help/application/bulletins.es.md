# Boletines y anuncios

Este documento describe el uso basico de la pestaña `Bulletins / Announcements` en APRSBox.

Esta pantalla se utiliza para preparar tramas APRS en formato de mensaje para boletines y anuncios.

## Casos de uso

Los boletines y anuncios son utiles para informacion breve, por ejemplo:

- avisos de club y de operadores,
- mensajes organizativos cortos,
- recordatorios de eventos,
- avisos tecnicos o meteorologicos locales.

## Campos basicos

- `Type` selecciona el tipo de entrada.
- `Code` identifica el boletin o anuncio.
- `Group` asigna la entrada a un nombre corto de grupo.
- `Message` contiene el texto del comunicado.
- `Path` define la ruta APRS, si hace falta.
- `Send interval` y `Activation` controlan con que frecuencia y en que horario puede enviarse la trama.

## Reglas practicas breves

- Use codigos `0-9` para boletines generales y de grupo.
- Use codigos `A-Z` para anuncios.
- Mantenga el campo de grupo corto y legible.
- Mantenga el texto del mensaje breve y concreto.
- El texto debe caber en 67 caracteres y usar ASCII imprimible.
- Para transmisiones locales simples, dejar la ruta vacia suele ser la opcion mas segura salvo que la practica local requiera otra cosa.

## Notas

Los boletines APRS no son un buen lugar para descripciones largas. Los mensajes cortos y claros son mas faciles de leer en radios y clientes APRS simples.
