# Objetos de repetidor en APRS

Este documento describe un formato practico de objeto de repetidor en APRS. Esta pensado como archivo de ayuda para un usuario que crea objetos de frecuencia, especialmente para repetidores FM.

El objetivo es preparar una trama que sea legible para los operadores, coherente con la practica de APRS Frequency Objects y lo mejor soportada posible por radios APRS moviles.

## 1. Ejemplo de trama de objeto

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

La trama se compone de varias partes logicas:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
|        | |      |        | |        | |          |    |    |    |
|        | |      |        | |        | |          |    |    |    +-- comentario, indicativo o descripcion
|        | |      |        | |        | |          |    |    +------- cobertura del repetidor
|        | |      |        | |        | |          |    +------------ shift del repetidor
|        | |      |        | |        | |          +----------------- tono CTCSS y ancho FM
|        | |      |        | |        +---------------------------- simbolo
|        | |      |        | +------------------------------------- longitud
|        | |      |        +--------------------------------------- tabla de simbolos
|        | |      +------------------------------------------------ latitud
|        | +------------------------------------------------------- marca de tiempo
|        +--------------------------------------------------------- nombre del objeto
+------------------------------------------------------------------ tipo de trama: objeto
```

## 2. Tipo de trama: objeto

Un objeto APRS comienza con punto y coma:

```text
;
```

Despues del punto y coma aparece el nombre del objeto:

```text
;438.462WX
```

En el ejemplo, el nombre del objeto contiene la frecuencia y un sufijo local:

```text
438.462WX
```

donde:

```text
438.462  - frecuencia del repetidor mostrada como nombre del objeto
WX       - sufijo local, en Polonia a menudo el codigo del condado
```

## 3. Nombre del objeto: frecuencia y sufijo local

Para objetos de repetidor, se recomienda que el nombre del objeto empiece con la frecuencia:

```text
438.462WX
145.600WA
145.775KR
```

Esta notacion es intencional. En los objetos APRS de repetidor y frecuencia, poner la frecuencia en el nombre del objeto mejora la legibilidad en radios APRS moviles. La radio muestra el nombre del objeto en la lista de estaciones, por lo que el operador ve inmediatamente la frecuencia del repetidor sin entrar en los detalles del objeto.

La frecuencia tambien debe repetirse en el comentario del objeto, por ejemplo:

```text
438.462MHz C127 -760 R10k SR5WWL
```

La primera aparicion de la frecuencia, en el nombre del objeto, sirve principalmente para la legibilidad en la lista de objetos. La segunda aparicion, en el comentario, forma parte de la informacion de frecuencia y puede ser usada por radios o aplicaciones para funciones QSY/TUNE o para presentar parametros del repetidor.

La frecuencia en el nombre y la frecuencia en el comentario no deben tratarse como un duplicado incorrecto. Es un compromiso deliberado derivado de la compatibilidad y del uso practico de los objetos de frecuencia.

## 4. Unicidad del nombre del objeto

El nombre del objeto APRS tiene longitud limitada, por lo que la notacion:

```text
frecuencia + sufijo local
```

es un compromiso entre legibilidad y unicidad.

Ejemplo:

```text
438.462WX
```

significa un objeto para la frecuencia `438.462 MHz` con sufijo local `WX`.

En Polonia, a menudo se usa como sufijo el codigo del condado. Esto ayuda a distinguir objetos de repetidores que trabajan en la misma frecuencia en ubicaciones diferentes.

Sin embargo, para objetos permanentes hay que recordar que el objeto puede llegar a toda la red APRS-IS. Un sufijo local, como el codigo del condado, reduce el riesgo de colisiones locales, pero no garantiza por completo la unicidad global.

Regla practica:

```text
esquema recomendado:
    frecuencia + sufijo local
    ejemplo: 438.462WX

recomendacion:
    el nombre del objeto debe empezar con la frecuencia

advertencia:
    para objetos permanentes enviados a APRS-IS, comprueba
    que el nombre sea lo mas globalmente unico posible
```

Si el repetidor tiene un indicativo, nombre o identificador bien conocido, puede colocarse en el comentario final en lugar de eliminar la frecuencia del nombre del objeto.

## 5. Marca de actividad

Despues del nombre del objeto aparece la marca de actividad:

```text
*
```

Ejemplo:

```text
;438.462WX*
```

Significado:

```text
*  - objeto activo
_  - objeto eliminado o inactivo
```

Para un repetidor operativo normal, se usa `*`.

## 6. Marca de tiempo

En el ejemplo se usa:

```text
111111z
```

Fragmento completo:

```text
;438.462WX*111111z
```

La marca `111111z` se usa a menudo como marca de tiempo fija para objetos permanentes.

Regla practica:

```text
objeto fijo o permanente:
    111111z

objeto temporal:
    hora UTC actual generada en cada transmision
```

Para un objeto fijo es mas importante refrescarlo correctamente de forma regular que informar la hora exacta de generacion.

## 7. Coordenadas y simbolo

Ejemplo de posicion:

```text
5218.54N/02113.09Er
```

Desglose:

```text
5218.54N   latitud
/          tabla de simbolos
02113.09E  longitud
r          simbolo
```

Para el objeto de repetidor del ejemplo se usa el simbolo `r`.

## 8. Frecuencia del repetidor en el comentario

Despues de la posicion se indica la frecuencia de trabajo del repetidor:

```text
438.462MHz
```

Formato recomendado:

```text
xxx.xxxMHz
```

Ejemplos:

```text
145.600MHz
438.462MHz
439.000MHz
```

La frecuencia del comentario debe coincidir con la frecuencia usada en el nombre del objeto.

Ejemplo correcto:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

Ejemplo sospechoso:

```text
;438.462WX*111111z5218.54N/02113.09Er439.000MHz C127 -760 R10k SR5WWL
```

En el segundo ejemplo, el nombre del objeto sugiere `438.462 MHz`, pero el comentario indica `439.000 MHz`. Esta notacion puede confundir al operador.

## 9. CTCSS, tono y ancho FM

En el ejemplo:

```text
C127
```

Esto indica informacion sobre el tono CTCSS y el modo de trabajo del repetidor.

Significado de las letras:

```text
t y c  - FM estrecha
T y C  - FM ancha

t y T  - el repetidor se abre con tono
c y C  - el repetidor se abre con tono y transmite tono
```

Interpretacion de ejemplo:

```text
T127  - FM ancha, el repetidor se abre con tono de 127 Hz
C127  - FM ancha, el repetidor se abre con tono de 127 Hz y transmite tono
t127  - FM estrecha, el repetidor se abre con tono de 127 Hz
c127  - FM estrecha, el repetidor se abre con tono de 127 Hz y transmite tono
```

Conviene mantener el formato de tres cifras cuando el tono tiene menos de tres digitos:

```text
T088
c088
```

## 10. Shift del repetidor

En el ejemplo:

```text
-760
```

Significa shift `-7.6 MHz`.

Regla de notacion:

```text
-760  -> shift -7.6 MHz
-060  -> shift -600 kHz
+760  -> shift +7.6 MHz
+060  -> shift +600 kHz
```

Es decir, el valor se escribe como desplazamiento sin separador decimal.

Ejemplos:

```text
145.600MHz -060
438.462MHz -760
439.000MHz +760
```

## 11. Cobertura del repetidor: Rxxk / Rxxm

Para objetos de repetidor, la cobertura puede indicarse como:

```text
Rxxk
Rxxm
```

Significado:

```text
R10k  - cobertura aproximada de 10 km
R25k  - cobertura aproximada de 25 km
R15m  - cobertura aproximada de 15 millas
```

En el ejemplo:

```text
R10k
```

asi que la cobertura declarada del repetidor es de unos 10 km.

Para objetos de repetidor, se prefiere la notacion `Rxxk` o `Rxxm`. No debe confundirse con la extension clasica `RNGxxxx`, que es otro mecanismo para describir cobertura de radio.

## 12. Comentario, indicativo o descripcion

Al final se puede poner un indicativo, nombre del repetidor o una descripcion breve:

```text
SR5WWL
```

Fragmento final completo:

```text
438.462MHz C127 -760 R10k SR5WWL
```

El comentario debe ser breve. Una trama APRS no es un buen lugar para descripciones largas, direcciones web o informacion de varias frases.

## 13. Orden recomendado de campos en el comentario

Para legibilidad y compatibilidad, conviene mantener un orden fijo:

```text
frecuencia modo/CTCSS shift cobertura comentario
```

Ejemplo:

```text
438.462MHz C127 -760 R10k SR5WWL
```

Otros ejemplos:

```text
145.600MHz T103 -060 R25k SR9ABC
439.000MHz C123 +760 R30k Local
145.775MHz c088 -060 R15k SR5YYY
```

## 14. Campos recomendados del formulario o generador

Al crear un objeto de repetidor, resulta util un generador sencillo que componga el nombre del objeto y el comentario a partir de campos separados.

Campos propuestos:

```text
Nombre del objeto:
    438.462WX

Modo del nombre del objeto:
    frecuencia + sufijo local
    nombre personalizado

Sufijo local:
    WX

Frecuencia:
    438.462

Tono CTCSS:
    127

Modo de tono:
    se abre con tono
    se abre con tono y transmite tono

Ancho FM:
    FM estrecha
    FM ancha

Shift:
    -7.6 MHz
    -0.6 MHz
    +0.6 MHz
    +7.6 MHz
    personalizado

Cobertura:
    10

Unidad de cobertura:
    km
    millas

Comentario:
    SR5WWL
```

Resultado:

```text
nombre del objeto:
    438.462WX

comentario:
    438.462MHz C127 -760 R10k SR5WWL
```

El generador debe asegurarse de que la frecuencia sea visible tanto en el nombre del objeto como en el comentario. No debe eliminarse la frecuencia del nombre solo porque ya aparece en el comentario.

Para un objeto permanente enviado a APRS-IS, conviene mostrar una advertencia:

```text
Los nombres de objetos permanentes deben ser lo mas globalmente unicos posible.
El esquema frecuencia + sufijo local se recomienda por legibilidad en radios APRS,
pero no garantiza unicidad completa en toda la red APRS-IS.
```

## 15. Validacion recomendada

Reglas de validacion propuestas:

```text
nombre del objeto:
    obligatorio
    formato recomendado para repetidores: frecuencia + sufijo local
    ejemplo: 438.462WX
    advertencia si un objeto permanente va a enviarse a APRS-IS
    y el nombre parece demasiado generico o no contiene sufijo

frecuencia:
    obligatoria
    formato xxx.xxx

coherencia entre nombre y comentario:
    la frecuencia del nombre del objeto debe coincidir
    con la frecuencia del comentario, si ambas se indican

CTCSS:
    opcional
    solo valores CTCSS comunes o un numero de 2-3 digitos

modo de tono:
    t / T / c / C

shift:
    opcional
    formato +xxx o -xxx

cobertura:
    opcional
    formato Rxxk o Rxxm

comentario:
    opcional
    texto breve sin sobrecargar la trama
```

La validacion debe ayudar al usuario, no bloquear todos los casos atipicos. Para un usuario consciente, conviene dejar la posibilidad de correccion manual.

## 16. Ejemplos de objetos listos

### Repetidor UHF, FM ancha, CTCSS, shift -7.6 MHz

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

### Repetidor VHF, FM ancha, tono en entrada, shift -600 kHz

```text
;145.600WA*111111z5215.00N/02055.00Er145.600MHz T103 -060 R25k SR5XXX
```

### Repetidor VHF, FM estrecha, tono en entrada y salida

```text
;145.775KR*111111z5215.00N/02055.00Er145.775MHz c088 -060 R15k SR5YYY
```

## 17. Como leer el objeto en detalle

De la trama de ejemplo:

```text
;438.462WX*111111z5218.54N/02113.09Er438.462MHz C127 -760 R10k SR5WWL
```

se puede leer:

```text
Object name: 438.462WX
Frequency from name: 438.462 MHz
Local suffix: WX
Position: 52°18.54'N, 21°13.09'E
Symbol: r
Frequency: 438.462 MHz
CTCSS: 127 Hz
FM width: wide
Tone mode: opens with tone and transmits tone
Shift: -7.6 MHz
Range: 10 km
Description: SR5WWL
```

## 18. Guia rapida

```text
;             inicio del objeto
438.462WX     nombre del objeto: frecuencia + sufijo local
*             objeto activo
_             objeto eliminado o inactivo
111111z       marca de tiempo fija
/             tabla de simbolos
r             simbolo de repetidor
438.462MHz    frecuencia en el comentario
T127          FM ancha, se abre con tono de 127 Hz
C127          FM ancha, se abre con tono de 127 Hz y transmite tono
t127          FM estrecha, se abre con tono de 127 Hz
c127          FM estrecha, se abre con tono de 127 Hz y transmite tono
-760          shift -7.6 MHz
-060          shift -600 kHz
R10k          cobertura de 10 km
R15m          cobertura de 15 millas
```
