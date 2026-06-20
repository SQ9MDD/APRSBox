# Boletines y anuncios APRS

Esta pantalla sirve para preparar mensajes cortos de difusión APRS en formato de mensaje. Los boletines y anuncios no son mensajes privados para una sola estación.
Están destinados a varios destinatarios, por ejemplo operadores locales, participantes de un evento, un grupo de club o estaciones dentro del alcance de radio.

## 1. Teoría

### Qué es un boletín APRS

Un boletín APRS es una información de texto corta enviada a varios destinatarios. Puede contener un mensaje de club, organizativo, técnico, meteorológico o cualquier otra información útil durante una actividad local de radio.

Un boletín no es una conversación de texto y no debe sustituir una descripción larga, un sitio web ni un mensaje privado para una persona concreta. Su función es transmitir rápidamente una información que tiene valor aquí y ahora.

Buenos usos de los boletines:

- información sobre una red local o una reunión,
- un mensaje para los participantes de un evento,
- información de club,
- un aviso corto sobre la operación de un repetidor, digi, iGate o estación de campo,
- un aviso técnico local,
- una información meteorológica u organizativa breve.

Ejemplos de buenos mensajes:

```text
NET 19:00 local repeater SR5XXX
HAMFEST parking on 145.550
WX alert: strong wind until 18 UTC
APRS test 12:00-14:00 local area
```

### Qué es un anuncio APRS

Un anuncio es parecido a un boletín, pero normalmente tiene un carácter más informativo o de aviso. En la práctica puede servir para publicar avisos cortos sobre actividades, eventos o información local importante.

Para el usuario, la diferencia más importante es simple:

```text
boletín       información breve de difusión, normalmente numerada con una cifra
anuncio       información breve marcada con una letra
```

### Boletín frente a un mensaje APRS normal

Un mensaje APRS normal va dirigido a un indicativo concreto. Un boletín o anuncio va dirigido a un destinatario especial del tipo `BLN`, por lo que los clientes APRS pueden reconocerlo como un mensaje de difusión.

Un boletín:

- no es un mensaje privado,
- no es un chat típico,
- no debería requerir respuesta de una estación concreta,
- debería ser corto y comprensible sin contexto adicional.

## 2. Compatibilidad con el protocolo APRS

Los boletines y anuncios se envían como tramas APRS en formato de mensaje. Se diferencian de un mensaje normal en que el campo de destinatario contiene un identificador especial que empieza por `BLN`.

Identificadores típicos:

```text
BLN0       boletín general número 0
BLN1       boletín general número 1
BLNA       anuncio marcado con la letra A
BLN0GRP    boletín de grupo, ejemplo con grupo corto GRP
```

El campo de destinatario APRS tiene longitud limitada, por eso el código y el nombre del grupo deben ser cortos. No merece la pena crear identificadores largos o no estándar,
porque radios antiguos y clientes APRS simples pueden no mostrarlos de la forma esperada.

Para compatibilidad y legibilidad, lo mejor es usar:

```text
0-9    para boletines generales y de grupo
A-Z    para anuncios
```

El texto del mensaje debe caber dentro del límite de un mensaje APRS corto. Una práctica segura es mantenerse dentro de un máximo de 67 caracteres y usar ASCII imprimible.
Conviene evitar caracteres nacionales, símbolos especiales y formato, porque algunas radios y clientes APRS antiguos pueden no mostrarlos correctamente.

## 3. Reglas de buen uso

APRS fue diseñado como un sistema de información operativa actual. Un buen boletín debería responder a la pregunta: ¿esta información es útil para las estaciones que la reciben aquí y ahora?

Mejores prácticas:

- escribe de forma breve y concreta,
- transmite información útil a nivel local u operativo,
- usa lenguaje simple,
- evita descripciones largas,
- evita repetir con demasiada frecuencia,
- no uses boletines como publicidad sin valor para los operadores locales,
- no envíes contenido que estaría mejor en una web, un correo o un mensajero.

Un buen boletín APRS es un mensaje corto con valor actual para operadores locales, no un texto enviado a la red solo porque técnicamente se puede transmitir.

### Intervalo de envío

El intervalo debe elegirse con sensatez. Un boletín debe recordar una información importante, pero no debería ocupar constantemente el canal de radio.

Para transmisiones RF locales, evita intervalos demasiado cortos. Si el mensaje no es urgente, es mejor enviarlo con menos frecuencia.
En eventos y actividades de campo, un buen enfoque es definir una ventana de actividad y usar un intervalo de repetición moderado.

### Camino APRS

Para transmisiones locales simples, lo más seguro es dejar el camino vacío o usar ajustes acordes con la práctica local.
Un camino demasiado amplio puede cargar innecesariamente el canal de radio y hacer que un mensaje local llegue más lejos de lo necesario.

Si el mensaje está destinado solo a APRS-IS, normalmente el camino RF no importa.

### Grupos

El grupo tiene sentido cuando el mensaje está destinado a una comunidad concreta, un evento, un club o una actividad local. El nombre del grupo debería ser corto, estable y fácil de reconocer.

Buenos nombres de grupo:

```text
CLUB
FIELD
ARES
EVENT
SP5
```

Nombres de grupo menos adecuados:

```text
nombre_de_grupo_muy_largo
reunion_del_club_2026
texto con espacios y caracteres especiales
```

## 4. Manejo del formulario

### Tipo

El campo `Tipo` selecciona la clase de entrada.

Opciones típicas:

```text
Boletín general
Boletín de grupo
Anuncio
```

El tipo seleccionado determina cómo se construye el destinatario APRS y cuál es el significado de los campos auxiliares.

### Código

El campo `Código` marca un boletín o anuncio con un solo carácter.

Uso recomendado:

```text
0-9    para boletines
A-Z    para anuncios
```

Ejemplos:

```text
0    primer boletín
1    segundo boletín
A    anuncio A
B    anuncio B
```

No cambies el código sin necesidad si el mensaje es una continuación de la misma información. Un código estable facilita que los receptores reconozcan que están viendo una actualización del mismo boletín o anuncio.

### Grupo

El campo `Grupo` se usa principalmente en los boletines de grupo. Permite limitar el significado del mensaje a un grupo concreto de destinatarios o a una actividad concreta.

El grupo debería ser:

- corto,
- legible,
- estable,
- escrito con caracteres ASCII simples.

Ejemplo:

```text
EVENT
CLUB
SP5
```

### Texto del mensaje

El campo `Texto del mensaje` contiene el mensaje APRS real.

El mejor texto es corto, inequívoco y comprensible sin contexto adicional. Recuerda que el mensaje puede leerse en la pequeña pantalla de una radio, no solo en una aplicación cómoda de escritorio.

Recomendaciones:

- máximo 67 caracteres,
- ASCII imprimible,
- sin caracteres nacionales,
- sin frases largas,
- sin formato,
- sin adornos innecesarios.

Buen ejemplo:

```text
NET 19:00 SR5XXX, check-ins welcome
```

Ejemplo menos adecuado:

```text
La reunión de nuestro grupo tendrá lugar esta tarde, los detalles están en el sitio web, por favor consulte allí toda la información.
```

### Camino

El campo `Camino` define el camino APRS usado en la transmisión RF.

Para mensajes locales simples, lo mejor es dejarlo vacío o usar solo el camino aceptado localmente.
No configures un camino amplio solo para que el mensaje llegue lo más lejos posible. Un boletín debería llegar donde tenga valor para sus destinatarios.

### Intervalo de envío

El campo `Intervalo de envío` define cada cuánto tiempo se puede volver a enviar el mensaje mientras está activo.

Este campo no decide por sí solo cuándo se permite transmitir el mensaje. El intervalo funciona junto con el modo de activación y el horario.

Ejemplo:

```text
Intervalo de envío: 30 minutos
Activo desde: 10:00 UTC
Activo hasta: 14:00 UTC
```

Esto significa que el mensaje puede enviarse cada 30 minutos solo dentro de la ventana entre las 10:00 y las 14:00 UTC.

### Modo de activación

El campo `Modo de activación` define cuándo la entrada está activa.

Modos típicos:

```text
Modo manual   la entrada se enciende y apaga manualmente
Programado    la entrada tiene una única ventana de actividad definida
Recurrente    la entrada vuelve regularmente según un plan repetitivo
```

### Activo desde

El campo `Activo desde` define el momento en el que la entrada pasa a estar activa en UTC.

En modo programado, es el inicio de una ventana de transmisión. En modo recurrente, es el primer inicio de todo el ciclo.

### Activo hasta

El campo `Activo hasta` define el momento en el que la entrada deja de estar activa en UTC.

En modo programado, es el final de una ventana de transmisión. En modo manual, puede servir como límite adicional de validez.

### Activo durante

El campo `Activo durante` define cuánto tiempo permanece activo un ciclo individual en modo recurrente.

Ejemplo:

```text
Activo durante: 3 horas
Repetir cada: 7 días
```

Esto significa que tras cada inicio de ciclo, el mensaje permanecerá activo durante 3 horas.

### Repetir cada

El campo `Repetir cada` define el intervalo entre inicios consecutivos del ciclo.

Ejemplo:

```text
Repetir cada: 1
Unidad de repetición: semana
```

Significa un ciclo repetido una vez por semana.

### Unidad de repetición

El campo `Unidad de repetición` define la unidad usada por `Repetir cada`.

Unidades típicas:

```text
días
semanas
meses
años
```

En el caso de meses y años, recuerda que se trata de unidades de calendario. No todos los meses tienen el mismo número de días.

## 5. Ejemplos de uso

### Boletín general

Uso: información corta para todos los destinatarios.

```text
Tipo: Boletín general
Código: 0
Texto del mensaje: NET 19:00 SR5XXX, check-ins welcome
Intervalo de envío: 30 minutos
```

Sentido de ejemplo:

```text
La red local comienza a las 19:00 en el repetidor SR5XXX.
```

### Boletín de grupo

Uso: mensaje para un grupo, evento o actividad concreta.

```text
Tipo: Boletín de grupo
Código: 1
Grupo: EVENT
Texto del mensaje: EVENT parking on 145.550 simplex
Intervalo de envío: 20 minutos
```

Sentido de ejemplo:

```text
Los participantes del evento encontrarán información sobre el canal de aparcamiento.
```

### Anuncio

Uso: un aviso corto o una información organizativa.

```text
Tipo: Anuncio
Código: A
Texto del mensaje: HAMFEST gates open 08:00 UTC
Intervalo de envío: 60 minutos
```

Sentido de ejemplo:

```text
El anuncio informa de la hora de apertura del evento.
```

## 6. Qué evitar

Evita:

- mensajes muy largos,
- caracteres nacionales y símbolos especiales,
- repetir con demasiada frecuencia,
- un camino amplio sin necesidad clara,
- mensajes no relacionados con la situación operativa local,
- contenido que debería ser un mensaje normal a una estación concreta,
- contenido que debería ir a una web, un correo o un mensajero.

Recuerda que el canal APRS por radio tiene capacidad limitada. Cada boletín transmitido debería tener sentido para sus destinatarios.

## 7. Guía rápida

```text
Boletín APRS       mensaje corto de difusión
Anuncio APRS       aviso corto o información
BLN                dirección especial usada para boletines y anuncios
0-9                códigos recomendados para boletines
A-Z                códigos recomendados para anuncios
Grupo              identificador corto de destinatarios o actividad
67 caracteres      límite seguro para el texto del mensaje
ASCII              conjunto de caracteres más seguro
Intervalo          con qué frecuencia repetir un mensaje activo
Activación         cuándo se puede transmitir el mensaje
```

## 8. Regla principal

Un boletín APRS debería ser corto, útil a nivel local y fácil de leer en equipos sencillos.
Si un mensaje requiere una explicación larga, muchas frases o enlaces a información adicional, probablemente no es adecuado como boletín APRS.
