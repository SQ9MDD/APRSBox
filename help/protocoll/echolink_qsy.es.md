# Objetos EchoLink en APRS

Este documento es un archivo de ayuda para un usuario que crea objetos APRS de frecuencia.

El objetivo de estos objetos es mostrar recursos locales de radio de una forma legible para operadores móviles y lo más compatible posible con la práctica de APRS Frequency Objects. El objeto debe ayudar a responder preguntas simples:

- dónde se encuentra el recurso,
- en qué frecuencia trabaja,
- qué parámetros de acceso requiere,
- cuál es su estado o una breve descripción.

Los objetos de este tipo deben tener significado local. No deben transmitirse mucho más allá del área donde el recurso resulta realmente útil.

## 1. Cuándo usar este tipo de objeto

Un objeto EchoLink se utiliza para describir un nodo local EchoLink y la frecuencia en la que puede utilizarse. Para un operador móvil, normalmente lo más importante es:

- el número de nodo EchoLink,
- la frecuencia de trabajo,
- el tono CTCSS o DCS, si es necesario,
- el estado del nodo,
- el indicativo o una breve descripción.

## 2. Ejemplo de trama de objeto

Ejemplo esquemático:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
```

En la práctica, las coordenadas y la descripción deben sustituirse por tus propios datos.

La trama se compone de varias partes:

```text
;EL-123456*111111z5215.00NE02055.00E0438.700MHz T103 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |
|        | |      |        | |        | |          |    |    +-- indicativo o breve descripción
|        | |      |        | |        | |          |    +------- estado del nodo
|        | |      |        | |        | |          +------------ tono / acceso
|        | |      |        | |        +----------------------- símbolo
|        | |      |        | +-------------------------------- longitud
|        | |      |        +---------------------------------- tabla de símbolos EchoLink
|        | |      +------------------------------------------- latitud
|        | +-------------------------------------------------- marca de tiempo
|        +---------------------------------------------------- nombre del objeto
+------------------------------------------------------------- tipo de trama: objeto
```

## 3. Nombre del objeto

Para objetos EchoLink se recomienda el nombre:

```text
EL-123456
```

donde `123456` es el número de nodo EchoLink.

Esto es importante porque un operador móvil a menudo necesita precisamente el número de nodo y no solo el indicativo de la estación. Colocar el número en el nombre del objeto hace que sea visible en la lista de estaciones u objetos de una radio APRS.

Ejemplos:

```text
EL-123456
EL-045678
EL-987654
```

## 4. Marca de actividad y tiempo

Para un objeto activo se usa:

```text
*
```

Para un objeto fijo se usa a menudo la marca:

```text
111111z
```

Ejemplo:

```text
;EL-123456*111111z
```

## 5. Coordenadas y símbolo

En el formato EchoLink se usan la tabla de símbolos `E` y el símbolo `0`:

```text
5215.00NE02055.00E0
```

Desglose:

```text
5215.00N   latitud
E          tabla de símbolos EchoLink
02055.00E  longitud
0          símbolo
```

En algunos ejemplos se usa una posición con precisión reducida de forma intencionada. Si no quieres mostrar la localización exacta del nodo, utiliza una posición aproximada que siga siendo útil para un usuario local.

## 6. Frecuencia

La frecuencia se indica en el comentario:

```text
438.700MHz
```

Formato recomendado:

```text
xxx.xxxMHz
```

Ejemplos:

```text
145.550MHz
438.700MHz
439.000MHz
```

## 7. Tono, DCS y acceso

Después de la frecuencia se puede indicar el tono CTCSS, el DCS o la información de que no se usa tono.

Ejemplos:

```text
T103    tono CTCSS 103 Hz
C127    CTCSS 127 Hz, apertura y envío de tono
D023    DCS 023
Toff    sin tono
```

## 8. Estado del nodo

En objetos EchoLink se puede añadir un estado corto. Debe ser muy breve, idealmente de 4 caracteres.

Ejemplos:

```text
IDLE    libre
BUSY    ocupado
CONF    conferencia
OFF_    no disponible
```

Si el estado no se conoce, es mejor usar una descripción breve u omitir este campo en lugar de escribir un texto largo.

## 9. Orden recomendado de los campos

Para la legibilidad conviene mantener el orden:

```text
frecuencia tono/DCS estado indicativo-o-descripción
```

Ejemplo:

```text
438.700MHz T103 IDLE SR5ABC
```

Otros ejemplos:

```text
145.550MHz T088 IDLE SR9XYZ
439.000MHz D023 BUSY EchoLink
438.700MHz Toff OFF_ SR5ABC
```

## 10. Buenas prácticas

- Coloca el número del nodo en el nombre del objeto como `EL-xxxxxx`.
- En el comentario, indica la frecuencia en formato `xxx.xxxMHz`.
- Añade tono o DCS si son necesarios para el acceso.
- El estado debe ser breve, idealmente de 4 caracteres.
- No describas toda la configuración de EchoLink en el comentario. La trama debe seguir siendo legible en una radio.
- El objeto debe transmitirse localmente, donde el nodo sea realmente útil.

## 11. Guía rápida

```text
;             inicio del objeto
EL-123456     nombre del objeto con número de nodo EchoLink
*             objeto activo
111111z       marca de tiempo fija
E             tabla de símbolos EchoLink
0             símbolo EchoLink
438.700MHz    frecuencia
T103          tono CTCSS 103 Hz
D023          DCS 023
IDLE          estado de ejemplo
SR5ABC        indicativo o breve descripción
```
