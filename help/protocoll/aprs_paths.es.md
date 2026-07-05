# Rutas APRS en la practica

Esta pagina explica las rutas APRS desde el punto de vista del protocolo: como leer una notacion como `WIDE2-1`, cual es la diferencia entre rutas trazadas y no trazadas, y como se realizan en la practica las rutas de uno y dos componentes.

## 1. Que es una ruta APRS

Una ruta APRS es una lista de saltos o alias que indica a la red RF como una trama puede ser repetida mas adelante.

Ejemplos:

```text
WIDE2-1
SP2-2
WIDE1-1,WIDE2-1
SP1-1,SP2-2
WIDE2-1,RFONLY
```

Reglas principales:

- los elementos de la ruta se separan con comas,
- la ruta se procesa de izquierda a derecha,
- el siguiente elemento no se toca hasta que se procese el primer elemento aun no consumido,
- `RFONLY` y `NOGATE` no son saltos de repeticion, sino marcadores que restringen el gate hacia APRS-IS.

En la practica, una transmision local sin digipeaters significa simplemente no usar ruta. Muchos programas y radios tambien usan la etiqueta comoda `DIRECT`, pero a nivel de protocolo esto solo significa transmision sin saltos digi.

## 2. Como leer `N-N`

En rutas como `WIDEn-N` o `SPn-N`, el numero de la izquierda identifica la familia del alias y su alcance inicial, mientras que el numero de la derecha actua como contador de repeticiones restantes.

Ejemplo:

```text
WIDE2-2
```

significa que la trama todavia puede ser repetida dos veces por digipeaters sucesivos. Despues de la primera repeticion, el contador baja:

```text
WIDE2-2 -> WIDE2-1
```

Despues de la segunda repeticion, la ruta queda consumida:

```text
WIDE2-1 -> WIDE2*
```

El asterisco `*` marca un elemento que ya fue usado y que no debe volver a emplearse para mas repeticiones.

De forma similar:

```text
SP2-2 -> SP2-1 -> SP2*
```

## 3. Rutas trazadas y no trazadas

La diferencia principal es si el digipeater inserta o no su propio indicativo en la ruta.

### Ruta trazada

En una ruta trazada, cada digipeater que repite la trama deja una marca visible. Gracias a eso se puede ver por donde viajo el paquete en RF.

Ejemplo:

```text
SP8XYZ-9>APRS,WIDE2-2:...
```

Despues del primer digi:

```text
SP8XYZ-9>APRS,SR5AAA*,WIDE2-1:...
```

Despues del segundo digi:

```text
SP8XYZ-9>APRS,SR5AAA*,SR5BBB*:...
```

Ventajas:

- es mas facil seguir la ruta del paquete,
- es mas facil diagnosticar el comportamiento de la red.

Desventaja:

- la trama crece con cada repeticion porque se insertan mas indicativos digi.

### Ruta no trazada

En una ruta no trazada, el digipeater no inserta su propio indicativo. Solo reduce el contador o marca el elemento como consumido.

Ejemplo:

```text
SP8XYZ-9>APRS,SP2-2:...
```

Despues del primer digi:

```text
SP8XYZ-9>APRS,SP2-1:...
```

Despues del segundo digi:

```text
SP8XYZ-9>APRS,SP2*:...
```

Ventajas:

- trama mas corta,
- menos crecimiento del paquete al pasar por mas saltos.

Desventaja:

- no se puede ver que digipeaters concretos reenviaron la trama.

En la practica, los alias `WIDE` suelen ser trazados, mientras que alias nacionales o regionales como `SP` o `WM` a veces se configuran como no trazados. Eso no es una propiedad magica de la palabra en si, sino el resultado de la configuracion de la red digi local.

## 4. Ruta de un componente

Una ruta de un componente tiene un solo elemento, pero eso no significa necesariamente una sola repeticion.

Ejemplos:

```text
WIDE2-1
WIDE2-2
SP2-1
SP2-2
```

Interpretacion:

- `WIDE2-1` es un elemento de ruta y una repeticion,
- `WIDE2-2` es un elemento de ruta y dos repeticiones,
- `SP2-1` es un elemento de ruta y una repeticion,
- `SP2-2` es un elemento de ruta y dos repeticiones.

Este es un error comun: la cantidad de elementos de la ruta no es lo mismo que la cantidad de repeticiones.

Ejemplo trazado de un componente:

```text
WIDE2-2
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Ejemplo no trazado de un componente:

```text
SP2-2
-> SP2-1
-> SP2*
```

## 5. Ruta de dos componentes

Una ruta de dos componentes tiene dos elementos separados por coma y siempre se procesa de izquierda a derecha.

Ejemplo:

```text
WIDE1-1,WIDE2-1
```

Primero debe consumirse el primer componente:

```text
WIDE1-1,WIDE2-1
-> DIGI1*,WIDE2-1
-> DIGI1*,DIGI2*
```

Otro ejemplo:

```text
SP1-1,SP2-2
```

Realizacion:

```text
SP1-1,SP2-2
-> SP1*,SP2-2
-> SP1*,SP2-1
-> SP1*,SP2*
```

Conclusiones importantes:

- `WIDE1-1,WIDE2-1` son dos elementos de ruta y dos repeticiones en total,
- `WIDE1-1,WIDE2-2` son dos elementos de ruta, pero tres repeticiones en total,
- `SP1-1,SP2-2` tambien son dos elementos de ruta y tres repeticiones en total.

Una ruta trazada de dos componentes crece mas rapido que una no trazada, porque cada salto puede agregar otro indicativo digi.

## 6. `RFONLY` y `NOGATE`

Al final de una ruta tambien pueden aparecer marcadores adicionales:

```text
WIDE2-1,RFONLY
WIDE1-1,WIDE2-1,NOGATE
```

En la practica cumplen una funcion parecida: se usan para bloquear el gate del trafico RF hacia APRS-IS.

Estos elementos:

- no agregan saltos de repeticion,
- no amplian el alcance RF,
- solo limitan el paso del trafico hacia el lado de internet.

## 7. Conclusiones practicas

- sin ruta significa transmision local sin repeticiones digi,
- una ruta de un componente suele ser suficiente cuando no hacen falta muchas repeticiones,
- una ruta de dos componentes da mas alcance, pero aumenta rapidamente el numero de copias en el canal,
- las rutas trazadas son mejores para diagnostico,
- las rutas no trazadas suelen mantener la trama mas corta,
- las combinaciones que empiezan con `WIDE1-1` solo tienen sentido si encajan con la practica local y con la topologia de la red local,
- siempre conviene seguir las recomendaciones usadas en tu region, porque la red digi local decide que alias funcionan realmente y como se procesan.
