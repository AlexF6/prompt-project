# app.py
# -------------------------------------------------------------
# Prototipo académico: Agenda de Citas Médicas (Flask)
# Características:
# - Registro de pacientes (nombre, documento, teléfono, correo)
# - Agendar, listar y cancelar citas (fecha, hora, médico)
# - Interfaz web mínima en HTML/CSS (render_template_string)
# - Persistencia en memoria (resetea al reiniciar)
#
# Ejecución:
#   pip install flask
#   python app.py
#   Navegar a http://127.0.0.1:5000/
# -------------------------------------------------------------

from flask import Flask, request, redirect, url_for, render_template_string, flash
from datetime import datetime
import itertools

app = Flask(__name__)
app.secret_key = "demo-academico"  # Necesario para flash messages (académico)

# -----------------------------
# "Base de datos" en memoria
# -----------------------------
# Estructuras simples para fines académicos. En producción usar DB real.
patients = {}        # id -> dict(nombre, documento, telefono, correo)
appointments = {}    # id -> dict(paciente_id, fecha (YYYY-MM-DD), hora (HH:MM), medico, estado)
pid_counter = itertools.count(start=1)
aid_counter = itertools.count(start=1)

# Algunos médicos de ejemplo para el selector (puede editarse libremente)
DEFAULT_DOCTORS = ["Dra. González", "Dr. Pérez", "Dra. Ramírez", "Dr. López"]

# -----------------------------
# Utilidades
# -----------------------------
def parse_datetime(date_str: str, time_str: str) -> datetime:
    """Convierte fecha y hora de formularios a datetime para ordenar/validar."""
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

def has_conflict(medico: str, fecha: str, hora: str, exclude_appointment_id: int = None) -> bool:
    """
    Verifica si ya existe una cita para el mismo médico en la misma fecha y hora.
    Opcionalmente excluye una cita por ID (para futuros updates).
    """
    for a_id, a in appointments.items():
        if exclude_appointment_id and a_id == exclude_appointment_id:
            continue
        if a["medico"].strip().lower() == medico.strip().lower() and a["fecha"] == fecha and a["hora"] == hora:
            return True
    return False

def upcoming_sorted(aps: dict) -> list:
    """Devuelve la lista de citas ordenada por fecha/hora ascendente."""
    def keyfun(item):
        _, a = item
        return parse_datetime(a["fecha"], a["hora"])
    return sorted(aps.items(), key=keyfun)

# -----------------------------
# Plantillas (HTML+CSS simples)
# -----------------------------
BASE_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Agenda de Citas Médicas</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root { --c1:#0ea5e9; --c2:#0369a1; --ok:#16a34a; --err:#dc2626; --bg:#f8fafc; }
    body { font-family: system-ui, Arial, sans-serif; background: var(--bg); margin:0; color:#0f172a; }
    header { background: linear-gradient(90deg, var(--c1), var(--c2)); color:white; padding:16px 20px; }
    header h1 { margin:0; font-size:1.25rem; }
    nav a { color:white; text-decoration:none; margin-right:12px; }
    .container { max-width: 1100px; margin: 20px auto; padding: 0 16px; }
    .card { background:white; border:1px solid #e2e8f0; border-radius:12px; padding:16px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
    .grid { display:grid; gap:16px; }
    .grid-2 { grid-template-columns: 1fr 1fr; }
    .grid-3 { grid-template-columns: 1fr 1fr 1fr; }
    table { width:100%; border-collapse: collapse; }
    th, td { text-align:left; padding:10px; border-bottom:1px solid #e2e8f0; }
    th { background:#f1f5f9; }
    .btn { display:inline-block; padding:8px 12px; border-radius:8px; border:1px solid #e2e8f0; background:#fff; cursor:pointer; }
    .btn.primary { background: var(--c1); color:white; border-color: transparent; }
    .btn.danger { background: var(--err); color:white; border-color: transparent; }
    .btn.ok { background: var(--ok); color:white; border-color: transparent; }
    .field { display:flex; flex-direction:column; margin-bottom:10px; }
    .field label { font-size:.9rem; color:#334155; margin-bottom:6px; }
    .field input, .field select { padding:10px; border:1px solid #cbd5e1; border-radius:8px; }
    .muted { color:#64748b; font-size:.9rem; }
    .flash { padding:10px 12px; border-radius:8px; margin-bottom:10px; }
    .flash.ok { background:#dcfce7; color:#166534; }
    .flash.err { background:#fee2e2; color:#991b1b; }
    footer { text-align:center; color:#64748b; padding:20px 0 40px; }
    @media (max-width: 900px) { .grid-2, .grid-3 { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div class="container" style="display:flex; align-items:center; justify-content:space-between;">
      <h1>Agenda de Citas Médicas</h1>
      <nav>
        <a href="{{ url_for('home') }}">Agenda</a>
        <a href="{{ url_for('patients_page') }}">Pacientes</a>
      </nav>
    </div>
  </header>

  <main class="container">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for cat, msg in messages %}
          <div class="flash {{ 'ok' if cat=='ok' else 'err' }}">{{ msg }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    {{ content|safe }}
  </main>

  <footer>
    <p class="muted">Prototipo académico &mdash; Flask monolítico, memoria volátil.</p>
  </footer>
</body>
</html>
"""

HOME_HTML = """
<div class="grid grid-2">
  <section class="card">
    <h2 style="margin-top:0;">Agendar nueva cita</h2>
    {% if not patients %}
      <p class="muted">Primero registra al menos un paciente en la pestaña <b>Pacientes</b>.</p>
    {% else %}
    <form method="post" action="{{ url_for('create_appointment') }}">
      <div class="field">
        <label>Paciente</label>
        <select name="paciente_id" required>
          <option value="" selected disabled>Selecciona un paciente...</option>
          {% for p_id, p in patients.items() %}
            <option value="{{ p_id }}">{{ p['nombre'] }} ({{ p['documento'] }})</option>
          {% endfor %}
        </select>
      </div>
      <div class="grid grid-3">
        <div class="field">
          <label>Fecha</label>
          <input type="date" name="fecha" required>
        </div>
        <div class="field">
          <label>Hora</label>
          <input type="time" name="hora" required>
        </div>
        <div class="field">
          <label>Médico</label>
          <select name="medico" required>
            <option value="" selected disabled>Selecciona...</option>
            {% for m in doctors %}
              <option value="{{ m }}">{{ m }}</option>
            {% endfor %}
          </select>
        </div>
      </div>
      <button class="btn primary" type="submit">Agendar</button>
    </form>
    {% endif %}
    <p class="muted" style="margin-top:8px;">El sistema valida conflictos por médico (misma fecha y hora no permitida).</p>
  </section>

  <section class="card">
    <h2 style="margin-top:0;">Filtrar agenda por médico</h2>
    <form method="get" action="{{ url_for('home') }}">
      <div class="grid grid-3">
        <div class="field">
          <label>Médico</label>
          <select name="medico">
            <option value="">Todos</option>
            {% for m in doctors %}
              <option value="{{ m }}" {{ 'selected' if request.args.get('medico')==m else '' }}>{{ m }}</option>
            {% endfor %}
          </select>
        </div>
      </div>
      <button class="btn" type="submit">Aplicar filtro</button>
      {% if request.args.get('medico') %}
        <a class="btn" href="{{ url_for('home') }}">Limpiar</a>
      {% endif %}
    </form>
  </section>
</div>

<section class="card" style="margin-top:16px;">
  <h2 style="margin-top:0;">Citas programadas</h2>
  {% if not appts %}
    <p class="muted">No hay citas programadas aún.</p>
  {% else %}
  <div style="overflow-x:auto;">
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Fecha</th>
          <th>Hora</th>
          <th>Médico</th>
          <th>Paciente</th>
          <th>Documento</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {% for a_id, a in appts %}
          {% set p = patients.get(a['paciente_id']) %}
          <tr>
            <td>#{{ a_id }}</td>
            <td>{{ a['fecha'] }}</td>
            <td>{{ a['hora'] }}</td>
            <td>{{ a['medico'] }}</td>
            <td>{{ p['nombre'] if p else '—' }}</td>
            <td>{{ p['documento'] if p else '—' }}</td>
            <td>
              <form method="post" action="{{ url_for('cancel_appointment', appointment_id=a_id) }}" onsubmit="return confirm('¿Cancelar la cita #{{a_id}}?');" style="display:inline;">
                <button class="btn danger" type="submit">Cancelar</button>
              </form>
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
</section>
"""

PATIENTS_HTML = """
<div class="grid grid-2">
  <section class="card">
    <h2 style="margin-top:0;">Registrar paciente</h2>
    <form method="post" action="{{ url_for('create_patient') }}">
      <div class="field">
        <label>Nombre completo</label>
        <input type="text" name="nombre" placeholder="Ej: Ana María Ruiz" required>
      </div>
      <div class="field">
        <label>Documento</label>
        <input type="text" name="documento" placeholder="CC / DNI / Pasaporte" required>
      </div>
      <div class="field">
        <label>Teléfono</label>
        <input type="tel" name="telefono" placeholder="Ej: +57 300 123 45 67" required>
      </div>
      <div class="field">
        <label>Correo</label>
        <input type="email" name="correo" placeholder="ejemplo@correo.com" required>
      </div>
      <button class="btn primary" type="submit">Registrar</button>
    </form>
    <p class="muted" style="margin-top:8px;">El documento debe ser único. Si ya existe, se mostrará un mensaje.</p>
  </section>

  <section class="card">
    <h2 style="margin-top:0;">Pacientes registrados</h2>
    {% if not patients %}
      <p class="muted">Aún no hay pacientes.</p>
    {% else %}
      <div style="overflow-x:auto;">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Nombre</th>
              <th>Documento</th>
              <th>Teléfono</th>
              <th>Correo</th>
            </tr>
          </thead>
          <tbody>
            {% for p_id, p in patients.items() %}
              <tr>
                <td>#{{ p_id }}</td>
                <td>{{ p['nombre'] }}</td>
                <td>{{ p['documento'] }}</td>
                <td>{{ p['telefono'] }}</td>
                <td>{{ p['correo'] }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% endif %}
  </section>
</div>
"""

# -----------------------------
# Rutas
# -----------------------------
@app.route("/")
def home():
    medico_filter = request.args.get("medico", "").strip()
    # Ordenar citas por fecha/hora
    ordered = upcoming_sorted(appointments)
    if medico_filter:
        ordered = [(i, a) for (i, a) in ordered if a["medico"].strip().lower() == medico_filter.strip().lower()]
    content = render_template_string(
        HOME_HTML,
        patients=patients,
        appts=ordered,
        doctors=DEFAULT_DOCTORS
    )
    return render_template_string(BASE_HTML, content=content)

@app.route("/patients")
def patients_page():
    content = render_template_string(PATIENTS_HTML, patients=patients)
    return render_template_string(BASE_HTML, content=content)

@app.route("/patients", methods=["POST"])
def create_patient():
    nombre = request.form.get("nombre", "").strip()
    documento = request.form.get("documento", "").strip()
    telefono = request.form.get("telefono", "").strip()
    correo = request.form.get("correo", "").strip()

    # Validaciones mínimas
    if not all([nombre, documento, telefono, correo]):
        flash("Todos los campos son obligatorios.", "err")
        return redirect(url_for("patients_page"))

    # Documento único
    for p in patients.values():
        if p["documento"].strip().lower() == documento.lower():
            flash("Ya existe un paciente con ese documento.", "err")
            return redirect(url_for("patients_page"))

    p_id = next(pid_counter)
    patients[p_id] = {
        "nombre": nombre,
        "documento": documento,
        "telefono": telefono,
        "correo": correo
    }
    flash(f"Paciente #{p_id} registrado correctamente.", "ok")
    return redirect(url_for("patients_page"))

@app.route("/appointments", methods=["POST"])
def create_appointment():
    try:
        paciente_id = int(request.form.get("paciente_id", "0"))
    except ValueError:
        paciente_id = 0
    fecha = request.form.get("fecha", "").strip()
    hora = request.form.get("hora", "").strip()
    medico = request.form.get("medico", "").strip()

    # Validaciones mínimas
    if paciente_id not in patients:
        flash("Paciente no válido o no seleccionado.", "err")
        return redirect(url_for("home"))

    # Validar formato fecha/hora
    try:
        _ = parse_datetime(fecha, hora)
    except Exception:
        flash("Fecha u hora con formato inválido.", "err")
        return redirect(url_for("home"))

    if not medico:
        flash("Debe seleccionar un médico.", "err")
        return redirect(url_for("home"))

    # Validar conflicto de agenda (médico/fecha/hora)
    if has_conflict(medico, fecha, hora):
        flash("Conflicto de agenda: ese médico ya tiene una cita en ese horario.", "err")
        return redirect(url_for("home"))

    a_id = next(aid_counter)
    appointments[a_id] = {
        "paciente_id": paciente_id,
        "fecha": fecha,
        "hora": hora,
        "medico": medico,
        "estado": "Programada"
    }
    flash(f"Cita #{a_id} creada correctamente.", "ok")
    return redirect(url_for("home"))

@app.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
def cancel_appointment(appointment_id: int):
    if appointment_id not in appointments:
        flash("La cita no existe.", "err")
        return redirect(url_for("home"))
    # Estrategia simple: eliminar. Alternativa: marcar estado "Cancelada".
    del appointments[appointment_id]
    flash(f"Cita #{appointment_id} cancelada.", "ok")
    return redirect(url_for("home"))

# -----------------------------
# Datos semilla (opcional)
# -----------------------------
def seed_demo():
    """Registra 2 pacientes de muestra para agilizar la demo."""
    if not patients:
        p1 = next(pid_counter)
        patients[p1] = {"nombre": "Juan Pérez", "documento": "CC-1001", "telefono": "3000000001", "correo": "juan@example.com"}
        p2 = next(pid_counter)
        patients[p2] = {"nombre": "Ana Ruiz", "documento": "CC-1002", "telefono": "3000000002", "correo": "ana@example.com"}

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    seed_demo()
    app.run(debug=True)
