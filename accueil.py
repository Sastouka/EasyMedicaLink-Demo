# accueil.py
# ──────────────────────────────────────────────────────────────────────────────
# Page d’accueil – entièrement responsive (mobiles & tablettes)
#  • Icônes et libellés ne se chevauchent plus
#  • Ajout d’un pied-de-page signature + adresse IP locale
#  • ***NOUVEAU :*** icône « Statistique » (accessible Admin & Médecin, désactivée pour Assistante)
#  • Tout le code d’origine est conservé, seules les parties pertinentes sont
#    ajustées, sans perte de lignes non modifiées
# ──────────────────────────────────────────────────────────────────────────────

from flask import Blueprint, render_template_string, session, redirect, url_for
from datetime import datetime
import theme
import utils
from rdv import rdv_bp   # ← import inchangé

accueil_bp = Blueprint('accueil', __name__)

acceuil_template = """
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <title>{{ config.nom_clinique or config.cabinet or 'EasyMedicaLink' }}</title>

  <!-- Bootstrap & DataTables -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css">

  <!-- Google Fonts & FontAwesome -->
  <link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

  <!-- Tailwind pour bg-gradient-to-r, from-*, to-* -->
  <script src="https://cdn.tailwindcss.com"></script>

  <style>
    :root {
      {% for var, val in theme_vars.items() %}
      --{{ var }}: {{ val }};
      {% endfor %}
    }
    body { padding-top:56px; background:var(--bg-color); color:var(--text-color); }
    .navbar, .offcanvas-header { background:linear-gradient(45deg,var(--primary-color),var(--secondary-color))!important; }
    .offcanvas-body, .card, .card-body { background:var(--card-bg)!important; color:var(--text-color)!important; }
    .card-header { background:var(--primary-color)!important; color:var(--button-text)!important; }
    .card { border-radius:15px; box-shadow:0 4px 20px var(--card-shadow)!important; }
    .form-control { background:var(--card-bg)!important; color:var(--text-color)!important; border:1px solid var(--primary-color)!important; }
    .btn-medical { background:linear-gradient(45deg,var(--primary-color),var(--secondary-color))!important; color:var(--button-text)!important; border:none; }
    .btn-medical:hover { opacity:0.9; }

    /* Cartes d’icônes – flex-basis pour éviter le chevauchement */
    .icon-card      { flex:1 1 170px; max-width:180px; color:var(--primary-color); padding:0.5rem; }
    .icon-card i    { font-size:40px!important; }
    .icon-card span { font-size:28px!important; }
    .icon-card.disabled { opacity:0.5; pointer-events:none; }

    .header-item { font-size:28px!important; }

    /* Responsive ajusté */
    @media (max-width:575.98px){
      .icon-card      { flex:1 1 140px; max-width:160px; }
      .icon-card i    { font-size:32px!important; }
      .icon-card span { font-size:20px!important; }
    }
  </style>
</head>
<body>

  <!-- Barre de navigation -->
  <nav class="navbar navbar-dark fixed-top">
    <div class="container-fluid d-flex align-items-center">
      <button class="navbar-toggler" style="transform:scale(0.75);" type="button"
              data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
        <i class="fas fa-bars"></i>
      </button>
      <a class="navbar-brand ms-auto" href="{{ url_for('accueil.accueil') }}" style="font-family:'Great Vibes',cursive;font-size:2rem;">
        <i class="fas fa-heartbeat icon-pulse me-2"></i>EasyMedicaLink
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
      <!-- Boutons Modifier/Logout -->
      <div class="d-flex gap-2 mb-4">
        <a href="{{ url_for('login.change_password') }}" class="btn btn-outline-secondary flex-fill d-flex align-items-center justify-content-center">
          <i class="fas fa-key me-2"></i>Modifier passe
        </a>
        <a href="{{ url_for('login.logout') }}" class="btn btn-outline-secondary flex-fill d-flex align-items-center justify-content-center">
          <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
        </a>
      </div>

      <!-- Formulaire paramètres (inchangé) -->
      <form id="settingsForm" action="{{ url_for('settings') }}" method="POST">
        <div class="mb-3"><label class="form-label">Nom de la clinique</label><input type="text" class="form-control" name="nom_clinique" value="{{ config.nom_clinique or '' }}"></div>
        <div class="mb-3"><label class="form-label">Cabinet</label><input type="text" class="form-control" name="cabinet" value="{{ config.cabinet or '' }}"></div>
        <div class="mb-3"><label class="form-label">Centre médical</label><input type="text" class="form-control" name="centre_medecin" value="{{ config.centre_medical or '' }}"></div>
        <div class="mb-3"><label class="form-label">Nom du médecin</label><input type="text" class="form-control" name="nom_medecin" value="{{ config.doctor_name or '' }}"></div>
        <div class="mb-3"><label class="form-label">Lieu</label><input type="text" class="form-control" name="lieu" value="{{ config.location or '' }}"></div>
        <div class="mb-3"><label class="form-label">Thème</label>
          <select class="form-select" name="theme">
            {% for t in theme_names %}<option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>{% endfor %}
          </select>
        </div>
        <div class="mb-3"><label class="form-label">Image d’arrière-plan</label><input type="text" class="form-control" name="arriere_plan" value="{{ config.background_file_path or '' }}"></div>
        <div class="mb-3"><label class="form-label">Chemin de stockage</label><input type="text" class="form-control" name="storage_path" value="{{ config.storage_path or '' }}"></div>
        <div class="d-flex gap-2 mt-4">
          <button type="submit" class="btn btn-success flex-fill d-flex align-items-center justify-content-center">
            <i class="fas fa-save me-2"></i>Enregistrer
          </button>
        </div>
      </form>
    </div>
  </div>

  <!-- Carte identité -->
  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card shadow-lg">
          <div class="card-header py-3 text-center">
            <h1 class="mb-2 header-item"><i class="fas fa-hospital me-2"></i>{{ config.nom_clinique or config.cabinet or 'EasyMedicaLink' }}</h1>
            <div class="d-flex justify-content-center gap-4 flex-wrap">
              <div class="d-flex align-items-center header-item"><i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name }}</span></div>
              <div class="d-flex align-items-center header-item"><i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location }}</span></div>
            </div>
            <p class="mt-2 header-item"><i class="fas fa-calendar-day me-2"></i>{{ current_date }}</p>
          </div>

          <!-- Icônes centrales -->
          <div class="card-body d-flex flex-wrap gap-3 justify-content-center">
            <!-- RDV -->
            <a href="{{ url_for('rdv.rdv_home') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-calendar-check fa-3x mb-2"></i><span>RDV</span>
              </div>
            </a>

            <!-- Consultation -->
            {% if role in ['admin','medecin'] %}
            <a href="{{ url_for('index') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-stethoscope fa-3x mb-2"></i><span>Consultation</span>
              </div>
            </a>
            {% else %}
            <a class="icon-card disabled text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-stethoscope fa-3x mb-2"></i><span>Consultation</span>
              </div>
            </a>
            {% endif %}

            <!-- Facturation -->
            {% if role in ['admin','medecin','assistante'] %}
            <a href="{{ url_for('facturation.facturation_home') }}" class="text-decoration-none text-center icon-card">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-file-invoice-dollar fa-2x mb-2"></i><span>Facturation</span>
              </div>
            </a>
            {% else %}
            <a class="icon-card disabled text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-file-invoice-dollar fa-3x mb-2"></i><span>Facturation</span>
              </div>
            </a>
            {% endif %}

            <!-- Statistique -->
            {% if role in ['admin','medecin'] %}
              <a href="{{ url_for('statistique.stats_home') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie fa-3x mb-2"></i><span>Statistique</span>
                </div>
              </a>
            {% elif role == 'assistante' %}
              <a class="icon-card disabled text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie fa-3x mb-2"></i><span>Statistique</span>
                </div>
              </a>
            {% endif %}

            <!-- Admin -->
            {% if role == 'admin' %}
            <a href="{{ url_for('administrateur_bp.dashboard') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-user-shield fa-3x mb-2"></i><span>Admin</span>
              </div>
            </a>
            {% endif %}
          </div>
        </div>
      </div>
    </div>
  </div>

  <footer class="text-center py-3 small">
    <p class="text-muted small mb-1">
      <i class="fas fa-heartbeat text-danger me-1"></i>
      SASTOUKA DIGITAL © 2025 • sastoukadigital@gmail.com tel +212652084735
    </p>
    <p class="mb-0">
      Accès réseau : <span class="fw-semibold">{{ host_address }}</span>
    </p>
  </footer>

  <!-- Scripts -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <script>
    // Soumission AJAX paramètres
    document.getElementById('settingsForm').addEventListener('submit', e=>{
      e.preventDefault();
      fetch(e.target.action,{method:e.target.method,body:new FormData(e.target),credentials:'same-origin'})
        .then(r=>{ if(!r.ok) throw new Error('Échec réseau'); return r; })
        .then(()=>Swal.fire({icon:'success',title:'Enregistré',text:'Paramètres sauvegardés.'}).then(()=>location.reload()))
        .catch(err=>Swal.fire({icon:'error',title:'Erreur',text:err.message}));
    });
  </script>
</body>
</html>
"""

@accueil_bp.route('/accueil')
def accueil():
    if 'email' not in session:
        return redirect(url_for('login.login'))
    config           = utils.load_config()
    session['theme'] = config.get('theme', theme.DEFAULT_THEME)
    current_date     = datetime.now().strftime("%Y-%m-%d")
    role             = session.get('role')
    host_address     = f"http://{utils.LOCAL_IP}:3000"
    return render_template_string(
        acceuil_template,
        config=config,
        current_date=current_date,
        role=role,
        host_address=host_address,
        theme_vars=theme.current_theme(),
        theme_names=list(theme.THEMES.keys())
    )
