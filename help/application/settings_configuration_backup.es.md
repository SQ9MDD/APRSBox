# Copia de seguridad de configuración

Este panel exporta y restaura una instantánea de la configuración de la interfaz APRSBox en formato `JSON` codificado en UTF-8.

## Datos incluidos

La copia contiene determinados ajustes globales y la configuración de fuentes de mapa, interfaces TNC y APRS-IS, estación y WX, flujos y reglas de enrutamiento, objetos y elementos APRS, boletines y estaciones de referencia de condiciones de banda.

El tráfico de ejecución, los registros de eventos, el historial de mensajes, las cuentas de usuario y otras tablas fuera del formato compatible no se incluyen.

El archivo puede contener indicativos, datos de conexión APRS-IS, rutas, endpoints y otra configuración operativa. Trátelo como información sensible.

## Exportación e importación

- `Exportar copia de configuración` descarga la instantánea actual.
- `Importar copia de configuración` valida el formato y la versión, y después reemplaza las tablas compatibles dentro de una única transacción.
- Si falla la validación o una comprobación de la base de datos, la importación se revierte.

La importación sobrescribe la configuración compatible actual. Exporte el estado actual antes de restaurar otro archivo. Tras una importación correcta, reinicie los servicios APRSBox; en Docker, reinicie o recree el contenedor con la herramienta de despliegue.
