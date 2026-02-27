import datetime
import hashlib
import os
import secrets
import socket
import ssl
import time

BASE_PATH = "/opt/frutis"

SESSION_TTL_SECONDS = 3600
LOGIN_WINDOW_SECONDS = 300
MAX_LOGIN_ATTEMPTS = 5

failed_login_attempts = {}
sessions = {}


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

    # Backward compatibility for legacy SHA256 hashes.
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
    # Required format for all non-login actions:
    # TOKEN|<session_token>|<actual_command>
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
context.load_cert_chain(certfile="server.crt", keyfile="server.key")

bindsocket = socket.socket()
bindsocket.bind(("0.0.0.0", 5000))
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

    # ================= LOG GENERAL =================
    try:
        with open(f"{BASE_PATH}/logs/log_general.txt", "a", encoding="utf-8") as f:
            f.write(log_entry)
    except OSError as exc:
        print("ERROR LOG GENERAL:", exc)

    # ================= REGISTRAR VENTA =================
    if command.startswith("VENTA"):
        partes = command.split("|", 3)
        if len(partes) != 4:
            send_and_close(cliente, b"Formato invalido de venta")
            continue

        _, usuario_cmd, producto, cantidad = [p.strip() for p in partes]
        if usuario_cmd != sesion["user"] and sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        if not valid_field(producto, max_len=120) or not valid_field(cantidad, max_len=32):
            send_and_close(cliente, b"Datos invalidos")
            continue

        try:
            with open(f"{BASE_PATH}/datos/ventas.txt", "a", encoding="utf-8") as f:
                f.write(log_entry)
            send_and_close(cliente, b"Venta registrada")
        except OSError:
            send_and_close(cliente, b"Error registrando venta")
        continue

    # ================= REGISTRAR INVENTARIO =================
    if command.startswith("INVENTARIO"):
        partes = command.split("|", 3)
        if len(partes) != 4:
            send_and_close(cliente, b"Formato invalido de inventario")
            continue

        _, usuario_cmd, producto, cantidad = [p.strip() for p in partes]
        if usuario_cmd != sesion["user"] and sesion["rol"] != "admin":
            send_and_close(cliente, b"No autorizado")
            continue

        if not valid_field(producto, max_len=120) or not valid_field(cantidad, max_len=32):
            send_and_close(cliente, b"Datos invalidos")
            continue

        try:
            with open(f"{BASE_PATH}/datos/inventario.txt", "a", encoding="utf-8") as f:
                f.write(log_entry)
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

    # ================= DEFAULT =================
    send_and_close(cliente, b"Comando no reconocido")
