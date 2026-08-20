# HTTPS

Este panel cambia la interfaz web de APRSBox de HTTP a HTTPS y administra los archivos utilizados por el servidor.

## Preparación de archivos

APRSBox necesita un par coincidente:

- un certificado de servidor PEM guardado como `aprsbox.crt`,
- una clave privada PEM guardada como `aprsbox.key`,
- una cadena de CA opcional guardada como `aprsbox-ca-chain.crt`.

Los archivos se pueden subir con las extensiones indicadas en el formulario. APRSBox los guarda con nombres fijos en `/opt/aprsbox/data/ssl`. El certificado y la clave privada se comprueban como un par antes de permitir HTTPS.

La generación de PKI local y la descarga de la CA raíz están desactivadas por ahora. De momento, crea el certificado con una CA externa o una herramienta PKI propia y súbelo desde este panel.

## Nombre mDNS

Si el host publica un nombre mediante mDNS, APRSBox puede estar disponible, por ejemplo, como `https://aprsbox.local`. mDNS debe estar activo en el host y ser compatible con el dispositivo cliente.

El certificado debe incluir el nombre utilizado, por ejemplo `DNS:aprsbox.local`, en Subject Alternative Name (SAN). Un Common Name por sí solo no es suficiente para los navegadores modernos. Las autoridades públicas normalmente no emiten certificados para nombres `.local`, por lo que suele utilizarse una CA privada y se instala su CA raíz como confiable en los dispositivos cliente.

## Certificados para direcciones IP

Si APRSBox se abre como `https://192.168.1.20`, esa dirección exacta debe aparecer en SAN como entrada IP, por ejemplo `IP:192.168.1.20`. Una entrada `DNS:192.168.1.20` no equivale a una entrada IP.

Para una dirección asignada por DHCP, configura una reserva o una dirección estática. Si cambia la dirección, el certificado deja de coincidir y debe volver a emitirse. Un certificado puede contener varios nombres DNS y varias direcciones IP.

## Activación de HTTPS

1. Sube el certificado y la clave privada correspondiente. La cadena de CA es opcional.
2. Comprueba los iconos verdes de estado.
3. Selecciona `Activar HTTPS`.
4. Selecciona `Guardar y reiniciar` y espera al reinicio de los servicios.

Al activarlo, APRSBox escucha HTTPS en el puerto `443`. El servidor HTTP normal del puerto `8000` queda desactivado y el puerto `80` redirige las solicitudes a HTTPS con el estado `308`.

Con una CA privada, el navegador puede mostrar un aviso hasta que su CA raíz se instale como confiable en ese dispositivo.

## Eliminación de archivos

El certificado del servidor y la clave privada no se pueden eliminar mientras HTTPS está activo. Primero desactiva HTTPS y espera a que la interfaz vuelva a `http://dirección:8000`. La cadena de CA se puede descargar o eliminar de forma independiente.
