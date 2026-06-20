# Objetos IRLP en APRS

Este documento es un archivo de ayuda para un usuario que crea objetos APRS de frecuencia.

El objetivo de estos objetos es mostrar recursos locales de radio de una forma legible para operadores móviles y lo más compatible posible con la práctica de APRS Frequency Objects. El objeto debe ayudar a responder preguntas simples:

- dónde se encuentra el recurso,
- en qué frecuencia trabaja,
- qué parámetros de acceso requiere,
- cuál es su estado o una breve descripción.

Los objetos de este tipo deben tener significado local. No deben transmitirse mucho más allá del área donde el recurso resulta realmente útil.

## 1. Cuándo usar este tipo de objeto

Un objeto IRLP se utiliza para describir un nodo local IRLP y la frecuencia en la que el operador puede utilizarlo. Para el usuario móvil, lo más importante es:

- el número de nodo IRLP,
- la frecuencia de trabajo,
- el tono CTCSS, DCS u otra información de acceso,
- el estado del nodo,
- el indicativo o una breve descripción.

## 2. Ejemplo de trama de objeto

Ejemplo esquemático:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
```

La trama se compone de varias partes:

```text
;IRLP-1234*111111z5215.00NI02055.00E0438.700MHz T103 -760 IDLE SR5ABC
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- indicativo o descripción
|        | |      |        | |        | |          |    |    +------- estado
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- tono / acceso
|        | |      |        | |        +---------------------------- símbolo
|        | |      |        | +------------------------------------- longitud
|        | |      |        +--------------------------------------- tabla de símbolos IRLP
|        | |      +------------------------------------------------ latitud
|        | +------------------------------------------------------- marca de tiempo
|        +--------------------------------------------------------- nombre del objeto
+------------------------------------------------------------------ tipo de trama: objeto
```

## 3. Nombre del objeto

Para objetos IRLP se recomiendan los nombres:

```text
IRLP-1234
IRLP12345
```

La primera forma es típica para números de nodo de cuatro dígitos. La segunda puede usarse si el número tiene cinco dígitos.

Ejemplos:

```text
IRLP-1234
IRLP-5678
IRLP12345
```

El número de nodo debe ser visible en el nombre del objeto, porque el operador móvil lo necesita para usar el enlace.

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
;IRLP-1234*111111z
```

## 5. Coordenadas y símbolo

En el formato IRLP se usan la tabla de símbolos `I` y el símbolo `0`:

```text
5215.00NI02055.00E0
```

Desglose:

```text
5215.00N   latitud
I          tabla de símbolos IRLP
02055.00E  longitud
0          símbolo
```

Si no debe publicarse la localización exacta, puede usarse una posición aproximada, siempre que siga estando relacionada con el área local de servicio del nodo.

## 6. Frecuencia

La frecuencia se indica en el comentario:

```text
438.700MHz
```

Formato recomendado:

```text
xxx.xxxMHz
```

## 7. Tono, DCS y shift

Después de la frecuencia se pueden indicar tono, DCS y shift.

Ejemplos:

```text
T103       tono CTCSS 103 Hz
C127       CTCSS 127 Hz, apertura y envío de tono
D023       DCS 023
-760       shift -7.6 MHz
-060       shift -600 kHz
+760       shift +7.6 MHz
```

## 8. Estado del nodo

El estado debe ser corto y legible.

Ejemplos:

```text
IDLE    libre
BUSY    ocupado
OFF_    no disponible
```

## 9. Orden recomendado de los campos

Para la legibilidad conviene mantener el orden:

```text
frecuencia tono/DCS shift estado indicativo-o-descripción
```

Ejemplo:

```text
438.700MHz T103 -760 IDLE SR5ABC
```

Otros ejemplos:

```text
145.575MHz T088 -060 IDLE IRLP
439.000MHz D023 -760 BUSY SR9XYZ
438.700MHz Toff -760 OFF_ Local
```

## 10. Buenas prácticas

- Coloca el número del nodo IRLP en el nombre del objeto.
- En el comentario, indica la frecuencia en formato `xxx.xxxMHz`.
- Añade tono, DCS o shift si son necesarios para usar el nodo.
- El estado debe ser corto.
- No uses una descripción larga. Un operador móvil debería poder leer los datos clave sin desplazarse.
- El objeto debe transmitirse localmente, en el área donde el nodo resulta realmente útil.

## 11. Guía rápida

```text
;             inicio del objeto
IRLP-1234     nombre del objeto con número de nodo IRLP
IRLP12345     variante para un número de cinco dígitos
*             objeto activo
111111z       marca de tiempo fija
I             tabla de símbolos IRLP
0             símbolo IRLP
438.700MHz    frecuencia
T103          tono CTCSS 103 Hz
D023          DCS 023
-760          shift -7.6 MHz
IDLE          estado de ejemplo
SR5ABC        indicativo o breve descripción
```
