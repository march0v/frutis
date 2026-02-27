import os
import socket
import ssl
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

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
        return None, None, None

    respuesta = enviar(f"LOGIN|{user}|{password}")
    partes = respuesta.split("|")
    if len(partes) < 3 or partes[0] != "OK":
        messagebox.showerror("Error", "Credenciales invalidas")
        return None, None, None

    rol = partes[1].strip()
    token = partes[2].strip()
    if rol not in ["supervisor", "admin"]:
        messagebox.showerror("Error", "No autorizado para este cliente")
        return None, None, None

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


def cargar_texto(comando):
    contenido = ejecutar_comando(comando)
    if contenido:
        viewer.delete("1.0", "end")
        viewer.insert("1.0", contenido)


def cargar_catalogo():
    respuesta = ejecutar_comando("LISTAR_PRODUCTOS")
    if not respuesta:
        return

    tabla.delete(*tabla.get_children())
    lines = [ln.strip() for ln in respuesta.splitlines() if ln.strip()]
    if not lines or lines[0].startswith("Sin productos"):
        estado_var.set("Catalogo vacio")
        return

    for row in lines[1:]:
        parts = row.split("|")
        if len(parts) != 3:
            continue
        tabla.insert("", "end", values=(parts[0], parts[1], f"$ {parts[2]}"))

    estado_var.set(f"Catalogo visible: {len(tabla.get_children())}")


root = tk.Tk()
root.withdraw()

USUARIO, SESSION_TOKEN, ROL = login_supervisor()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel(root)
ventana.title("FRUTIS | Panel Supervisor")
ventana.geometry("980x620")
ventana.configure(bg="#f4f7fb")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

style = ttk.Style(ventana)
style.theme_use("clam")
style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), background="#f4f7fb", foreground="#1f2a44")
style.configure("Sub.TLabel", font=("Segoe UI", 10), background="#f4f7fb", foreground="#4a5568")
style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)

header = ttk.Frame(ventana, padding=(18, 14))
header.pack(fill="x")
ttk.Label(header, text="Centro de Supervision", style="Header.TLabel").pack(anchor="w")
ttk.Label(header, text=f"Sesion: {USUARIO} ({ROL})", style="Sub.TLabel").pack(anchor="w")

main = ttk.Frame(ventana, padding=(16, 8, 16, 16))
main.pack(fill="both", expand=True)
main.columnconfigure(0, weight=1)
main.columnconfigure(1, weight=1)
main.rowconfigure(1, weight=1)

acciones = ttk.LabelFrame(main, text="Consultas", padding=12)
acciones.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

for txt, cmd in [
    ("Ver Logs", "SOLICITAR_LOGS"),
    ("Ver Ventas", "VER_VENTAS"),
    ("Ver Inventario", "VER_INVENTARIO"),
]:
    ttk.Button(acciones, text=txt, style="Action.TButton", command=lambda c=cmd: cargar_texto(c)).pack(fill="x", pady=4)

panel_catalogo = ttk.LabelFrame(main, text="Catalogo de precios", padding=12)
panel_catalogo.grid(row=0, column=1, sticky="nsew", pady=(0, 10))

ttk.Button(panel_catalogo, text="Refrescar catalogo", command=cargar_catalogo).pack(anchor="w", pady=(0, 8))

tabla = ttk.Treeview(panel_catalogo, columns=("producto", "unidad", "precio"), show="headings", height=8)
tabla.heading("producto", text="Producto")
tabla.heading("unidad", text="Unidad")
tabla.heading("precio", text="Precio")
tabla.column("producto", width=220)
tabla.column("unidad", width=100, anchor="center")
tabla.column("precio", width=100, anchor="e")
tabla.pack(fill="both", expand=True)

viewer_box = ttk.LabelFrame(main, text="Detalle", padding=12)
viewer_box.grid(row=1, column=0, columnspan=2, sticky="nsew")
viewer = ScrolledText(viewer_box, wrap="word", font=("Consolas", 10), height=16)
viewer.pack(fill="both", expand=True)

estado_var = tk.StringVar(value="Listo")
ttk.Label(ventana, textvariable=estado_var, anchor="w", padding=(16, 8)).pack(fill="x")

cargar_catalogo()
ventana.mainloop()
