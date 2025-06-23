# developpeur.py – Espace Développeur : clés machines + comptes admin
from datetime import date
from pathlib import Path
import json, os
from flask import (
    Blueprint, render_template_string, request,
    redirect, url_for, flash, session, jsonify
)
from typing import Optional # AJOUTEZ CETTE LIGNE

import login as login_mod
import activation
import utils # Import utils to access set_dynamic_base_dir and DYNAMIC_BASE_DIR

# ───────── 1. Paramètres ─────────
_DEV_MAIL = "sastoukadigital@gmail.com"
_DEV_HASH = login_mod.hash_password("Sastouka_1989")
TRIAL_DAYS = activation.TRIAL_DAYS
PLANS = [
    # L'option "essai" est supprimée d'ici. L'essai de 7 jours est géré
    # automatiquement à l'enregistrement d'un nouvel admin et via la page d'activation.
    ("1 mois",   "1 mois"),
    ("1 an",     "1 an"),
    ("illimité", "Illimité")
]

# KEY_DB will now be dynamic, within the admin's specific folder
# It needs to be initialized after utils.set_dynamic_base_dir is called
KEY_DB: Optional[Path] = None

def _set_dev_paths():
    """Sets the dynamic directory paths for developpeur blueprint."""
    global KEY_DB
    # Ensure utils.DYNAMIC_BASE_DIR is set by set_dynamic_base_dir
    if utils.DYNAMIC_BASE_DIR is None:
        print("ERROR: utils.DYNAMIC_BASE_DIR not set. Cannot initialize developer paths.")
        # Fallback or error handling if base dir is not set
        admin_email_from_session = session.get('admin_email', 'default_admin@example.com')
        utils.set_dynamic_base_dir(admin_email_from_session)

    KEY_DB = Path(utils.DYNAMIC_BASE_DIR) / "dev_keys.json"
    os.makedirs(KEY_DB.parent, exist_ok=True)
    print(f"DEBUG: Developer KEY_DB path set to: {KEY_DB}")


def _load_keys() -> dict:
    if KEY_DB is None:
        _set_dev_paths() # Attempt to set paths if not already set
        if KEY_DB is None: # If still None, something went wrong
            print("ERROR: KEY_DB is still not set after attempting _set_dev_paths. Cannot load keys.")
            return {}

    if KEY_DB.exists():
        return json.loads(KEY_DB.read_text(encoding="utf-8"))
    return {}

def _save_keys(d: dict):
    if KEY_DB is None:
        _set_dev_paths() # Attempt to set paths if not already set
        if KEY_DB is None: # If still None, something went wrong
            print("ERROR: KEY_DB is still not set after attempting _set_dev_paths. Cannot save keys.")
            return
            
    KEY_DB.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

developpeur_bp = Blueprint("developpeur_bp", __name__, url_prefix="/developpeur")

# ───────── 2. Templates ─────────
LOGIN_HTML = """
<!doctype html><html lang='fr'>
{{ pwa_head()|safe }}
<head><meta charset='utf-8'>
<title>Dev | Connexion</title>
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
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
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

<link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
<link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css' rel='stylesheet'>
<link href='https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css' rel='stylesheet'>
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>

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

  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-key section-icon'></i>Générer une clé machine</h5>
    <div class='card-body'>
      <form class='row gy-2 gx-3 align-items-end' method='POST'
            action='{{ url_for("developpeur_bp.gen_custom") }}'>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-desktop me-1'></i>ID machine</label>
          <input name='machine_id' class='form-control' placeholder='16 caractères' required>
        </div>
        <div class='col-12 col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-user me-1'></i>Nom</label>
          <input name='nom' class='form-control' required>
        </div>
        <div class='col-12 col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-user me-1'></i>Prénom</label>
          <input name='prenom' class='form-control' required>
        </div>
        <div class='col-12 col-md-2'>
          <label class='form-label fw-semibold'><i class='fas fa-file-signature me-1'></i>Plan</label>
          <select name='plan' class='form-select'>
            {% for c,l in plans %}<option value='{{c}}'>{{l}}</option>{% endfor %}
          </select>
        </div>
        <div class='col-12 col-md-2 d-grid'>
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

  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-server section-icon'></i>Clés machines</h5>
    <div class='card-body'>
      <div class="table-responsive">
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
  </div>

  <div class='card shadow-sm mb-4'>
    <h5 class='card-header'><i class='fas fa-user-plus section-icon'></i>Créer un compte admin</h5>
    <div class='card-body'>
      <form class='row gy-2 gx-3 align-items-end' method='POST'
            action='{{ url_for("developpeur_bp.create_admin") }}'>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-envelope me-1'></i>Email</label>
          <input name='email' type='email' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-key me-1'></i>Mot de passe</label>
          <input name='password' type='password' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-key me-1'></i>Confirmer</label>
          <input name='confirm' type='password' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-hospital me-1'></i>Clinique</label>
          <input name='clinic' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-calendar-alt me-1'></i>Date création</label>
          <input name='creation_date' type='date' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-map-marker-alt me-1'></i>Adresse</label>
          <input name='address' class='form-control' required>
        </div>
        <div class='col-12 col-md-4'>
          <label class='form-label fw-semibold'><i class='fas fa-phone me-1'></i>Téléphone</label>
          <input name='phone' type='tel' class='form-control' placeholder='Numéro de téléphone' required>
        </div>
        <input type='hidden' name='role' value='admin'>
        <div class='col-12 d-grid mt-2'>
          <button class='btn btn-grad'><i class='fas fa-user-plus me-1'></i>Créer</button>
        </div>
      </form>
    </div>
  </div>

  <div class='card shadow-sm'>
    <h5 class='card-header'><i class='fas fa-users section-icon'></i>Comptes admin</h5>
    <div class='card-body'>
      <div class="table-responsive">
        <table id='tblAdmin' class='table table-striped table-hover rounded overflow-hidden'>
          <thead><tr><th>Email</th><th>Clinique</th><th>Téléphone</th><th>Date création</th><th>Adresse</th><th>Actif</th><th>Actions</th></tr></thead>
          <tbody>
            {% for e,u in admins.items() %}
              <tr>
                <td>{{e}}</td><td>{{u.clinic}}</td><td>{{u.phone}}</td><td>{{u.creation_date}}</td><td>{{u.address}}</td>
                <td><span class='badge {{'bg-success' if u.active else 'bg-secondary'}}'>
                     {{'Oui' if u.active else 'Non'}}</span></td>
                <td class='text-nowrap'>
                  {% if u.phone %}
                  <a class='btn btn-sm btn-success me-1' title='Contacter via WhatsApp'
                     href='https://wa.me/{{ u.phone | replace("+", "") }}' target='_blank'>
                     <i class='fab fa-whatsapp'></i>
                  </a>
                  {% endif %}
                  <button class='btn btn-sm btn-info me-1 edit-admin-btn' title='Modifier'
                          data-bs-toggle='modal' data-bs-target='#editAdminModal'
                          data-email='{{ e }}'
                          data-clinic='{{ u.clinic }}'
                          data-creation_date='{{ u.creation_date }}'
                          data-address='{{ u.address }}'
                          data-phone='{{ u.phone }}'
                          data-active='{{ u.get('active', False) | tojson }}'>
                     <i class='fas fa-pen'></i>
                  </button>
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

</div>

<div class="modal fade" id="editAdminModal" tabindex="-1" aria-labelledby="editAdminModalLabel" aria-hidden="true">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="editAdminModalLabel">Modifier le compte Admin</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <form id="editAdminForm" method="POST" action="">
        <div class="modal-body">
          <input type="hidden" name="original_email" id="edit_original_email">
          <div class="mb-3">
            <label for="edit_email" class="form-label">Email</label>
            <input type="email" class="form-control" id="edit_email" name="email" required>
          </div>
          <div class="mb-3">
            <label for="edit_clinic" class="form-label">Nom de la clinique</label>
            <input type="text" class="form-control" id="edit_clinic" name="clinic" required>
          </div>
          <div class="mb-3">
            <label for="edit_creation_date" class="form-label">Date de création</label>
            <input type="date" class="form-control" id="edit_creation_date" name="creation_date" required>
          </div>
          <div class="mb-3">
            <label for="edit_address" class="form-label">Adresse</label>
            <input type="text" class="form-control" id="edit_address" name="address" required>
          </div>
          <div class="mb-3">
            <label for="edit_phone" class="form-label">Téléphone</label>
            <input type="tel" class="form-control" id="edit_phone" name="phone" placeholder='Numéro de téléphone' required>
          </div>
          <div class="mb-3">
            <label for="edit_password" class="form-label">Nouveau mot de passe (laisser vide si inchangé)</label>
            <input type="password" class="form-control" id="edit_password" name="password">
          </div>
          <div class="mb-3">
            <label for="edit_confirm_password" class="form-label">Confirmer le nouveau mot de passe</label>
            <input type="password" class="form-control" id="edit_confirm_password" name="confirm_password">
          </div>
          <div class="form-check">
            <input class="form-check-input" type="checkbox" id="edit_active" name="active">
            <label class="form-check-label" for="edit_active">
              Actif
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annuler</button>
          <button type="submit" class="btn btn-primary">Enregistrer les modifications</button>
        </div>
      </form>
    </div>
  </div>
</div>

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

    // Handle opening the edit modal
    $('#editAdminModal').on('show.bs.modal', function (event) {
      const button = $(event.relatedTarget); // Button that triggered the modal
      const email = button.data('email');
      const clinic = button.data('clinic');
      const creation_date = button.data('creation_date');
      const address = button.data('address');
      const phone = button.data('phone');
      const active = button.data('active');

      const modal = $(this);
      modal.find('#edit_original_email').val(email);
      modal.find('#edit_email').val(email);
      modal.find('#edit_clinic').val(clinic);
      modal.find('#edit_creation_date').val(creation_date);
      modal.find('#edit_address').val(address);
      modal.find('#edit_phone').val(phone);
      modal.find('#edit_active').prop('checked', active);

      // Set the form action dynamically
      modal.find('#editAdminForm').attr('action', '{{ url_for("developpeur_bp.edit_admin") }}');
    });

    // Handle form submission for editing admin
    $('#editAdminForm').on('submit', function(e) {
      e.preventDefault();
      const form = $(this);
      const formData = form.serialize();

      const newPassword = $('#edit_password').val();
      const confirmPassword = $('#edit_confirm_password').val();

      if (newPassword && newPassword !== confirmPassword) {
        Swal.fire({
          icon: 'error',
          title: 'Erreur',
          text: 'Les nouveaux mots de passe ne correspondent pas.'
        });
        return;
      }

      fetch(form.attr('action'), {
        method: 'POST',
        body: new URLSearchParams(formData),
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      })
      .then(response => response.json())
      .then(data => {
        if (data.status === 'success') {
          Swal.fire({
            icon: 'success',
            title: 'Succès',
            text: data.message
          }).then(() => {
            location.reload(); // Reload to reflect changes
          });
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Erreur',
            text: data.message
          });
        }
      })
      .catch(error => {
        console.error('Error:', error);
        Swal.fire({
          icon: 'error',
          title: 'Erreur réseau',
          text: 'Impossible de se connecter au serveur.'
        });
      });
    });
  });
</script>
</body>
</html>
"""

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
        "phone": f["phone"], # Ajout du champ téléphone
        "active": True
    }
    login_mod.save_users(users)
    flash("Admin créé", "success")
    return redirect(url_for(".dashboard"))

@developpeur_bp.route("/edit_admin", methods=["POST"])
def edit_admin():
    if (r := _dev_only()): return r
    f = request.form
    original_email = f["original_email"].lower()
    new_email = f["email"].lower()
    new_password = f.get("password")
    confirm_password = f.get("confirm_password")

    users = login_mod.load_users()

    if original_email not in users:
        return jsonify({"status": "error", "message": "Compte admin non trouvé."})

    user_data = users[original_email]

    # Check if email is being changed to an existing email (that isn't the original)
    if new_email != original_email and new_email in users:
        return jsonify({"status": "error", "message": "Le nouvel email existe déjà."})

    # Update password if provided
    if new_password:
        if new_password != confirm_password:
            return jsonify({"status": "error", "message": "Les mots de passe ne correspondent pas."})
        user_data["password"] = login_mod.hash_password(new_password)

    # Update other fields
    user_data["clinic"] = f["clinic"]
    user_data["creation_date"] = f["creation_date"]
    user_data["address"] = f["address"]
    user_data["phone"] = f["phone"]
    user_data["active"] = f.get("active") == "on"

    # If email changed, delete old entry and add new one
    if new_email != original_email:
        del users[original_email]
        users[new_email] = user_data
    else:
        users[new_email] = user_data # Ensure changes are saved to the correct key

    login_mod.save_users(users)
    return jsonify({"status": "success", "message": "Compte admin mis à jour."})


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