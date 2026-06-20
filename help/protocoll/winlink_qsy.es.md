# Objetos Winlink en APRS

El objetivo de estos objetos es mostrar recursos locales de radio de una forma legible para operadores móviles y lo más compatible posible con la práctica de APRS Frequency Objects. El objeto debe ayudar a responder preguntas simples:

- dónde se encuentra el recurso,
- en qué frecuencia trabaja,
- qué parámetros de acceso requiere,
- cuál es su estado o una breve descripción.

Los objetos de este tipo deben tener significado local. No deben transmitirse mucho más allá del área donde el recurso resulta realmente útil.

## 1. Cuándo usar este tipo de objeto

Un objeto Winlink se utiliza para describir un punto local de acceso por radio a Winlink, por ejemplo una pasarela packet. No es un objeto típico de repetidor de voz. Su objetivo es mostrar al operador dónde está el recurso local Winlink y con qué parámetros puede conectarse a él.

La información más importante:

- el indicativo o identificador de la pasarela,
- la frecuencia de trabajo,
- la velocidad packet,
- cualquier offset o nota local,
- un comentario corto.

## 2. Ejemplo de trama de objeto

Ejemplo esquemático:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
```

La trama se compone de varias partes:

```text
;WL-SR5ABC*111111z5215.00NW02055.00Ea144.950MHz 1200 -000 Winlink
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- breve descripción
|        | |      |        | |        | |          |    +------- offset / información adicional
|        | |      |        | |        | |          +------------ velocidad packet
|        | |      |        | |        +----------------------- símbolo
|        | |      |        | +-------------------------------- longitud
|        | |      |        +---------------------------------- tabla de símbolos Winlink
|        | |      +------------------------------------------- latitud
|        | +-------------------------------------------------- marca de tiempo
|        +---------------------------------------------------- nombre del objeto
+------------------------------------------------------------- tipo de trama: objeto
```

## 3. Nombre del objeto

Para objetos Winlink se usan nombres:

```text
WL-CALL
W1-CALL
W2-CALL
...
W9-CALL
```

Ejemplos:

```text
WL-SR5ABC
W1-SR5ABC
W2-SP9XYZ
```

`WL-` significa el objeto Winlink básico. Las variantes `W1-` a `W9-` pueden usarse cuando existen varios objetos asociados con el mismo indicativo o la misma ubicación.

El nombre debe ser corto y legible, porque aparece en la lista de objetos.

## 4. Marca de actividad y tiempo

Para un objeto activo se usa:

```text
*
```

Para un objeto fijo se usa a menudo:

```text
111111z
```

Ejemplo:

```text
;WL-SR5ABC*111111z
```

## 5. Coordenadas y símbolo

En el formato Winlink se usan la tabla de símbolos `W` y el símbolo `a`:

```text
5215.00NW02055.00Ea
```

Desglose:

```text
5215.00N   latitud
W          tabla de símbolos Winlink
02055.00E  longitud
a          símbolo
```

Si no debe publicarse la posición exacta de la pasarela, puede usarse una posición aproximada dentro del área donde el recurso es útil.

## 6. Frecuencia

La frecuencia se indica en el comentario:

```text
144.950MHz
```

Formato recomendado:

```text
xxx.xxxMHz
```

Ejemplos:

```text
144.950MHz
145.050MHz
430.525MHz
```

## 7. Velocidad packet

En un objeto Winlink, el lugar donde en repetidores de voz suele aparecer el tono se usa en cambio para la velocidad packet.

Ejemplos:

```text
1200
9600
```

Ejemplo de comentario:

```text
144.950MHz 1200 -000 Winlink
```

## 8. Offset y comentario

Después de la velocidad se puede añadir el offset o una breve información adicional.

Ejemplos:

```text
-000    sin offset, simplex
+060    offset +600 kHz
-060    offset -600 kHz
```

El comentario final debe ser corto:

```text
Winlink
RMS
Packet
SR5ABC
```

## 9. Orden recomendado de los campos

Para la legibilidad conviene mantener el orden:

```text
frecuencia velocidad offset/descripción comentario-corto
```

Ejemplo:

```text
144.950MHz 1200 -000 Winlink
```

Otros ejemplos:

```text
145.050MHz 1200 -000 RMS
430.525MHz 9600 -000 Winlink
144.950MHz 1200 Packet SR5ABC
```

## 10. Buenas prácticas

- Recuerda que Winlink es un recurso packet/data, no un repetidor de voz.
- En el nombre usa `WL-` o `W1-` a `W9-` y un indicativo o identificador corto.
- En el comentario indica la frecuencia en formato `xxx.xxxMHz`.
- Indica la velocidad packet, por ejemplo `1200` o `9600`.
- No pongas tono CTCSS en lugar de la velocidad packet si el objeto describe un punto típico Winlink packet.
- La descripción final debe ser corta.

## 11. Guía rápida

```text
;             inicio del objeto
WL-SR5ABC     nombre básico del objeto Winlink
W1-SR5ABC     variante adicional
*             objeto activo
111111z       marca de tiempo fija
W             tabla de símbolos Winlink
a             símbolo Winlink
144.950MHz    frecuencia
1200          velocidad packet
9600          velocidad packet
-000          simplex / sin offset
Winlink       breve descripción
```
