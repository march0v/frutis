# FRUTIS (Backup)

Middleware y clientes GUI con autenticacion por token y control de roles.

## Componentes
- `middleware.py`: servidor TLS, login, sesiones, autorizacion y registro de eventos.
- `admin_gui.py`: cliente admin para logs, ventas, inventario y monitor.
- `supervisor_gui.py`: cliente supervisor para consultas.
- `empleado_gui.py`: cliente empleado para registrar ventas e inventario.

## Variables de entorno
### Middleware
- `FRUTIS_BASE_PATH` (default: `/opt/frutis`)
- `FRUTIS_BIND_HOST` (default: `0.0.0.0`)
- `FRUTIS_PORT` (default: `5000`)
- `FRUTIS_CERT_PATH` (default: `server.crt`)
- `FRUTIS_KEY_PATH` (default: `server.key`)

### Clientes GUI
- `FRUTIS_SERVER_IP` (default: `172.25.250.11`)
- `FRUTIS_SERVER_PORT` (default: `5000`)

## Protocolo de autenticacion
1. Login:
   - Cliente envia: `LOGIN|usuario|password`
   - Respuesta exitosa: `OK|rol|token`
2. Comandos autenticados:
   - Cliente envia: `TOKEN|<token>|<comando>`

## Comandos soportados
- Empleado/admin:
  - `VENTA|usuario|producto|cantidad`
  - `INVENTARIO|usuario|producto|cantidad`
- Supervisor/admin:
  - `SOLICITAR_LOGS`
  - `VER_VENTAS`
  - `VER_INVENTARIO`
- Admin:
  - `CREAR_USUARIO|usuario|pass|rol`
  - `MONITOR`

## Ejecucion basica
1. Inicia middleware:
```bash
python3 middleware.py
```
2. Abre el cliente requerido:
```bash
python3 admin_gui.py
# o
python3 supervisor_gui.py
# o
python3 empleado_gui.py
```

## Seguridad aplicada
- Hash de contrasenas con PBKDF2 + salt.
- Sesion con token temporal.
- Autorizacion por rol en cada comando.
- Mitigacion de fuerza bruta en login por IP.
- Sanitizacion de logs y validacion de campos.
