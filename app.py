# ==============================================================================
# ARCHIVO PRINCIPAL DEL BACKEND: app.py
# Sistema Web de Control y Reporte de Gastos
# Tecnologías: Python 3, Flask, SQLite3, Werkzeug Security, OpenPyXL
# ==============================================================================

import sqlite3
import io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Inicialización de la aplicación Flask
app = Flask(__name__)
# Clave secreta necesaria para cifrar las cookies de sesión del usuario
app.secret_key = 'clave_secreta_profesional_gastos_flask'
# Nombre del archivo de base de datos local SQLite
DATABASE = 'gastos.db'


def get_db_connection():
    """
    Establece y retorna una conexión activa a la base de datos SQLite.
    Configura row_factory = sqlite3.Row para acceder a las columnas por su nombre.
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Crea las tablas 'usuarios' y 'gastos' si aún no existen en la base de datos,
    e inserta el usuario administrador por defecto (usuario: admin / clave: 123).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Creación de la tabla de usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')

        # 2. Creación de la tabla de gastos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                monto REAL NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 3. Verificación e inserción del usuario por defecto 'admin' con contraseña '123' encriptada
        cursor.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
        if not cursor.fetchone():
            cursor.execute(
                'INSERT INTO usuarios (username, password_hash) VALUES (?, ?)',
                ('admin', generate_password_hash('123'))
            )

        conn.commit()


def login_required(f):
    """
    Decorador de seguridad que protege las rutas privadas del sistema.
    Si no existe una sesión iniciada ('user_id'), redirige al formulario de login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Por favor, inicia sesión para acceder al sistema.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Gestiona el inicio de sesión (GET muestra el formulario, POST valida credenciales).
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        with get_db_connection() as conn:
            user = conn.execute(
                'SELECT * FROM usuarios WHERE username = ?', (username,)
            ).fetchone()

        # Verifica si el usuario existe y compara el hash seguro de la contraseña
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('¡Bienvenido al Sistema de Control de Gastos!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales incorrectas. Intente nuevamente.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """
    Cierra la sesión activa limpiando las variables de sesión del navegador.
    """
    session.clear()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    """
    Ruta principal del sistema:
    - Filtra los gastos por rango de fechas si el usuario aplica filtros.
    - Calcula los indicadores (Total Gastado, N° de Operaciones y Gasto Promedio).
    - Renderiza la plantilla dashboard.html con los datos obtenidos.
    """
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')

    query = 'SELECT * FROM gastos WHERE 1=1'
    params = []

    if fecha_inicio:
        query += ' AND fecha >= ?'
        params.append(fecha_inicio)
    if fecha_fin:
        query += ' AND fecha <= ?'
        params.append(fecha_fin)

    query += ' ORDER BY fecha DESC, id DESC'

    with get_db_connection() as conn:
        gastos = conn.execute(query, params).fetchall()

    # Cálculo de métricas estadísticas para las tarjetas de resumen
    total_gastos = sum(g['monto'] for g in gastos)
    cantidad_registros = len(gastos)
    promedio_gasto = (total_gastos / cantidad_registros) if cantidad_registros > 0 else 0.0
    fecha_actual = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'dashboard.html',
        gastos=gastos,
        total_gastos=total_gastos,
        cantidad_registros=cantidad_registros,
        promedio_gasto=promedio_gasto,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        fecha_actual=fecha_actual
    )


@app.route('/registrar', methods=['POST'])
@login_required
def registrar_gasto():
    """
    Recibe los datos del formulario (fecha, descripción, monto),
    valida la integridad de la información y guarda el registro en SQLite.
    """
    fecha = request.form.get('fecha', '').strip()
    descripcion = request.form.get('descripcion', '').strip()
    monto_str = request.form.get('monto', '').strip()

    if not fecha or not descripcion or not monto_str:
        flash('Todos los campos son obligatorios.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        monto = float(monto_str)
        if monto <= 0:
            raise ValueError
    except ValueError:
        flash('El monto debe ser un número válido mayor a cero.', 'danger')
        return redirect(url_for('dashboard'))

    with get_db_connection() as conn:
        conn.execute(
            'INSERT INTO gastos (fecha, descripcion, monto) VALUES (?, ?, ?)',
            (fecha, descripcion, monto)
        )
        conn.commit()

    flash('Gasto registrado exitosamente.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_gasto(id):
    """
    Elimina un registro específico de la tabla 'gastos' según su ID.
    """
    with get_db_connection() as conn:
        conn.execute('DELETE FROM gastos WHERE id = ?', (id,))
        conn.commit()
    flash('Registro eliminado correctamente.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/reporte/excel')
@login_required
def exportar_excel():
    """
    Genera y descarga un archivo Excel nativo (.xlsx) con los registros actuales
    o filtrados, incluyendo estilos profesionales y fórmula dinámica de suma (=SUM).
    """
    fecha_inicio = request.args.get('fecha_inicio', '')
    fecha_fin = request.args.get('fecha_fin', '')

    query = 'SELECT id, fecha, descripcion, monto FROM gastos WHERE 1=1'
    params = []

    if fecha_inicio:
        query += ' AND fecha >= ?'
        params.append(fecha_inicio)
    if fecha_fin:
        query += ' AND fecha <= ?'
        params.append(fecha_fin)

    query += ' ORDER BY fecha DESC, id DESC'

    with get_db_connection() as conn:
        gastos = conn.execute(query, params).fetchall()

    # Creación del libro y hoja de cálculo Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte_Gastos"

    # Definición de paleta de colores, fuentes y bordes
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
    total_font = Font(bold=True, size=11)
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Título principal del documento
    ws.merge_cells('A1:D1')
    ws['A1'] = "REPORTE DETALLADO DE GASTOS"
    ws['A1'].font = Font(bold=True, size=14, color="0F172A")
    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # Encabezados de columnas
    headers = ['N°', 'Fecha', 'Descripción', 'Monto (S/)']
    ws.append([])
    ws.append(headers)

    for col_num in range(1, 5):
        cell = ws.cell(row=3, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_num != 3 else "left", vertical="center")
        cell.border = thin_border
    ws.row_dimensions[3].height = 22

    # Inserción de filas con los gastos
    row_idx = 4
    for idx, g in enumerate(gastos, start=1):
        ws.append([idx, g['fecha'], g['descripcion'], float(g['monto'])])
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=2).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=4).number_format = '#,##0.00'
        for col_num in range(1, 5):
            ws.cell(row=row_idx, column=col_num).border = thin_border
        row_idx += 1

    # Fila de cierre con el Total Acumulado mediante fórmula Excel
    ws.cell(row=row_idx, column=3, value="TOTAL ACUMULADO (S/):").alignment = Alignment(horizontal="right")
    total_cell = ws.cell(row=row_idx, column=4)
    total_cell.value = f"=SUM(D4:D{row_idx - 1})" if len(gastos) > 0 else 0.00
    total_cell.number_format = '#,##0.00'

    for col_num in range(1, 5):
        c = ws.cell(row=row_idx, column=col_num)
        c.fill = total_fill
        c.font = total_font
        c.border = thin_border

    # Ajuste del ancho de columnas para evitar texto cortado
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 16
    ws.column_dimensions['C'].width = 45
    ws.column_dimensions['D'].width = 18

    # Guardar archivo en memoria RAM y enviarlo como descarga HTTP
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=reporte_gastos.xlsx'}
    )


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
