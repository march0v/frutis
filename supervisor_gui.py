import os
import socket
import ssl
import tkinter as tk
from tkinter import messagebox, simpledialog

SERVER_IP = os.getenv("FRUTIS_SERVER_IP", "172.25.250.11")
SERVER_PORT = int(os.getenv("FRUTIS_SERVER_PORT", "5000"))


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


def login_supervisor():
    user = simpledialog.askstring("Supervisor", "Usuario:")
    password = simpledialog.askstring("Supervisor", "Contrasena:", show="*")
    if not user or not password:
        return None, None

    respuesta = enviar(f"LOGIN|{user}|{password}")
    partes = respuesta.split("|")
    if len(partes) < 3 or partes[0] != "OK":
        messagebox.showerror("Error", "Credenciales invalidas")
        return None, None

    rol = partes[1].strip()
    token = partes[2].strip()
    if rol not in ["supervisor", "admin"]:
        messagebox.showerror("Error", "No autorizado para este cliente")
        return None, None

    return user, token, rol


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

USUARIO, SESSION_TOKEN, ROL = login_supervisor()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel()
ventana.title("FRUTIS - SUPERVISOR")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

tk.Label(ventana, text=f"{ROL.capitalize()}: {USUARIO}", font=("Arial", 13)).pack(pady=10)
tk.Button(ventana, text="Ver Logs", width=28, command=lambda: ver_respuesta("Logs", "SOLICITAR_LOGS")).pack(pady=5)
tk.Button(ventana, text="Ver Ventas", width=28, command=lambda: ver_respuesta("Ventas", "VER_VENTAS")).pack(pady=5)
tk.Button(ventana, text="Ver Inventario", width=28, command=lambda: ver_respuesta("Inventario", "VER_INVENTARIO")).pack(pady=5)

ventana.mainloop()
