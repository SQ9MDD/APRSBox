# Copia de seguridad de configuración

Este panel exporta y restaura una instantánea de la configuración de la interfaz APRSBox en formato `JSON` codificado en UTF-8.

## Datos incluidos

La copia v2 contiene ajustes globales, de mensajes y de notificaciones, además de la configuración de fuentes de mapa, interfaces TNC y APRS-IS, estación y WX, transportes y reglas de radar de notificaciones, flujos y reglas de enrutamiento, objetos y elementos APRS y boletines.

El tráfico de ejecución, los resultados de pruebas de transportes, el estado del radar de notificaciones, los registros de eventos, el historial de mensajes, las alertas APRS propias, las cuentas de usuario y otras tablas fuera del formato compatible no se incluyen.

El archivo puede contener indicativos, datos de conexión APRS-IS, rutas, endpoints, tokens de webhook y Telegram y otra configuración operativa. Trátelo como información sensible.

## Exportación e importación

- `Exportar copia de configuración` descarga la instantánea actual.
- `Importar copia de configuración` valida el formato y la versión, y después reemplaza las tablas compatibles dentro de una única transacción.
- Si falla la validación o una comprobación de la base de datos, la importación se revierte.
- Solo se admite el formato v2. Los archivos v1 creados por versiones anteriores no se pueden importar.

La importación sobrescribe la configuración compatible actual. Exporte el estado actual antes de restaurar otro archivo. Tras una importación correcta, reinicie los servicios APRSBox; en Docker, reinicie o recree el contenedor con la herramienta de despliegue.
