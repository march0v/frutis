import os
import socket
import ssl
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

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


def cargar_catalogo():
    respuesta = ejecutar_comando("LISTAR_PRODUCTOS")
    if not respuesta:
        return

    catalogo.clear()
    tabla.delete(*tabla.get_children())

    lines = [ln.strip() for ln in respuesta.splitlines() if ln.strip()]
    if not lines or lines[0].startswith("Sin productos"):
        productos_combo["values"] = []
        producto_var.set("")
        unidad_var.set("-")
        precio_var.set("0.00")
        total_var.set("0.00")
        estado_var.set("No hay productos configurados")
        return

    for row in lines[1:]:
        parts = row.split("|")
        if len(parts) != 3:
            continue

        nombre = parts[0].strip()
        unidad = parts[1].strip().lower()
        precio = float(parts[2].strip())
        catalogo[nombre] = {"unidad": unidad, "precio": precio}
        tabla.insert("", "end", values=(nombre, unidad, f"$ {precio:.2f}"))

    productos_combo["values"] = sorted(catalogo.keys())
    if not producto_var.get() and productos_combo["values"]:
        producto_var.set(productos_combo["values"][0])
    actualizar_producto()
    estado_var.set(f"Catalogo actualizado: {len(catalogo)} producto(s)")


def actualizar_producto(*_):
    producto = producto_var.get().strip()
    info = catalogo.get(producto)
    if not info:
        unidad_var.set("-")
        precio_var.set("0.00")
        total_var.set("0.00")
        return

    unidad_var.set(info["unidad"])
    precio_var.set(f"{info['precio']:.2f}")
    calcular_total()


def calcular_total(*_):
    producto = producto_var.get().strip()
    info = catalogo.get(producto)
    if not info:
        total_var.set("0.00")
        return

    try:
        cantidad = float(cantidad_var.get().strip())
        if cantidad <= 0:
            raise ValueError
    except ValueError:
        total_var.set("0.00")
        return

    total = cantidad * info["precio"]
    total_var.set(f"{total:.2f}")


def registrar_inventario():
    producto = producto_var.get().strip()
    info = catalogo.get(producto)
    cantidad = cantidad_var.get().strip()

    if not info:
        messagebox.showwarning("Producto", "Selecciona un producto valido")
        return

    if not cantidad:
        messagebox.showwarning("Cantidad", "Ingresa la cantidad")
        return

    resp = ejecutar_comando(f"INVENTARIO|{USUARIO}|{producto}|{cantidad}|{info['unidad']}")
    if resp:
        estado_var.set(resp)
        messagebox.showinfo("Inventario", resp)


def registrar_venta():
    producto = producto_var.get().strip()
    info = catalogo.get(producto)
    cantidad = cantidad_var.get().strip()

    if not info:
        messagebox.showwarning("Producto", "Selecciona un producto valido")
        return

    if not cantidad:
        messagebox.showwarning("Cantidad", "Ingresa la cantidad")
        return

    calcular_total()
    total_estimado = total_var.get()

    resp = ejecutar_comando(f"VENTA|{USUARIO}|{producto}|{cantidad}|{info['unidad']}")
    if resp:
        estado_var.set(resp)
        messagebox.showinfo("Venta registrada", f"Total a pagar: $ {total_estimado}\n\n{resp}")


root = tk.Tk()
root.withdraw()

USUARIO, SESSION_TOKEN = login_empleado()
if not SESSION_TOKEN:
    raise SystemExit(1)

ventana = tk.Toplevel(root)
ventana.title("FRUTIS | Terminal Empleado")
ventana.geometry("980x620")
ventana.configure(bg="#f5f8fc")
ventana.protocol("WM_DELETE_WINDOW", root.destroy)

style = ttk.Style(ventana)
style.theme_use("clam")
style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), background="#f5f8fc", foreground="#1f2a44")
style.configure("Sub.TLabel", font=("Segoe UI", 10), background="#f5f8fc", foreground="#4a5568")
style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=8)

header = ttk.Frame(ventana, padding=(18, 14))
header.pack(fill="x")
ttk.Label(header, text="Operacion de Ventas e Inventario", style="Header.TLabel").pack(anchor="w")
ttk.Label(header, text=f"Empleado: {USUARIO}", style="Sub.TLabel").pack(anchor="w")

main = ttk.Frame(ventana, padding=(16, 8, 16, 16))
main.pack(fill="both", expand=True)
main.columnconfigure(0, weight=2)
main.columnconfigure(1, weight=1)

panel = ttk.LabelFrame(main, text="Registro", padding=14)
panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

producto_var = tk.StringVar()
cantidad_var = tk.StringVar()
unidad_var = tk.StringVar(value="-")
precio_var = tk.StringVar(value="0.00")
total_var = tk.StringVar(value="0.00")

row1 = ttk.Frame(panel)
row1.pack(fill="x", pady=4)

ttk.Label(row1, text="Producto:").grid(row=0, column=0, sticky="w", padx=(0, 8))
productos_combo = ttk.Combobox(row1, textvariable=producto_var, state="readonly")
productos_combo.grid(row=0, column=1, sticky="ew")
row1.columnconfigure(1, weight=1)

row2 = ttk.Frame(panel)
row2.pack(fill="x", pady=4)

ttk.Label(row2, text="Cantidad:").grid(row=0, column=0, sticky="w", padx=(0, 8))
entry_cantidad = ttk.Entry(row2, textvariable=cantidad_var)
entry_cantidad.grid(row=0, column=1, sticky="ew")
row2.columnconfigure(1, weight=1)

resumen = ttk.Frame(panel)
resumen.pack(fill="x", pady=(10, 8))

for i, (label, var) in enumerate([
    ("Unidad del producto", unidad_var),
    ("Precio unitario", precio_var),
    ("Total estimado", total_var),
]):
    ttk.Label(resumen, text=label + ":", width=18).grid(row=i, column=0, sticky="w")
    ttk.Label(resumen, textvariable=var, font=("Segoe UI", 10, "bold")).grid(row=i, column=1, sticky="w")

acciones = ttk.Frame(panel)
acciones.pack(fill="x", pady=(10, 4))

ttk.Button(acciones, text="Registrar Venta", style="Action.TButton", command=registrar_venta).pack(side="left", padx=(0, 8))
ttk.Button(acciones, text="Agregar Inventario", style="Action.TButton", command=registrar_inventario).pack(side="left", padx=(0, 8))
ttk.Button(acciones, text="Actualizar Catalogo", command=cargar_catalogo).pack(side="left")

vista = ttk.LabelFrame(main, text="Catalogo de productos", padding=12)
vista.grid(row=0, column=1, sticky="nsew")

tabla = ttk.Treeview(vista, columns=("producto", "unidad", "precio"), show="headings", height=18)
tabla.heading("producto", text="Producto")
tabla.heading("unidad", text="Unidad")
tabla.heading("precio", text="Precio")
tabla.column("producto", width=170)
tabla.column("unidad", width=90, anchor="center")
tabla.column("precio", width=90, anchor="e")
tabla.pack(fill="both", expand=True)

estado_var = tk.StringVar(value="Listo")
ttk.Label(ventana, textvariable=estado_var, anchor="w", padding=(16, 8)).pack(fill="x")

catalogo = {}
productos_combo.bind("<<ComboboxSelected>>", actualizar_producto)
entry_cantidad.bind("<KeyRelease>", calcular_total)

cargar_catalogo()
ventana.mainloop()
