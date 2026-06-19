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

- `Type` selecciona el tipo de entrada, por ejemplo boletin general, boletin de grupo o anuncio. Esto influye en como se construye el destinatario APRS y en que campos auxiliares son relevantes.
- `Code` identifica el boletin o anuncio con un solo caracter. Los boletines suelen usar digitos `0-9`, mientras que los anuncios usan letras `A-Z`, lo que facilita reconocer el tipo de mensaje en el lado receptor.
- `Group` asigna la entrada a un nombre corto de grupo, sobre todo para boletines de grupo. Este valor debe mantenerse corto, legible y estable porque pasa a formar parte del identificador visible para el receptor.
- `Message` contiene el texto real del comunicado enviado a la red APRS. Conviene escribir aqui un texto breve y claro para que pueda leerse comodamente en una radio o en un cliente APRS simple sin desplazamiento ni dudas de contexto.
- `Path` define la ruta APRS si debe usarse en la transmision por RF. Para mensajes locales simples, dejar este campo vacio suele ser la opcion mas segura salvo que la practica local requiera una ruta concreta.
- `Send interval` define cada cuanto tiempo puede reenviarse la entrada, mientras que `Activation` define cuando puede estar activa. En la practica, estos campos trabajan juntos: uno controla el intervalo entre transmisiones y el otro la ventana de tiempo en la que el envio esta permitido.

## Reglas practicas breves

- Use codigos `0-9` para boletines generales y de grupo.
- Use codigos `A-Z` para anuncios.
- Mantenga el campo de grupo corto y legible.
- Mantenga el texto del mensaje breve y concreto.
- El texto debe caber en 67 caracteres y usar ASCII imprimible.
- Para transmisiones locales simples, dejar la ruta vacia suele ser la opcion mas segura salvo que la practica local requiera otra cosa.

## Notas

Los boletines APRS no son un buen lugar para descripciones largas. Los mensajes cortos y claros son mas faciles de leer en radios y clientes APRS simples.
