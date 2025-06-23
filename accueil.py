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

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.datatables.net/1.13.1/css/dataTables.bootstrap5.min.css">

  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&family=Great+Vibes&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>

  <style>
    :root {
      {% for var, val in theme_vars.items() %}
      --{{ var }}: {{ val }};
      {% endfor %}
      --font-primary: 'Poppins', sans-serif;
      --font-secondary: 'Great Vibes', cursive;
      --gradient-main: linear-gradient(45deg, var(--primary-color) 0%, var(--secondary-color) 100%);
      --shadow-light: 0 5px 15px rgba(0, 0, 0, 0.1);
      --shadow-medium: 0 8px 25px rgba(0, 0, 0, 0.2);
      --border-radius-lg: 1rem;
      --border-radius-md: 0.75rem;
      --border-radius-sm: 0.5rem;
    }

    body {
      font-family: var(--font-primary);
      background: var(--bg-color);
      color: var(--text-color);
      padding-top: 56px;
      transition: background 0.3s ease, color 0.3s ease;
    }

    .navbar {
      background: var(--gradient-main) !important;
      box-shadow: var(--shadow-medium);
    }
    .navbar-brand {
      font-family: var(--font-secondary);
      font-size: 2.0rem !important;
      color: white !important;
      display: flex;
      align-items: center;
      transition: transform 0.3s ease;
    }
    .navbar-brand:hover {
      transform: scale(1.05);
    }
    .navbar-toggler {
      border: none;
      outline: none;
    }
    .navbar-toggler i {
      color: white;
      font-size: 1.5rem;
    }

    .offcanvas-header {
      background: var(--gradient-main) !important;
      color: white;
    }
    .offcanvas-body {
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
    }
    .offcanvas-title {
      font-weight: 600;
    }

    .card {
      border-radius: var(--border-radius-lg);
      box-shadow: var(--shadow-light);
      background: var(--card-bg) !important;
      color: var(--text-color) !important;
      border: none;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .card:hover {
      box-shadow: var(--shadow-medium);
    }

    .card-header {
      background: var(--primary-color) !important;
      color: var(--button-text) !important;
      border-top-left-radius: var(--border-radius-lg);
      border-top-right-radius: var(--border-radius-lg);
      padding: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .card-header::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(255, 255, 255, 0.1);
      transform: skewY(-5deg);
      transform-origin: top left;
      z-index: 0;
    }
    .card-header h1, .card-header .header-item, .card-header p {
      position: relative;
      z-index: 1;
      font-size: 1.8rem !important;
      font-weight: 700;
    }
    .card-header i {
      font-size: 1.8rem !important;
      margin-right: 0.5rem;
    }
    .header-item {
      font-size: 1.2rem !important;
      font-weight: 400;
    }

    /* Floating Labels (for consistency, even if not used on this page) */
    .floating-label {
      position: relative;
      margin-bottom: 1rem;
    }
    .floating-label input,
    .floating-label select {
      padding: 1rem 0.75rem 0.5rem;
      height: auto;
      border-radius: var(--border-radius-sm);
      border: 1px solid var(--secondary-color);
      background-color: var(--card-bg);
      color: var(--text-color);
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .floating-label input:focus,
    .floating-label select:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 0.25rem rgba(var(--primary-color-rgb), 0.25);
      background-color: var(--card-bg);
      color: var(--text-color);
    }
    .floating-label label {
      position: absolute;
      top: 0.75rem;
      left: 0.75rem;
      font-size: 1rem;
      color: var(--text-color-light);
      transition: all 0.2s ease;
      pointer-events: none;
    }
    .floating-label input:focus + label,
    .floating-label input:not(:placeholder-shown) + label,
    .floating-label select:focus + label,
    .floating-label select:not([value=""]) + label {
      top: 0.25rem;
      left: 0.75rem;
      font-size: 0.75rem;
      color: var(--primary-color);
      background-color: var(--card-bg);
      padding: 0 0.25rem;
      transform: translateX(-0.25rem);
    }
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-text,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-month-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-day-field,
    .floating-label input[type="date"]:not([value=""])::-webkit-datetime-edit-year-field {
      color: var(--text-color);
    }
    .floating-label input[type="date"]::-webkit-calendar-picker-indicator {
      filter: {% if session.theme == 'dark' %}invert(1){% else %}none{% endif %};
    }

    /* Buttons */
    .btn {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      transition: all 0.3s ease;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.75rem 1.25rem;
    }
    .btn i {
      margin-right: 0.5rem;
    }
    .btn-primary {
      background: var(--gradient-main);
      border: none;
      color: var(--button-text);
      box-shadow: var(--shadow-light);
    }
    .btn-primary:hover {
      box-shadow: var(--shadow-medium);
      background: var(--gradient-main);
      opacity: 0.9;
    }
    .btn-success {
      background-color: var(--success-color);
      border-color: var(--success-color);
      color: white;
    }
    .btn-success:hover {
      background-color: var(--success-color-dark);
      border-color: var(--success-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-warning {
      background-color: var(--warning-color);
      border-color: var(--warning-color);
      color: white;
    }
    .btn-warning:hover {
      background-color: var(--warning-color-dark);
      border-color: var(--warning-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-danger {
      background-color: var(--danger-color);
      border-color: var(--danger-color);
      color: white;
    }
    .btn-danger:hover {
      background-color: var(--danger-color-dark);
      border-color: var(--danger-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-info { /* WhatsApp button */
      background-color: #25D366;
      border-color: #25D366;
      color: white;
    }
    .btn-info:hover {
      background-color: #1DA851;
      border-color: #1DA851;
      box-shadow: var(--shadow-medium);
    }
    .btn-outline-secondary {
      border-color: var(--secondary-color);
      color: var(--text-color);
      background-color: transparent;
    }
    .btn-outline-secondary:hover {
      background-color: var(--secondary-color);
      color: white;
      box-shadow: var(--shadow-light);
    }
    .btn-secondary {
      background-color: var(--secondary-color);
      border-color: var(--secondary-color);
      color: var(--button-text);
    }
    .btn-secondary:hover {
      background-color: var(--secondary-color-dark);
      border-color: var(--secondary-color-dark);
      box-shadow: var(--shadow-medium);
    }
    .btn-sm {
      padding: 0.5rem 0.8rem;
      font-size: 0.875rem;
    }

    /* Icon Cards */
    .icon-card {
      flex: 1 1 170px; /* Adjusted flex-basis for better responsiveness */
      max-width: 180px;
      color: var(--primary-color);
      padding: 0.5rem;
      text-decoration: none; /* Ensure links don't have underlines */
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .icon-card:hover {
      transform: translateY(-5px); /* Keep a subtle lift for icon cards */
      box-shadow: var(--shadow-medium);
    }
    .icon-card i {
      font-size: 40px !important;
      margin-bottom: 0.5rem; /* Added margin for spacing */
    }
    .icon-card span {
      font-size: 1.1rem !important; /* Adjusted font size for better readability */
      font-weight: 600; /* Make text bolder */
      color: var(--text-color); /* Ensure text color is consistent */
    }
    .icon-card .border {
      border-radius: var(--border-radius-lg); /* Match card border-radius */
      border: 1px solid var(--border-color) !important; /* Use theme border color */
      background-color: var(--card-bg); /* Ensure background is card-bg */
      box-shadow: var(--shadow-light); /* Add shadow to inner div */
      transition: all 0.2s ease;
    }
    .icon-card:hover .border {
      border-color: var(--primary-color) !important; /* Highlight border on hover */
    }
    .icon-card.disabled {
      opacity: 0.5;
      pointer-events: none;
    }

    .header-item {
      font-size: 1.2rem !important; /* Adjusted to match rdv_template */
      font-weight: 400;
    }
    .header-item h1 {
      font-size: 1.8rem !important; /* Adjusted to match rdv_template */
      font-weight: 700;
    }
    .header-item i {
      font-size: 1.8rem !important; /* Adjusted to match rdv_template */
      margin-right: 0.5rem;
    }

    /* Flash messages */
    .alert {
      border-radius: var(--border-radius-md);
      font-weight: 600;
      position: fixed;
      top: 70px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1060;
      width: 90%;
      max-width: 500px;
      box-shadow: var(--shadow-medium);
      animation: fadeInOut 5s forwards;
    }

    @keyframes fadeInOut {
      0% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
      10% { opacity: 1; transform: translateX(-50%) translateY(0); }
      90% { opacity: 1; transform: translateX(-50%) translateY(0); }
      100% { opacity: 0; transform: translateX(-50%) translateY(-20px); }
    }

    /* Footer */
    footer {
      background: var(--gradient-main);
      color: white;
      font-weight: 300;
      box-shadow: 0 -5px 15px rgba(0, 0, 0, 0.1);
    }
    footer a {
      color: white;
      text-decoration: none;
      transition: color 0.2s ease;
    }
    footer a:hover {
      color: var(--text-color-light);
    }

    /* Responsive adjustments */
    @media (max-width: 768px) {
      .card-header h1 {
        font-size: 1.5rem !important;
      }
      .card-header .header-item {
        font-size: 1rem !important;
      }
      .card-header i {
        font-size: 1.5rem !important;
      }
      .icon-card {
        flex: 1 1 140px;
        max-width: 160px;
      }
      .icon-card i {
        font-size: 32px !important;
      }
      .icon-card span {
        font-size: 20px !important;
      }
      .btn {
        width: 100%;
        margin-bottom: 0.5rem;
      }
      .d-flex.gap-2 {
        flex-direction: column;
      }
    }
  </style>
</head>
<body>

  <nav class="navbar navbar-dark fixed-top">
    <div class="container-fluid d-flex align-items-center">
      <button class="navbar-toggler" type="button"
              data-bs-toggle="offcanvas" data-bs-target="#settingsOffcanvas">
        <i class="fas fa-bars"></i>
      </button>
      <a class="navbar-brand ms-auto d-flex align-items-center" href="{{ url_for('accueil.accueil') }}">
        <i class="fas fa-heartbeat me-2"></i>EasyMedicaLink
      </a>
    </div>
  </nav>

  <div class="offcanvas offcanvas-start" tabindex="-1" id="settingsOffcanvas">
    <div class="offcanvas-header text-white">
      <h5 class="offcanvas-title"><i class="fas fa-cog me-2"></i>Paramètres</h5>
      <button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas"></button>
    </div>
    <div class="offcanvas-body">
      <div class="d-flex gap-2 mb-4">
        <a href="{{ url_for('login.change_password') }}" class="btn btn-outline-secondary flex-fill">
          <i class="fas fa-key me-2"></i>Modifier passe
        </a>
        <a href="{{ url_for('login.logout') }}" class="btn btn-outline-secondary flex-fill">
          <i class="fas fa-sign-out-alt me-2"></i>Déconnexion
        </a>
      </div>

      <form id="settingsForm" action="{{ url_for('settings') }}" method="POST">
        <div class="mb-3 floating-label">
          <input type="text" class="form-control" name="nom_clinique" id="nom_clinique" value="{{ config.nom_clinique or '' }}" placeholder=" ">
          <label for="nom_clinique">Nom de la clinique</label>
        </div>
        <div class="mb-3 floating-label">
          <input type="text" class="form-control" name="cabinet" id="cabinet" value="{{ config.cabinet or '' }}" placeholder=" ">
          <label for="cabinet">Cabinet</label>
        </div>
        <div class="mb-3 floating-label">
          <input type="text" class="form-control" name="centre_medecin" id="centre_medecin" value="{{ config.centre_medical or '' }}" placeholder=" ">
          <label for="centre_medecin">Centre médical</label>
        </div>
        <div class="mb-3 floating-label">
          <input type="text" class="form-control" name="nom_medecin" id="nom_medecin" value="{{ config.doctor_name or '' }}" placeholder=" ">
          <label for="nom_medecin">Nom du médecin</label>
        </div>
        <div class="mb-3 floating-label">
          <input type="text" class="form-control" name="lieu" id="lieu" value="{{ config.location or '' }}" placeholder=" ">
          <label for="lieu">Lieu</label>
        </div>
        <div class="mb-3 floating-label">
          <select class="form-select" name="theme" id="theme_select" placeholder=" ">
            {% for t in theme_names %}<option value="{{ t }}" {% if config.theme == t %}selected{% endif %}>{{ t.capitalize() }}</option>{% endfor %}
          </select>
          <label for="theme_select">Thème</label>
        </div>
        <div class="d-flex gap-2 mt-4">
          <button type="submit" class="btn btn-success flex-fill">
            <i class="fas fa-save me-2"></i>Enregistrer
          </button>
        </div>
      </form>
    </div>
  </div>

  <div class="container-fluid my-4">
    <div class="row justify-content-center">
      <div class="col-12">
        <div class="card shadow-lg">
          <div class="card-header py-3 text-center">
            <h1 class="mb-2 header-item"><i class="fas fa-hospital me-2"></i>{{ config.nom_clinique or config.cabinet or 'NOM CLINIQUE/CABINET' }}</h1>
            <div class="d-flex justify-content-center gap-4 flex-wrap">
              <div class="d-flex align-items-center header-item"><i class="fas fa-user-md me-2"></i><span>{{ config.doctor_name or 'NOM MEDECIN' }}</span></div>
              <div class="d-flex align-items-center header-item"><i class="fas fa-map-marker-alt me-2"></i><span>{{ config.location or 'LIEU' }}</span></div>
            </div>
            <p class="mt-2 header-item"><i class="fas fa-calendar-day me-2"></i>{{ current_date }}</p>
          </div>

          <div class="card-body d-flex flex-wrap gap-3 justify-content-center">
            <a href="{{ url_for('rdv.rdv_home') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-calendar-check mb-2"></i><span>RDV</span>
              </div>
            </a>

            {% if role in ['admin','medecin'] %}
            <a href="{{ url_for('index') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-stethoscope mb-2"></i><span>Consultations</span>
              </div>
            </a>
            {% else %}
            <a class="icon-card disabled text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-stethoscope mb-2"></i><span>Consultations</span>
              </div>
            </a>
            {% endif %}

            {% if role in ['admin','medecin','assistante'] %}
            <a href="{{ url_for('facturation.facturation_home') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-file-invoice-dollar mb-2"></i><span>Factures</span>
              </div>
            </a>
            {% else %}
            <a class="icon-card disabled text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-file-invoice-dollar mb-2"></i><span>Factures</span>
              </div>
            </a>
            {% endif %}

            {% if role in ['admin','medecin'] %}
              <a href="{{ url_for('statistique.stats_home') }}" class="icon-card text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie mb-2"></i><span>Statistiques</span>
                </div>
              </a>
            {% elif role == 'assistante' %}
              <a class="icon-card disabled text-center">
                <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                  <i class="fas fa-chart-pie mb-2"></i><span>Statistiques</span>
                </div>
              </a>
            {% endif %}

            {% if role == 'admin' %}
            <a href="{{ url_for('administrateur_bp.dashboard') }}" class="icon-card text-center">
              <div class="border rounded h-100 p-3 d-flex flex-column justify-content-center align-items-center">
                <i class="fas fa-user-shield mb-2"></i><span>Admin</span>
              </div>
            </a>
            {% endif %}
          </div>
        </div>
      </div>
    </div>
  </div>

  <footer class="text-center py-3 small">
    <div class="card-footer text-center py-3">
      <div style="margin-bottom: 0 !important;">
        <p class="small mb-1" style="color: white;">
          <i class="fas fa-heartbeat me-1"></i>
          SASTOUKA DIGITAL © 2025 • sastoukadigital@gmail.com tel +212652084735
        </p>

        <p class="small mb-0" style="color: white;">
          Ouvrir l’application en réseau {{ host_address }}
        </p>
        <!-- Bouton de téléchargement du guide utilisateur -->
        <a href="{{ url_for('static', filename='Guide_Utilisateur_EasyMedicaLink.pdf') }}"
           class="btn btn-sm btn-outline-light mt-2" download>
          <i class="fas fa-download me-1"></i> Télécharger le Guide Utilisateur
        </a>
      </div>
  </footer>

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
