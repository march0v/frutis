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


def abrir_texto(titulo, contenido):
    ventana = tk.Toplevel(root)
    ventana.title(titulo)
    ventana.geometry("900x520")

    salida = ScrolledText(ventana, wrap="word", font=("Segoe UI", 10))
    salida.pack(fill="both", expand=True, padx=12, pady=12)
    salida.insert("1.0", contenido)


def ver_respuesta(titulo, comando):
    contenido = ejecutar_comando(comando)
    if not contenido:
        return
    abrir_texto(titulo, contenido)


def refrescar_catalogo():
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

    estado_var.set(f"Productos cargados: {len(tabla.get_children())}")


def guardar_precio():
    producto = entry_producto.get().strip()
    unidad = unidad_var.get().strip().lower()
    precio = entry_precio.get().strip()

    if not producto or not unidad or not precio:
        messagebox.showwarning("Datos incompletos", "Completa producto, unidad y precio")
        return

    resp = ejecutar_comando(f"SET_PRODUCTO|{producto}|{unidad}|{precio}")
    if resp:
        estado_var.set(resp)
        refrescar_catalogo()


def crear_usuario():
    nuevo = simpledialog.askstring("Nuevo usuario", "Usuario:")
    pwd = simpledialog.askstring("Nuevo usuario", "Contrasena:", show="*")
    rol = simpledialog.askstring("Nuevo usuario", "Rol (admin/supervisor/empleado):")
    if not nuevo or not pwd or not rol:
        return

    resp = ejecutar_comando(f"CREAR_USUARIO|{nuevo}|{pwd}|{rol}")
    if resp:
        estado_var.set(resp)
        messagebox.showinfo("Resultado", resp)


root = tk.Tk()
root.withdraw()

USUARIO, SESSION_TOKEN = login_admin()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel(root)
ventana.title("FRUTIS | Panel de Administracion")
ventana.geometry("980x620")
ventana.configure(bg="#f3f6fa")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

style = ttk.Style(ventana)
style.theme_use("clam")
style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), background="#f3f6fa", foreground="#1f2a44")
style.configure("Sub.TLabel", font=("Segoe UI", 10), background="#f3f6fa", foreground="#4a5568")
style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)

header = ttk.Frame(ventana, padding=(18, 14))
header.pack(fill="x")
ttk.Label(header, text="Panel Administrativo", style="Header.TLabel").pack(anchor="w")
ttk.Label(header, text=f"Sesion iniciada: {USUARIO}", style="Sub.TLabel").pack(anchor="w")

contenedor = ttk.Frame(ventana, padding=(16, 8, 16, 16))
contenedor.pack(fill="both", expand=True)
contenedor.columnconfigure(0, weight=1)
contenedor.columnconfigure(1, weight=2)
contenedor.rowconfigure(1, weight=1)

acciones = ttk.LabelFrame(contenedor, text="Acciones", padding=12)
acciones.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

botones = [
    ("Ver Inventario", lambda: ver_respuesta("Inventario", "VER_INVENTARIO")),
    ("Ver Ventas", lambda: ver_respuesta("Ventas", "VER_VENTAS")),
    ("Ver Logs", lambda: ver_respuesta("Logs", "SOLICITAR_LOGS")),
    ("Monitor en vivo", lambda: ver_respuesta("Monitor", "MONITOR")),
    ("Crear Usuario", crear_usuario),
]

for text, cmd in botones:
    ttk.Button(acciones, text=text, style="Action.TButton", command=cmd).pack(fill="x", pady=4)

precios = ttk.LabelFrame(contenedor, text="Productos y precios fijos", padding=12)
precios.grid(row=0, column=1, sticky="nsew", pady=(0, 10))

form = ttk.Frame(precios)
form.pack(fill="x", pady=(0, 10))

entry_producto = ttk.Entry(form)
entry_producto.grid(row=0, column=0, sticky="ew", padx=(0, 8))
entry_producto.insert(0, "Producto")

unidad_var = tk.StringVar(value="unidades")
combo_unidad = ttk.Combobox(form, textvariable=unidad_var, values=["unidades", "kilos"], state="readonly", width=12)
combo_unidad.grid(row=0, column=1, padx=(0, 8))

entry_precio = ttk.Entry(form, width=14)
entry_precio.grid(row=0, column=2, padx=(0, 8))
entry_precio.insert(0, "0.00")

ttk.Button(form, text="Guardar precio", style="Action.TButton", command=guardar_precio).grid(row=0, column=3, padx=(0, 8))
ttk.Button(form, text="Refrescar", command=refrescar_catalogo).grid(row=0, column=4)
form.columnconfigure(0, weight=1)

tabla = ttk.Treeview(precios, columns=("producto", "unidad", "precio"), show="headings", height=12)
tabla.heading("producto", text="Producto")
tabla.heading("unidad", text="Unidad")
tabla.heading("precio", text="Precio fijo")
tabla.column("producto", width=260)
tabla.column("unidad", width=100, anchor="center")
tabla.column("precio", width=120, anchor="e")
tabla.pack(fill="both", expand=True)

estado_var = tk.StringVar(value="Listo")
barra = ttk.Label(ventana, textvariable=estado_var, anchor="w", padding=(16, 8))
barra.pack(fill="x")

refrescar_catalogo()
ventana.mainloop()
