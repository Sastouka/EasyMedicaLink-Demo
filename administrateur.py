# administrateur.py
# ──────────────────────────────────────────────────────────────────────────────
#  Version mise à jour :
#    • _current_plan() lit désormais le plan dans users.json (bloc 'activation').
#    • Plus aucune référence à utils.ACTIVATION_FILE.
#    • Boutons de téléchargement toujours affichés en bas.
#    • Aucune autre ligne d’origine perdue ; filtres propriétaire + rôles inchangés.
# ──────────────────────────────────────────────────────────────────────────────

from flask import Blueprint, render_template_string, request, redirect, url_for, flash, session, abort
from datetime import datetime
import json
from pathlib import Path
import theme
import utils
import login

# Récupération de TRIAL_DAYS pour l’affichage
try:
    from activation import TRIAL_DAYS
except ImportError:
    TRIAL_DAYS = 7

administrateur_bp = Blueprint('administrateur_bp', __name__, url_prefix='/administrateur')

# ──────────────────────────────────────────────────────────────────────────────
# Helper plan
# ──────────────────────────────────────────────────────────────────────────────
def _current_plan() -> str:
    """
    Renvoie le plan de licence de l’administrateur connecté (lecture users.json).
    """
    mapping = {
        f"essai_{TRIAL_DAYS}jours": f"Essai ({TRIAL_DAYS} jours)",
        "1 an":     "1 an",
        "illimité": "Illimité",
    }
    user = login.load_users().get(session.get("email"))
    plan_raw = (
        user.get("activation", {}).get("plan", "").lower()
        if user else ""
    )
    return mapping.get(plan_raw, plan_raw.capitalize() or "Inconnu")

# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATE HTML
# ──────────────────────────────────────────────────────────────────────────────
administrateur_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>Administration - {{ config.nom_clinique or 'EasyMedicaLink' }}</title>

  <!-- Bootstrap & DataTables -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css" rel="stylesheet">
  <link href="https://cdn.datatables.net/responsive/2.4.1/css/responsive.bootstrap5.min.css" rel="stylesheet">

  <!-- Google Fonts & FontAwesome -->
  <link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script src="https://cdn.tailwindcss.com"></script>

  <style>
    :root { {% for var,val in theme_vars.items() %}--{{ var }}:{{ val }};{% endfor %} }
    body { padding-top:56px; background:var(--bg-color); color:var(--text-color); }
    .navbar, .offcanvas-header { background:linear-gradient(45deg,var(--primary-color),var(--secondary-color)) !important; }
    .offcanvas-body, .card, .form-control, .table { background:var(--card-bg) !important; color:var(--text-color) !important; }
    .card-header { background:var(--primary-color) !important; color:var(--button-text) !important; }
    .btn-medical { background:linear-gradient(45deg,var(--primary-color),var(--secondary-color)) !important; color:var(--button-text) !important; border:none; }
    .header-item { font-size:28px !important; }
    .icon-card { flex:1 1 170px; max-width:180px; color:var(--primary-color); padding:.5rem; }
    .icon-card i { font-size:40px !important; }
    .icon-card span { font-size:28px !important; }
    @media(max-width:575.98px) {
      .icon-card { flex:1 1 140px; max-width:160px; }
      .icon-card i { font-size:32px !important; }
      .icon-card span { font-size:20px !important; }
    }
  </style>
</head>
<body>
  <!-- Navbar -->
  <nav class="navbar navbar-dark fixed-top">
    <div class="container-fluid d-flex align-items-center">
      <button class="navbar-toggler" type="button" data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
        <i class="fas fa-bars"></i>
      </button>
      <a class="navbar-brand ms-auto d-flex align-items-center"
         href="{{ url_for('accueil.accueil') }}"
         style="font-family:'Great Vibes',cursive;font-size:2rem;color:white;">
        <i class="fas fa-home me-2" style="transform:translateX(-0.5cm);"></i>
        <i class="fas fa-heartbeat me-2"></i>EasyMedicaLink
      </a>
    </div>
  </nav>

  <!-- Offcanvas Paramètres -->
  <div class="offcanvas offcanvas-start" tabindex="-1" id="settingsOffcanvas">
    <div class="offcanvas-header text-white">
      <h5 class="offcanvas-title"><i class="fas fa-cog me-2"></i>Paramètres</h5>
      <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas"></button>
    </div>
    <div class="offcanvas-body">
      <!-- Boutons actions -->
      <div class="d-flex flex-column gap-3 mb-4">
        <a href="{{ url_for('login.change_password') }}"
          data-bs-dismiss="offcanvas"
          onclick="window.location.href='{{ url_for('login.change_password') }}'; return false;"
          class="btn-medical rounded-2xl shadow-lg d-flex align-items-center justify-content-center py-2">
          <i class="fas fa-key me-2"></i>Modifier mot de passe
        </a>
        <a href="{{ url_for('login.logout') }}"
          data-bs-dismiss="offcanvas"
          onclick="window.location.href='{{ url_for('login.logout') }}'; return false;"
          class="btn-medical rounded-2xl shadow-lg d-flex align-items-center justify-content-center py-2">
          <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
        </a>
        <a href="{{ url_for('activation', bypass=1) }}"
          data-bs-dismiss="offcanvas"
          onclick="window.location.href='{{ url_for('activation', bypass=1) }}'; return false;"
          class="btn-medical rounded-2xl shadow-lg d-flex align-items-center justify-content-center py-2">
          <i class="fas fa-bolt me-2"></i>Changer de plan
        </a>
      </div>

      <!-- Formulaire de paramétrage -->
      <form id="adminSettingsForm" action="{{ url_for('settings') }}" method="POST">
        <div class="mb-3">
          <label class="form-label fw-semibold">Nom de la clinique</label>
          <input type="text" name="nom_clinique" value="{{ config.nom_clinique or '' }}" class="form-control" required>
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Cabinet</label>
          <input type="text" name="cabinet" value="{{ config.cabinet or '' }}" class="form-control">
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Centre médical</label>
          <input type="text" name="centre_medical" value="{{ config.centre_medical or '' }}" class="form-control">
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Nom du médecin</label>
          <input type="text" name="nom_medecin" value="{{ config.doctor_name or '' }}" class="form-control">
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Lieu</label>
          <input type="text" name="lieu" value="{{ config.location or '' }}" class="form-control">
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Thème</label>
          <select id="adminThemeSelect" name="theme" class="form-select">
            {% for t in theme_names %}
              <option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label fw-semibold">Arrière-plan</label>
          <select name="arriere_plan" class="form-select">
            {% for bg in backgrounds %}
              <option value="{{ bg }}" {% if config.background_file_path.endswith(bg) %}selected{% endif %}>{{ bg }}</option>
            {% endfor %}
          </select>
        </div>

      <form id="adminSettingsForm" action="{{ url_for('settings') }}" method="POST">
        <input type="hidden" name="theme" id="hiddenTheme">
        <button class="btn btn-medical rounded-2xl shadow-lg w-100 py-2" type="submit">
          <i class="fas fa-save me-2"></i>Enregistrer les modifications
        </button>
      </form>
    </div>
  </div>

  <script>
    const themeSel=document.getElementById('adminThemeSelect'),hTheme=document.getElementById('hiddenTheme');
    hTheme.value=themeSel.value;
    themeSel.addEventListener('change',()=>hTheme.value=themeSel.value);
    document.getElementById('adminSettingsForm').addEventListener('submit',e=>{
      e.preventDefault();
      fetch(e.target.action,{method:'POST',body:new FormData(e.target),credentials:'same-origin'})
        .then(r=>{if(!r.ok)throw new Error();return r;}).then(()=>location.reload())
        .catch(()=>alert("Impossible d'enregistrer"));
    });
  </script>

  <!-- Carte identité + Infos licence -->
  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card shadow-lg">
          <div class="card-header py-3 text-center">
            <h1 class="mb-2 header-item"><i class="fas fa-hospital me-2"></i>{{ config.nom_clinique or 'EasyMedicaLink' }}</h1>
            <div class="d-flex justify-content-center gap-4 flex-wrap">
              <div class="d-flex align-items-center header-item"><i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name or '' }}</span></div>
              <div class="d-flex align-items-center header-item"><i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location or '' }}</span></div>
            </div>
            <p class="mt-2 header-item"><i class="fas fa-calendar-day me-2"></i>{{ current_date }}</p>
          </div>

          <div class="card-body">
            <div class="mb-3 text-center">
              <h6 class="fw-bold"><i class="fas fa-id-badge me-2"></i>Informations de licence</h6>
              <p class="mb-1"><strong>Plan :</strong> {{ plan }}</p>
              <p class="mb-4"><strong>Administrateur :</strong> {{ admin_email }}</p>
            </div>

            <div class="d-flex justify-content-around flex-wrap gap-3">
              <a href="{{ url_for('rdv.rdv_home') }}" class="text-decoration-none text-center icon-card">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-calendar-alt fa-2x mb-2"></i><span>RDV</span>
                </div>
              </a>
              <a href="{{ url_for('index') }}" class="text-decoration-none text-center icon-card">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-stethoscope fa-2x mb-2"></i><span>Consultation</span>
                </div>
              </a>
              <a href="{{ url_for('facturation.facturation_home') }}" class="text-decoration-none text-center icon-card">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-file-invoice-dollar fa-2x mb-2"></i><span>Facturation</span>
                </div>
              </a>
              <a href="{{ url_for('statistique.stats_home') }}" class="text-decoration-none text-center icon-card">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie fa-2x mb-2"></i><span>Statistique</span>
                </div>
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Gestion des comptes -->
  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card">
          <div class="card-header text-center"><h2 class="header-item">Administration des comptes</h2></div>
          <div class="card-body">
            <form class="row g-3 mb-4" method="POST" action="{{ url_for('administrateur_bp.create_user') }}">
              <div class="col-12 col-md-2"><input name="nom" class="form-control" placeholder="Nom" required></div>
              <div class="col-12 col-md-2"><input name="prenom" class="form-control" placeholder="Prénom" required></div>
              <div class="col-12 col-md-2">
                <select name="role" class="form-select" required>
                  <option value="medecin">Médecin</option>
                  <option value="assistante">Assistante</option>
                </select>
              </div>
              <div class="col-12 col-md-2"><input name="password" type="password" class="form-control" placeholder="Mot de passe" required></div>
              <div class="col-12 col-md-2"><button class="btn btn-medical w-100" type="submit"><i class="fas fa-user-plus me-1"></i>Créer</button></div>
            </form>

            <div class="table-responsive">
              <table id="usersTable" class="table table-striped table-hover nowrap" style="width:100%">
                <thead><tr><th>Nom</th><th>Prénom</th><th>Email</th><th>Rôle</th><th>Actif</th><th>Actions</th></tr></thead>
                <tbody>
                  {% for email, info in users.items() %}
                  <tr>
                    <td>{{ info.nom }}</td>
                    <td>{{ info.prenom }}</td>
                    <td>{{ email }}</td>
                    <td>{{ info.role }}</td>
                    <td>{{ 'Oui' if info.active else 'Non' }}</td>
                    <td>
                      <a href="#" class="btn btn-outline-primary btn-sm me-1 editBtn" data-email="{{ email }}"><i class="fas fa-edit"></i></a>
                      <a href="{{ url_for('administrateur_bp.toggle_active', user_email=email) }}" class="btn btn-outline-secondary btn-sm me-1">
                        {% if info.active %}<i class="fas fa-user-slash"></i>{% else %}<i class="fas fa-user-check"></i>{% endif %}
                      </a>
                      <a href="{{ url_for('administrateur_bp.delete_user', user_email=email) }}" class="btn btn-outline-danger btn-sm"><i class="fas fa-trash"></i></a>
                    </td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="container-fluid my-4">
    <div class="d-flex justify-content-center gap-3">
      {% if win64_filename %}
      <a href="{{ url_for('static', filename=win64_filename) }}" class="btn btn-medical">
        Télécharger EasyMedicalLink Win64
      </a>
      {% endif %}
      {% if win32_filename %}
      <a href="{{ url_for('static', filename=win32_filename) }}" class="btn btn-medical">
        Télécharger EasyMedicalLink Win32
      </a>
      {% endif %}
    </div>
  </div>

  <!-- Modal + JS -->
  <div class="modal fade" id="editModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <form id="editForm" method="POST" class="modal-content" action="{{ url_for('administrateur_bp.edit_user') }}">
        <div class="modal-header"><h5 class="modal-title">Modifier l'utilisateur</h5><button class="btn-close" type="button" data-bs-dismiss="modal"></button></div>
        <div class="modal-body">
          <input type="hidden" name="email" id="editEmail">
          <div class="mb-3"><label class="form-label">Adresse email</label><input id="newEmail" name="new_email" type="email" class="form-control" required></div>
          <div class="mb-3"><label class="form-label">Nouveau mot de passe</label><input id="newPassword" name="new_password" type="password" class="form-control" placeholder="Laisser vide pour ne pas changer"></div>
          <div class="mb-3"><input id="editNom" name="nom" class="form-control" placeholder="Nom" required></div>
          <div class="mb-3"><input id="editPrenom" name="prenom" class="form-control" placeholder="Prénom" required></div>
          <div class="mb-3">
            <select id="editRole" name="role" class="form-select" required>
              <option value="medecin">Médecin</option><option value="assistante">Assistante</option>
            </select>
          </div>
        </div>
        <div class="modal-footer"><button class="btn btn-medical" type="submit">Enregistrer</button></div>
      </form>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/jquery.dataTables.min.js"></script>
  <script src="https://cdn.datatables.net/1.13.1/js/dataTables.bootstrap5.min.js"></script>
  <script src="https://cdn.datatables.net/responsive/2.4.1/js/dataTables.responsive.min.js"></script>
  <script src="https://cdn.datatables.net/responsive/2.4.1/js/responsive.bootstrap5.min.js"></script>
  <script>
    document.addEventListener('DOMContentLoaded',()=>{
      new DataTable('#usersTable',{
        responsive:true,
        lengthChange:false,
        language:{url:"//cdn.datatables.net/plug-ins/1.13.1/i18n/fr-FR.json"}
      });
    });
    document.querySelectorAll('.editBtn').forEach(btn=>{
      btn.addEventListener('click',e=>{
        e.preventDefault();
        const email=btn.dataset.email;
        fetch(`/administrateur/get_user/${email}`).then(r=>r.json()).then(u=>{
          document.getElementById('editEmail').value=email;
          document.getElementById('newEmail').value=email;
          document.getElementById('editNom').value=u.nom;
          document.getElementById('editPrenom').value=u.prenom;
          document.getElementById('editRole').value=u.role;
          new bootstrap.Modal(document.getElementById('editModal')).show();
        });
      });
    });
    document.getElementById('editForm').addEventListener('submit',e=>{
      e.preventDefault();
      fetch(e.target.action,{method:'POST',body:new FormData(e.target),credentials:'same-origin'}).then(()=>location.reload());
    });
  </script>
</body>
</html>
"""
@administrateur_bp.route('/', methods=['GET'])
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login.login'))

    # Debugging : afficher le chemin du dossier static et son contenu
    import os
    from flask import current_app
    static_folder = current_app.static_folder
    print("Static folder =", static_folder)
    try:
        contents = os.listdir(static_folder)
        print("Contenu de static/ =", contents)
    except Exception as e:
        print("Erreur lors de la lecture du dossier static :", e)

    # Détection robuste des exécutables, même si Windows a ajouté « .exe.exe »
    win64_filename = next(
        (f for f in contents if f.startswith('EasyMedicaLink-Win64.exe')),
        None
    )
    win32_filename = next(
        (f for f in contents if f.startswith('EasyMedicaLink-Win32.exe')),
        None
    )

    admin_email  = session['email']
    full_users   = login.load_users()
    users        = {
        e: u for e, u in full_users.items()
        if u.get('role') in ('medecin', 'assistante') and u.get('owner') == admin_email
    }
    config       = utils.load_config()
    current_date = datetime.now().strftime("%Y-%m-%d")

    return render_template_string(
        administrateur_template,
        users=users,
        config=config,
        current_date=current_date,
        theme_vars=theme.current_theme(),
        theme_names=list(theme.THEMES.keys()),
        plan=_current_plan(),
        admin_email=admin_email,
        win64_filename=win64_filename,
        win32_filename=win32_filename
    )

@administrateur_bp.route('/get_user/<user_email>')
def get_user(user_email):
    u = login.load_users().get(user_email)
    if not u:
        return {}, 404
    return {'nom': u['nom'], 'prenom': u['prenom'], 'role': u['role']}

@administrateur_bp.route('/create_user', methods=['POST'])
def create_user():
    if 'email' not in session:
        return redirect(url_for('login.login'))
    admin_email = session['email']
    data        = request.form
    users       = login.load_users()
    key         = f"{data['prenom'].lower()}.{data['nom'].lower()}@easymedicalink.com"
    if key in users:
        flash("Utilisateur existe déjà.", "warning")
    else:
        users[key] = {
            'nom':      data['nom'],
            'prenom':   data['prenom'],
            'role':     data['role'],
            'password': login.hash_password(data['password']),
            'active':   True,
            'owner':    admin_email
        }
        login.save_users(users)
        flash("Compte créé !", "success")
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/edit_user', methods=['POST'])
def edit_user():
    data      = request.form
    old_email = data['email']
    new_email = data.get('new_email', old_email).strip().lower()
    users     = login.load_users()
    if old_email not in users or users[old_email].get('owner') != session.get('email'):
        flash("Action non autorisée.", "error")
        return redirect(url_for('administrateur_bp.dashboard'))
    user = users.pop(old_email)
    user.update({'nom': data['nom'], 'prenom': data['prenom'], 'role': data['role']})
    new_pwd = data.get('new_password', '').strip()
    if new_pwd:
        user['password'] = login.hash_password(new_pwd)
    users[new_email] = user
    login.save_users(users)
    flash("Données mises à jour.", "success")
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/toggle_active/<user_email>')
def toggle_active(user_email):
    users = login.load_users()
    if user_email in users and users[user_email].get('owner') == session.get('email'):
        users[user_email]['active'] = not users[user_email]['active']
        login.save_users(users)
    return redirect(url_for('administrateur_bp.dashboard'))

@administrateur_bp.route('/delete_user/<user_email>')
def delete_user(user_email):
    users = login.load_users()
    if user_email in users and users[user_email].get('owner') == session.get('email'):
        users.pop(user_email)
        login.save_users(users)
    return redirect(url_for('administrateur_bp.dashboard'))
