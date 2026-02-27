import datetime
import hashlib
import os
import secrets
import socket
import ssl
import time

BASE_PATH = os.getenv("FRUTIS_BASE_PATH", "/opt/frutis")
SERVER_HOST = os.getenv("FRUTIS_BIND_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("FRUTIS_PORT", "5000"))
CATALOGO_PATH = f"{BASE_PATH}/datos/catalogo_productos.txt"

SESSION_TTL_SECONDS = 3600
LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 5

ALLOWED_UNITS = {"kilos", "unidades"}

failed_login_attempts = {}
sessions = {}

os.makedirs(f"{BASE_PATH}/logs", exist_ok=True)
os.makedirs(f"{BASE_PATH}/datos", exist_ok=True)


# ================= PASSWORD HASH =================

def hash_pass(password, salt=None, iterations=210000):
    if salt is None:
        salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_pass(password, stored_hash):
    if not stored_hash:
        return False

    stored_hash = stored_hash.strip()

    if "$" not in stored_hash:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return secrets.compare_digest(legacy, stored_hash)

    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        calc = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
        return secrets.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


# ================= LOGIN HELPERS =================

def parse_user_line(line):
    parts = [x.strip() for x in line.strip().split(",")]
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def is_rate_limited(ip_addr):
    now = time.time()
    attempts = [
        ts for ts in failed_login_attempts.get(ip_addr, [])
        if now - ts < LOGIN_WINDOW_SECONDS
    ]
    failed_login_attempts[ip_addr] = attempts
    return len(attempts) >= MAX_LOGIN_ATTEMPTS


def register_failed_login(ip_addr):
    attempts = failed_login_attempts.get(ip_addr, [])
    attempts.append(time.time())
    failed_login_attempts[ip_addr] = attempts


def clear_failed_login(ip_addr):
    failed_login_attempts.pop(ip_addr, None)


def autenticar(user, password):
    try:
        with open(f"{BASE_PATH}/usuarios.txt", "r", encoding="utf-8") as f:
            for linea in f:
                if not linea.strip():
                    continue

                parsed = parse_user_line(linea)
                if parsed is None:
                    continue

                username, stored_hash, rol = parsed
                if username == user and verify_pass(password, stored_hash):
                    return rol
    except OSError as exc:
        print("ERROR AUTH FILE:", exc)

    return None


# ================= SESSION HELPERS =================

def crear_sesion(user, rol):
    token = secrets.token_urlsafe(32)
    sessions[token] = {
        "user": user,
        "rol": rol,
        "exp": time.time() + SESSION_TTL_SECONDS,
    }
    return token


def obtener_sesion(token):
    sesion = sessions.get(token)
    if not sesion:
        return None

    if sesion["exp"] < time.time():
        sessions.pop(token, None)
        return None

    return sesion


def extraer_comando_autenticado(data):
    partes = data.split("|", 2)
    if len(partes) < 3 or partes[0] != "TOKEN":
        return None, None

    token = partes[1].strip()
    comando = partes[2].strip()
    sesion = obtener_sesion(token)
    if not sesion:
        return None, None

    return sesion, comando


# ================= VALIDATION HELPERS =================

def sanitize_log_value(value):
    return value.replace("\n", "\\n").replace("\r", "\\r")


def valid_field(value, max_len=64):
    if not value or len(value) > max_len:
        return False

    blocked = [",", "|", "\n", "\r", "\t"]
    return all(ch not in value for ch in blocked)


def parse_positive_number(raw, max_value=1000000.0):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if value <= 0 or value > max_value:
        return None

    return value


def normalize_product(value):
    return " ".join(value.strip().split()).lower()


def parse_catalog_line(line):
    parts = [x.strip() for x in line.strip().split("|")]
    if len(parts) != 3:
        return None

    nombre, unidad, precio_raw = parts
    unidad = unidad.lower()
    precio = parse_positive_number(precio_raw)
    if not nombre or unidad not in ALLOWED_UNITS or precio is None:
        return None

    return {
        "nombre": nombre,
        "key": normalize_product(nombre),
        "unidad": unidad,
        "precio": precio,
    }


def load_catalog():
    catalog = {}
    if not os.path.exists(CATALOGO_PATH):
        return catalog

    try:
        with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                parsed = parse_catalog_line(line)
                if not parsed:
                    continue
                catalog[parsed["key"]] = parsed
    except OSError as exc:
        print("ERROR CATALOGO:", exc)

    return catalog


def save_catalog(catalog):
    lines = []
    for key in sorted(catalog.keys()):
        item = catalog[key]
        lines.append(f"{item['nombre']}|{item['unidad']}|{item['precio']:.2f}\n")

    with open(CATALOGO_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def format_catalog(catalog):
    if not catalog:
        return "Sin productos"

    rows = ["PRODUCTO|UNIDAD|PRECIO"]
    for key in sorted(catalog.keys()):
        item = catalog[key]
        rows.append(f"{item['nombre']}|{item['unidad']}|{item['precio']:.2f}")
    return "\n".join(rows)


def send_and_close(cliente, payload):
    try:
        if isinstance(payload, bytes):
            cliente.send(payload)
        else:
            cliente.send(str(payload).encode())
    except OSError:
        pass

    try:
        cliente.close()
    except OSError:
        pass


# ================= SOCKET =================

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain(
    certfile=os.getenv("FRUTIS_CERT_PATH", "server.crt"),
    keyfile=os.getenv("FRUTIS_KEY_PATH", "server.key"),
)

bindsocket = socket.socket()
bindsocket.bind((SERVER_HOST, SERVER_PORT))
bindsocket.listen(5)

print(" FRUTIS Middleware activo...")

while True:
    newsocket, addr = bindsocket.accept()

    try:
        cliente = context.wrap_socket(newsocket, server_side=True)
    except ssl.SSLError as exc:
        print("ERROR TLS:", exc)
        newsocket.close()
        continue

    try:
        raw = cliente.recv(4096)
        data = raw.decode(errors="replace").strip()
    except OSError as exc:
        print("ERROR RECV:", exc)
        send_and_close(cliente, b"FAIL")
        continue

    if not data:
        send_and_close(cliente, b"FAIL")
        continue

    client_ip = addr[0]

    # ================= LOGIN =================
    if data.startswith("LOGIN"):
        if is_rate_limited(client_ip):
            send_and_close(cliente, b"FAIL|RATE_LIMIT")
            continue

        try:
            _, user, password = data.split("|", 2)
            rol = autenticar(user.strip(), password.strip())

            if rol:
                clear_failed_login(client_ip)
                token = crear_sesion(user.strip(), rol)
                send_and_close(cliente, f"OK|{rol}|{token}")
            else:
                register_failed_login(client_ip)
                send_and_close(cliente, b"FAIL")
        except ValueError:
            register_failed_login(client_ip)
            send_and_close(cliente, b"FAIL")

        continue

    sesion, command = extraer_comando_autenticado(data)
    if sesion is None:
        send_and_close(cliente, b"FAIL|AUTH_REQUIRED")
        continue

    fecha = datetime.datetime.now()
    safe_data = sanitize_log_value(command)
    log_entry = f"{fecha} | {addr} | {safe_data}\n"

    try:
        with open(f"{BASE_PATH}/logs/log_general.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except OSError as exc:
        print("ERROR LOG GENERAL:", exc)

    # ================= LISTAR PRODUCTOS =================
    if command == "LISTAR_PRODUCTOS":
        catalog = load_catalog()
        send_and_close(cliente, format_catalog(catalog))
        continue

    # ================= CONFIGURAR PRODUCTO (ADMIN) =================
    if command.startswith("SET_PRODUCTO"):
        if sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        partes = command.split("|", 3)
        if len(partes) != 4:
            send_and_close(cliente, b"Formato invalido. Use: SET_PRODUCTO|producto|unidad|precio")
            continue

        _, producto, unidad_raw, precio_raw = [p.strip() for p in partes]
        unidad = unidad_raw.lower()

        if not valid_field(producto, max_len=120):
            send_and_close(cliente, b"Nombre de producto invalido")
            continue

        if unidad not in ALLOWED_UNITS:
            send_and_close(cliente, b"Unidad invalida. Use kilos o unidades")
            continue

        precio = parse_positive_number(precio_raw)
        if precio is None:
            send_and_close(cliente, b"Precio invalido")
            continue

        try:
            catalog = load_catalog()
            key = normalize_product(producto)
            catalog[key] = {
                "nombre": producto,
                "key": key,
                "unidad": unidad,
                "precio": precio,
            }
            save_catalog(catalog)
            send_and_close(cliente, b"Producto actualizado")
        except OSError:
            send_and_close(cliente, b"Error guardando producto")
        continue

    # ================= REGISTRAR VENTA =================
    if command.startswith("VENTA"):
        partes = command.split("|", 4)
        if len(partes) != 5:
            send_and_close(cliente, b"Formato invalido de venta")
            continue

        _, usuario_cmd, producto, cantidad_raw, unidad_cmd = [p.strip() for p in partes]
        if usuario_cmd != sesion["user"] and sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        if not valid_field(producto, max_len=120):
            send_and_close(cliente, b"Producto invalido")
            continue

        cantidad = parse_positive_number(cantidad_raw)
        if cantidad is None:
            send_and_close(cliente, b"Cantidad invalida")
            continue

        catalog = load_catalog()
        key = normalize_product(producto)
        item = catalog.get(key)
        if not item:
            send_and_close(cliente, b"Producto no configurado por admin")
            continue

        if unidad_cmd.lower() != item["unidad"]:
            send_and_close(cliente, b"Unidad no coincide con producto")
            continue

        total = cantidad * item["precio"]
        detalle = (
            f"{fecha} | {addr} | VENTA|{usuario_cmd}|{item['nombre']}|"
            f"{cantidad:.2f}|{item['unidad']}|{item['precio']:.2f}|{total:.2f}\n"
        )

        try:
            with open(f"{BASE_PATH}/datos/ventas.txt", "a", encoding="utf-8") as f:
                f.write(detalle)
            send_and_close(cliente, f"Venta registrada|TOTAL={total:.2f}")
        except OSError:
            send_and_close(cliente, b"Error registrando venta")
        continue

    # ================= REGISTRAR INVENTARIO =================
    if command.startswith("INVENTARIO"):
        partes = command.split("|", 4)
        if len(partes) != 5:
            send_and_close(cliente, b"Formato invalido de inventario")
            continue

        _, usuario_cmd, producto, cantidad_raw, unidad_cmd = [p.strip() for p in partes]
        if usuario_cmd != sesion["user"] and sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        if not valid_field(producto, max_len=120):
            send_and_close(cliente, b"Producto invalido")
            continue

        cantidad = parse_positive_number(cantidad_raw)
        if cantidad is None:
            send_and_close(cliente, b"Cantidad invalida")
            continue

        catalog = load_catalog()
        key = normalize_product(producto)
        item = catalog.get(key)
        if not item:
            send_and_close(cliente, b"Producto no configurado por admin")
            continue

        if unidad_cmd.lower() != item["unidad"]:
            send_and_close(cliente, b"Unidad no coincide con producto")
            continue

        detalle = (
            f"{fecha} | {addr} | INVENTARIO|{usuario_cmd}|{item['nombre']}|"
            f"{cantidad:.2f}|{item['unidad']}|{item['precio']:.2f}\n"
        )

        try:
            with open(f"{BASE_PATH}/datos/inventario.txt", "a", encoding="utf-8") as f:
                f.write(detalle)
            send_and_close(cliente, b"Inventario actualizado")
        except OSError:
            send_and_close(cliente, b"Error actualizando inventario")
        continue

    # ================= VER LOGS =================
    if command == "SOLICITAR_LOGS":
        if sesion["rol"] not in ["admin", "supervisor"]:
            send_and_close(cliente, b"No autorizado")
            continue

        try:
            with open(f"{BASE_PATH}/logs/log_general.txt", "r", encoding="utf-8") as f:
                send_and_close(cliente, f.read())
        except OSError:
            send_and_close(cliente, b"Sin logs")

        continue

    # ================= VER VENTAS =================
    if command == "VER_VENTAS":
        if sesion["rol"] not in ["admin", "supervisor"]:
            send_and_close(cliente, b"No autorizado")
            continue

        try:
            with open(f"{BASE_PATH}/datos/ventas.txt", "r", encoding="utf-8") as f:
                send_and_close(cliente, f.read())
        except OSError:
            send_and_close(cliente, b"Sin ventas")

        continue

    # ================= VER INVENTARIO =================
    if command == "VER_INVENTARIO":
        if sesion["rol"] not in ["admin", "supervisor"]:
            send_and_close(cliente, b"No autorizado")
            continue

        try:
            with open(f"{BASE_PATH}/datos/inventario.txt", "r", encoding="utf-8") as f:
                send_and_close(cliente, f.read())
        except OSError:
            send_and_close(cliente, b"Sin inventario")

        continue

    # ================= CREAR USUARIO DESDE ADMIN =================
    if command.startswith("CREAR_USUARIO"):
        if sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        try:
            partes = command.split("|")
            if len(partes) != 4:
                send_and_close(cliente, b"Formato invalido. Use: CREAR_USUARIO|usuario|pass|rol")
                continue

            _, nuevo_user, nueva_pass, nuevo_rol = [p.strip() for p in partes]
            nuevo_rol = nuevo_rol.lower()

            if not valid_field(nuevo_user):
                send_and_close(cliente, b"Nombre de usuario invalido")
                continue

            if not valid_field(nueva_pass, max_len=128):
                send_and_close(cliente, b"Password invalido")
                continue

            if nuevo_rol not in ["admin", "supervisor", "empleado"]:
                send_and_close(cliente, b"Rol invalido")
                continue

            ruta = f"{BASE_PATH}/usuarios.txt"
            existe = False

            if os.path.exists(ruta):
                with open(ruta, "r", encoding="utf-8") as f:
                    for linea in f:
                        parsed = parse_user_line(linea)
                        if parsed is None:
                            continue
                        username, _, _ = parsed
                        if username == nuevo_user:
                            existe = True
                            break

            if existe:
                send_and_close(cliente, b"Usuario ya existe")
                continue

            password_hash = hash_pass(nueva_pass)

            with open(ruta, "a", encoding="utf-8") as f:
                f.write(f"{nuevo_user},{password_hash},{nuevo_rol}\n")

            send_and_close(cliente, b"Usuario creado correctamente")
        except OSError as exc:
            print("ERROR CREAR USUARIO:", type(exc).__name__, str(exc))
            send_and_close(cliente, b"Error al crear usuario")

        continue

    # ===== MONITOR EN VIVO ADMIN =====
    if command == "MONITOR":
        if sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        try:
            with open(f"{BASE_PATH}/logs/log_general.txt", "r", encoding="utf-8") as f:
                lineas = f.readlines()[-15:]
                send_and_close(cliente, "".join(lineas))
        except OSError:
            send_and_close(cliente, b"Sin actividad")

        continue

    send_and_close(cliente, b"Comando no reconocido")
