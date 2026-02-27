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


def login_empleado():
    user = simpledialog.askstring("Empleado", "Usuario:")
    password = simpledialog.askstring("Empleado", "Contrasena:", show="*")
    if not user or not password:
        return None, None

    respuesta = enviar(f"LOGIN|{user}|{password}")
    partes = respuesta.split("|")
    if len(partes) < 3 or partes[0] != "OK":
        messagebox.showerror("Error", "Credenciales invalidas")
        return None, None

    rol = partes[1].strip()
    token = partes[2].strip()
    if rol != "empleado":
        messagebox.showerror("Error", "No autorizado para este cliente")
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


def registrar_venta():
    producto = simpledialog.askstring("Venta", "Producto:")
    cantidad = simpledialog.askstring("Venta", "Cantidad:")
    if not producto or not cantidad:
        return

    resp = ejecutar_comando(f"VENTA|{USUARIO}|{producto}|{cantidad}")
    if resp:
        messagebox.showinfo("Respuesta", resp)


def registrar_inventario():
    producto = simpledialog.askstring("Inventario", "Producto:")
    cantidad = simpledialog.askstring("Inventario", "Cantidad:")
    if not producto or not cantidad:
        return

    resp = ejecutar_comando(f"INVENTARIO|{USUARIO}|{producto}|{cantidad}")
    if resp:
        messagebox.showinfo("Respuesta", resp)


root = tk.Tk()
root.withdraw()

USUARIO, SESSION_TOKEN = login_empleado()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel()
ventana.title("FRUTIS - EMPLEADO")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

tk.Label(ventana, text=f"Empleado: {USUARIO}", font=("Arial", 13)).pack(pady=10)
tk.Button(ventana, text="Registrar Venta", width=28, command=registrar_venta).pack(pady=5)
tk.Button(ventana, text="Registrar Inventario", width=28, command=registrar_inventario).pack(pady=5)

ventana.mainloop()
