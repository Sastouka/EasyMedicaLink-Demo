# developpeur.py  –  Espace Développeur : clés machines + comptes admin
from datetime import date
from pathlib import Path
import json, os
from flask import (
    Blueprint, render_template_string, request,
    redirect, url_for, flash, session
)

import login as login_mod
import activation

# ───────── 1. Paramètres ─────────
_DEV_MAIL = "sastoukadigital@gmail.com"
_DEV_HASH = login_mod.hash_password("Sastouka_1989")
TRIAL_DAYS = activation.TRIAL_DAYS
PLANS = [
    ("essai",    f"Essai {TRIAL_DAYS} j"),
    ("1 mois",   "1 mois"),
    ("1 an",     "1 an"),
    ("illimité", "Illimité")
]

KEY_DB = Path(activation.MEDICALINK_FILES) / "dev_keys.json"
os.makedirs(KEY_DB.parent, exist_ok=True)

def _load_keys() -> dict:
    if KEY_DB.exists():
        return json.loads(KEY_DB.read_text(encoding="utf-8"))
    return {}

def _save_keys(d: dict):
    KEY_DB.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

developpeur_bp = Blueprint("developpeur_bp", __name__, url_prefix="/developpeur")

# ───────── 2. Templates ─────────
LOGIN_HTML = """
<!doctype html><html lang='fr'>
{{ pwa_head()|safe }}
<head><meta charset='utf-8'>
<title>Dev | Connexion</title>
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'></head>
<body class='vh-100 d-flex align-items-center justify-content-center bg-light'>
<div class='card p-4 shadow' style='max-width:380px;width:100%'>
<h4 class='mb-3 text-center'>Espace Développeur</h4>
{% with m=get_flashed_messages(with_categories=true) %}{% for c,msg in m %}
<div class='alert alert-{{c}}'>{{msg}}</div>{% endfor %}{% endwith %}
<form method='POST'>
  <input name='email' class='form-control mb-2' placeholder='Email' required>
  <input name='password' type='password' class='form-control mb-3' placeholder='Mot de passe' required>
  <button class='btn btn-primary w-100'>Se connecter</button>
</form></div></body></html>"""

DASH_HTML = """
<!doctype html>
<html lang='fr'>
{{ pwa_head()|safe }}
<head>
<meta charset='utf-8'>
<title>Développeur | Dashboard</title>

<!-- CSS externes -->
<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
<link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css' rel='stylesheet'>
<link href='https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css' rel='stylesheet'>

<style>
:root{
  --grad1:#4b6cb7;  /* bleu   */
  --grad2:#182848;  /* indigo */
}
body{background:#f5f7fb;}
.navbar{
  background:linear-gradient(90deg,var(--grad1),var(--grad2));
}
.card-header{
  background:linear-gradient(45deg,var(--grad1),var(--grad2));
  color:#fff;font-weight:600;
}
.section-icon{margin-right:.45rem;}
.table thead{background:#e9ecef}
.btn-grad{
  background:linear-gradient(90deg,var(--grad1),var(--grad2));
  border:none;color:#fff;
}
</style>
</head>

<body>
<nav class='navbar navbar-dark shadow'>
  <div class='container-fluid'>
    <span class='navbar-brand d-flex align-items-center gap-2'>
      <i class='fas fa-code'></i> Mode Développeur <span class='fw-light'>EASYMEDICALINK</span>
    </span>
    <a href='{{ url_for("developpeur_bp.dev_logout") }}'
       class='btn btn-sm btn-outline-light rounded-pill'><i class='fas fa-sign-out-alt'></i> Quitter</a>
  </div>
</nav>

<div class='container my-4'>

  <!-- Message flash global -->
  {% with m=get_flashed_messages(with_categories=true) %}
    {% if m %}
      {% for c,msg in m %}
        <div class='alert alert-{{c}} alert-dismissible fade show shadow-sm' role='alert'>
          <i class='fas fa-info-circle me-2'></i>{{msg}}
          <button type='button' class='btn-close' data-bs-dismiss='alert'></button>
        </div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <!-- Générateur de clés -->
  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-key section-icon'></i>Générer une clé machine</h5>
    <div class='card-body'>
      <form class='row gy-2 gx-3 align-items-end' method='POST'
            action='{{ url_for("developpeur_bp.gen_custom") }}'>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-desktop me-1'></i>ID machine</label>
          <input name='machine_id' class='form-control' placeholder='16 caractères' required>
        </div>
        <div class='col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-user me-1'></i>Nom</label>
          <input name='nom' class='form-control' required>
        </div>
        <div class='col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-user me-1'></i>Prénom</label>
          <input name='prenom' class='form-control' required>
        </div>
        <div class='col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-file-signature me-1'></i>Plan</label>
          <select name='plan' class='form-select'>
            {% for c,l in plans %}<option value='{{c}}'>{{l}}</option>{% endfor %}
          </select>
        </div>
        <div class='col-md-2 d-grid'>
          <button class='btn btn-grad'><i class='fas fa-magic me-1'></i>Générer</button>
        </div>
        {% if key %}
          <div class='col-12'>
            <div class='alert alert-info mt-3 shadow-sm'>
              <i class='fas fa-check-circle me-2'></i>
              <strong>Clé&nbsp;:</strong> {{key}}
            </div>
          </div>
        {% endif %}
      </form>
    </div>
  </div>

  <!-- Tableau machines -->
  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-server section-icon'></i>Clés machines</h5>
    <div class='card-body'>
      <table id='tblKeys' class='table table-striped table-hover rounded overflow-hidden'>
        <thead><tr><th>ID</th><th>Propriétaire</th><th>Plan</th><th>Clé</th></tr></thead>
        <tbody>
          {% for mid,info in machines.items() %}
            <tr>
              <td class='fw-semibold'>{{mid}}</td>
              <td>{{info.prenom}}&nbsp;{{info.nom}}</td>
              <td>{{info.plan}}</td>
              <td class='text-break'>{{info.key}}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Création admin -->
  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-user-plus section-icon'></i>Créer un compte admin</h5>
    <div class='card-body'>
      <form class='row gy-2 gx-3 align-items-end' method='POST'
            action='{{ url_for("developpeur_bp.create_admin") }}'>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-envelope me-1'></i>Email</label>
          <input name='email' type='email' class='form-control' required>
        </div>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-key me-1'></i>Mot de passe</label>
          <input name='password' type='password' class='form-control' required>
        </div>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-key me-1'></i>Confirmer</label>
          <input name='confirm' type='password' class='form-control' required>
        </div>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-hospital me-1'></i>Clinique</label>
          <input name='clinic' class='form-control' required>
        </div>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-calendar-alt me-1'></i>Date création</label>
          <input name='creation_date' type='date' class='form-control' required>
        </div>
        <div class='col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-map-marker-alt me-1'></i>Adresse</label>
          <input name='address' class='form-control' required>
        </div>
        <input type='hidden' name='role' value='admin'>
        <div class='col-12 d-grid mt-2'>
          <button class='btn btn-grad'><i class='fas fa-user-plus me-1'></i>Créer</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Tableau admins -->
  <div class='card shadow-sm'>
    <h5 class='card-header'><i class='fas fa-users section-icon'></i>Comptes admin</h5>
    <div class='card-body'>
      <table id='tblAdmin' class='table table-striped table-hover rounded overflow-hidden'>
        <thead><tr><th>Email</th><th>Clinique</th><th>Actif</th><th>Actions</th></tr></thead>
        <tbody>
          {% for e,u in admins.items() %}
            <tr>
              <td>{{e}}</td><td>{{u.clinic}}</td>
              <td><span class='badge {{'bg-success' if u.active else 'bg-secondary'}}'>
                   {{'Oui' if u.active else 'Non'}}</span></td>
              <td class='text-nowrap'>
                <a class='btn btn-sm btn-outline-secondary' title='Activer/Désactiver'
                   href='{{ url_for('developpeur_bp.toggle_active',admin_email=e) }}'>
                   <i class='fas fa-power-off'></i></a>
                <a class='btn btn-sm btn-outline-danger' title='Supprimer'
                   href='{{ url_for('developpeur_bp.delete_admin',admin_email=e) }}'>
                   <i class='fas fa-trash'></i></a>
              </td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div>

<!-- JS -->
<script src='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'></script>
<script src='https://code.jquery.com/jquery-3.6.0.min.js'></script>
<script src='https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js'></script>
<script src='https://cdn.datatables.net/1.13.1/js/dataTables.bootstrap5.min.js'></script>
<script>
  $(function(){
    $('#tblKeys, #tblAdmin').DataTable({
      lengthChange:false,
      language:{url:'//cdn.datatables.net/plug-ins/1.13.1/i18n/fr-FR.json'}
    });
  });
</script>
</body>
</html>"""

# ───────── 3. Helpers ─────────
def _dev_only():
    if not session.get("is_developpeur"):
        return redirect(url_for("developpeur_bp.login_page"))

def _store_key(mid, plan, key, nom, prenom):
    d = _load_keys()
    d[mid] = {"plan": plan, "key": key, "nom": nom, "prenom": prenom}
    _save_keys(d)

# ───────── 4. Routes ─────────
@developpeur_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        if request.form["email"].lower() == _DEV_MAIL \
           and login_mod.hash_password(request.form["password"]) == _DEV_HASH:
            session["is_developpeur"] = True
            flash("Mode développeur activé ✔", "success")
            return redirect(url_for("developpeur_bp.dashboard"))
        flash("Identifiants incorrects", "danger")
    return render_template_string(LOGIN_HTML)

@developpeur_bp.route("/dev_logout")
def dev_logout():
    session.pop("is_developpeur", None)
    flash("Mode développeur désactivé", "info")
    return redirect(url_for("login.login"))

@developpeur_bp.route("/")
def dashboard():
    if (r := _dev_only()): return r
    admins = {e: u for e, u in login_mod.load_users().items() if u.get("role") == "admin"}
    return render_template_string(
        DASH_HTML,
        admins=admins,
        machines=_load_keys(),
        key=session.pop("generated_key", None),
        plans=PLANS
    )

@developpeur_bp.route("/generate", methods=["POST"])
def gen_custom():
    if (r := _dev_only()): return r
    mid   = request.form["machine_id"].strip().lower()
    plan  = request.form["plan"]
    nom   = request.form["nom"].strip()
    prenom= request.form["prenom"].strip()
    key   = activation.generate_activation_key_for_user(mid, plan)
    session["generated_key"] = key
    _store_key(mid, plan, key, nom, prenom)
    return redirect(url_for(".dashboard"))

@developpeur_bp.route("/create_admin", methods=["POST"])
def create_admin():
    if (r := _dev_only()): return r
    f, users = request.form, login_mod.load_users()
    email = f["email"].lower()
    if email in users:
        flash("Admin existe déjà", "warning")
        return redirect(url_for(".dashboard"))
    if f["password"] != f["confirm"]:
        flash("Les mots de passe ne correspondent pas", "danger")
        return redirect(url_for(".dashboard"))

    users[email] = {
        "role": "admin",
        "password": login_mod.hash_password(f["password"]),
        "clinic": f["clinic"],
        "creation_date": f["creation_date"],
        "address": f["address"],
        "active": True
    }
    login_mod.save_users(users)
    flash("Admin créé", "success")
    return redirect(url_for(".dashboard"))

@developpeur_bp.route("/toggle_active/<admin_email>")
def toggle_active(admin_email):
    if (r := _dev_only()): return r
    users = login_mod.load_users()
    if admin_email in users and users[admin_email]["role"] == "admin":
        users[admin_email]["active"] = not users[admin_email].get("active", True)
        login_mod.save_users(users)
    return redirect(url_for(".dashboard"))

@developpeur_bp.route("/delete_admin/<admin_email>")
def delete_admin(admin_email):
    if (r := _dev_only()): return r
    users = login_mod.load_users()
    users.pop(admin_email, None)
    login_mod.save_users(users)
    return redirect(url_for(".dashboard"))
