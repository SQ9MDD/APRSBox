# Objetos WiRES / WiRES-X en APRS

Este documento es un archivo de ayuda para un usuario que crea objetos APRS de frecuencia.

El objetivo de estos objetos es mostrar recursos locales de radio de una forma legible para operadores móviles y lo más compatible posible con la práctica de APRS Frequency Objects. El objeto debe ayudar a responder preguntas simples:

- dónde se encuentra el recurso,
- en qué frecuencia trabaja,
- qué parámetros de acceso requiere,
- cuál es su estado o una breve descripción.

Los objetos de este tipo deben tener significado local. No deben transmitirse mucho más allá del área donde el recurso resulta realmente útil.

## 1. Cuándo usar este tipo de objeto

Un objeto WiRES o WiRES-X se utiliza para describir un nodo local o un repetidor asociado con la red Yaesu WiRES / WiRES-X. Este tipo de objeto puede ser útil para un operador móvil que ve en la radio APRS información sobre un recurso local y puede pasar rápidamente a la frecuencia correcta.

Usos típicos:

- repetidor local con acceso WiRES-X,
- nodo local WiRES,
- información sobre frecuencia, DCS/CTCSS, shift y cobertura,
- una breve descripción o el indicativo del repetidor.

## 2. Ejemplo de trama de objeto

Ejemplo práctico:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
```

La trama se compone de varias partes:

```text
;WIR-17967*111111z5356.33N/02150.80Er438.525MHz DOFF -760 R99k SR4MIT
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- indicativo o breve descripción
|        | |      |        | |        | |          |    |    +------- cobertura
|        | |      |        | |        | |          |    +------------ shift
|        | |      |        | |        | |          +----------------- DCS / SQL / tono
|        | |      |        | |        +---------------------------- símbolo
|        | |      |        | +------------------------------------- longitud
|        | |      |        +--------------------------------------- tabla de símbolos
|        | |      +------------------------------------------------ latitud
|        | +------------------------------------------------------- marca de tiempo
|        +--------------------------------------------------------- nombre del objeto
+------------------------------------------------------------------ tipo de trama: objeto
```

## 3. Nombre del objeto

Para objetos WiRES se recomienda un nombre que empiece por:

```text
WIR-
```

Ejemplos:

```text
WIR-17967
WIR-1101D
```

El nombre debe mostrar el número o identificador del nodo WiRES, porque precisamente ese número es importante para el operador que ve el objeto en la lista de estaciones.

En un objeto WiRES-X asociado a un repetidor conviene mantener el nombre en la forma `WIR-xxxxx`, y poner la frecuencia, el shift y los parámetros de acceso en el comentario.

## 4. Marca de actividad y tiempo

Después del nombre del objeto aparece la marca de actividad:

```text
*
```

Significado:

```text
*  - objeto activo
_  - objeto eliminado o inactivo
```

Para un objeto fijo se usa a menudo la marca:

```text
111111z
```

Ejemplo:

```text
;WIR-17967*111111z
```

## 5. Coordenadas y símbolo

En el ejemplo se usa el símbolo clásico de repetidor:

```text
5356.33N/02150.80Er
```

Desglose:

```text
5356.33N   latitud
/          tabla de símbolos
02150.80E  longitud
r          símbolo de repetidor
```

En la práctica de APRS Frequency Objects para WiRES también puede verse la tabla de símbolos `W` y el símbolo `0`, destinados a marcar un nodo WiRES. En la práctica, si el objeto describe un repetidor con WiRES-X, el símbolo de repetidor `r` puede resultar más claro para el usuario.

## 6. Frecuencia

La frecuencia se indica en el comentario:

```text
438.525MHz
```

Formato recomendado:

```text
xxx.xxxMHz
```

Ejemplos:

```text
438.525MHz
439.000MHz
145.600MHz
```

## 7. DCS, CTCSS, SQL y acceso

En el ejemplo:

```text
DOFF
```

indica información relacionada con DCS o squelch. En objetos WiRES / WiRES-X pueden encontrarse distintas prácticas locales, por lo que lo más importante es que la notación sea corta y clara para los operadores de la región.

Ejemplos de campos de acceso:

```text
D023    DCS 023
D754    DCS 754
DOFF    DCS desactivado o sin DCS, según la práctica local de descripción
T103    tono CTCSS 103 Hz
C127    CTCSS 127 Hz, repetidor abierto por tono y transmitiendo tono
```

## 8. Shift

El shift se escribe como desplazamiento sin separador decimal:

```text
-760
```

Significado:

```text
-760  - shift -7.6 MHz
-060  - shift -600 kHz
+760  - shift +7.6 MHz
+060  - shift +600 kHz
```

## 9. Cobertura

La cobertura puede darse como:

```text
Rxxk
Rxxm
```

Ejemplos:

```text
R99k  - cobertura de unos 99 km
R25k  - cobertura de unos 25 km
R15m  - cobertura de unas 15 millas
```

## 10. Orden recomendado de los campos

Para la legibilidad conviene mantener un orden fijo:

```text
frecuencia DCS/CTCSS shift cobertura descripción
```

Ejemplo:

```text
438.525MHz DOFF -760 R99k SR4MIT
```

Otros ejemplos:

```text
438.525MHz D023 -760 R50k Wires node
439.000MHz T103 -760 R30k Local Wires
145.600MHz C127 -060 R25k WIRES-X
```

## 11. Buenas prácticas

- Usa el nombre `WIR-xxxxx` si conoces el número del nodo.
- En el comentario, indica la frecuencia en formato `xxx.xxxMHz`.
- Añade el shift si el recurso funciona a través de un repetidor.
- Añade DCS, CTCSS o una nota corta de acceso si hace falta.
- Añade cobertura solo si tienes un valor aproximado razonable.
- El comentario final debe ser corto, por ejemplo el indicativo del repetidor o un nombre local.

## 12. Guía rápida

```text
;             inicio del objeto
WIR-17967     nombre del objeto con número de nodo WiRES
*             objeto activo
111111z       marca de tiempo fija
r             símbolo de repetidor, práctico para un objeto de repetidor
438.525MHz    frecuencia
D023          DCS 023
DOFF          sin DCS o DCS desactivado, según la práctica local
T103          tono CTCSS 103 Hz
-760          shift -7.6 MHz
R99k          cobertura de unos 99 km
SR4MIT        indicativo o breve descripción
```
