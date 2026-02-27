import socket
import ssl
import tkinter as tk
from tkinter import messagebox, simpledialog

SERVER_IP = "172.25.250.11"
SERVER_PORT = 5000


def enviar(data):
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    cliente = context.wrap_socket(socket.socket(), server_hostname=SERVER_IP)
    cliente.connect((SERVER_IP, SERVER_PORT))
    cliente.send(data.encode("utf-8"))

    try:
        respuesta = cliente.recv(65535).decode("utf-8", errors="replace")
    except OSError:
        respuesta = ""

    cliente.close()
    return respuesta


def login_admin():
    user = simpledialog.askstring("Admin Login", "Usuario:")
    password = simpledialog.askstring("Admin Login", "Contrasena:", show="*")
    if not user or not password:
        return None, None

    respuesta = enviar(f"LOGIN|{user}|{password}")
    partes = respuesta.split("|")
    if len(partes) < 3 or partes[0] != "OK":
        messagebox.showerror("Error", "Credenciales invalidas")
        return None, None

    rol = partes[1].strip()
    token = partes[2].strip()
    if rol != "admin":
        messagebox.showerror("Error", "No eres administrador")
        return None, None

    return user, token


def ejecutar_comando(comando):
    respuesta = enviar(f"TOKEN|{SESSION_TOKEN}|{comando}")
    if respuesta.startswith("FAIL|AUTH_REQUIRED"):
        messagebox.showerror("Error", "Sesion invalida o expirada")
        return ""
    if respuesta == "No autorizado":
        messagebox.showerror("Error", "No autorizado")
        return ""
    return respuesta


def ver_respuesta(titulo, comando):
    contenido = ejecutar_comando(comando)
    if not contenido:
        return

    ventana = tk.Toplevel()
    ventana.title(titulo)
    texto = tk.Text(ventana, width=90, height=30)
    texto.pack()
    texto.insert("end", contenido)


root = tk.Tk()
root.withdraw()

USUARIO, SESSION_TOKEN = login_admin()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel()
ventana.title("FRUTIS - ADMIN PANEL")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

tk.Label(ventana, text=f"Admin: {USUARIO}", font=("Arial", 13)).pack(pady=10)
tk.Button(ventana, text="Ver Inventario", width=28, command=lambda: ver_respuesta("Inventario", "VER_INVENTARIO")).pack(pady=5)
tk.Button(ventana, text="Ver Ventas", width=28, command=lambda: ver_respuesta("Ventas", "VER_VENTAS")).pack(pady=5)
tk.Button(ventana, text="Ver Logs", width=28, command=lambda: ver_respuesta("Logs", "SOLICITAR_LOGS")).pack(pady=5)
tk.Button(ventana, text="Monitor en vivo", width=28, command=lambda: ver_respuesta("Monitor", "MONITOR")).pack(pady=5)

ventana.mainloop()
