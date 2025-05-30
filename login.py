# login.py — rôle Admin visible partout, création/reset ouverts à tous
import os
import sys
import json
import hmac
import hashlib
import ctypes
import platform
import socket
import uuid
import pathlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Blueprint,
    request,
    render_template_string,
    redirect,
    url_for,
    flash,
    session,
    current_app
)

def generate_reset_token(length: int = 32) -> str:
    """
    Génère un token URL-safe pour la réinitialisation de mot de passe.
    """
    return secrets.token_urlsafe(length)

# ── Chemin caché du fichier utilisateurs ────────────────────────────────────
if getattr(sys, "frozen", False):
    base = Path(sys.executable).parent
else:
    base = Path(__file__).resolve().parent

hidden_dir = base / "MEDICALINK_FILES"
hidden_dir.mkdir(parents=True, exist_ok=True)
# Windows : attribuer l’attribut caché au dossier
if platform.system() == "Windows":
    ctypes.windll.kernel32.SetFileAttributesW(str(hidden_dir), 0x02)

USERS_FILE = hidden_dir / ".users.json"       # préfixe point → cache sous *nix
HMAC_KEY    = b"votre_cle_secrete_interne"    # modifiez par une vraie clé

# ── Calcul du HMAC d’un contenu bytes ───────────────────────────────────────
def _sign(data: bytes) -> str:
    return hmac.new(HMAC_KEY, data, hashlib.sha256).hexdigest()

# ── Lecture sécurisée ───────────────────────────────────────────────────────
def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    raw = USERS_FILE.read_bytes()
    try:
        payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
    except ValueError:
        sys.exit("users.json endommagé : signature manquante.")
    if not hmac.compare_digest(_sign(payload), sig.decode()):
        sys.exit("users.json corrompu : intégrité compromise.")
    return json.loads(payload.decode("utf-8"))

# ── Écriture sécurisée ──────────────────────────────────────────────────────
def save_users(users: dict):
    payload = json.dumps(users, ensure_ascii=False, indent=2).encode("utf-8")
    sig     = _sign(payload).encode()
    blob    = payload + b"\n---SIGNATURE---\n" + sig
    USERS_FILE.write_bytes(blob)

# ── Hachage de mot de passe ─────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """
    Renvoie le SHA256 du mot de passe.
    """
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# ── QR et utils localhost ────────────────────────────────────────────────────
def lan_ip() -> str:
    ip = socket.gethostbyname(socket.gethostname())
    if ip.startswith("127."):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            ip = "0.0.0.0"
    return ip

def is_localhost(req) -> bool:
    return req.remote_addr in ("127.0.0.1", "::1")

# ────────────────────────────────────────────────────────────────────────────
# Blueprint
# ────────────────────────────────────────────────────────────────────────────
login_bp = Blueprint("login", __name__)

# ───────── 3. templates
login_template = """
<!DOCTYPE html><html lang='fr'>
{{ pwa_head()|safe }}
<head>
  <meta charset='UTF-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>Connexion</title>
  <link href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css' rel='stylesheet'>
  <link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css' rel='stylesheet'>
  <style>
    @keyframes fadeInUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes gradientFlow {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }

    body {
      background: linear-gradient(135deg, #f0fafe 0%, #e3f2fd 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-direction: column; /* Added to stack card and signature */
    }

    .card {
      border-radius: 20px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.1);
      border: none;
      overflow: hidden;
      animation: fadeInUp 0.6s ease-out;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
    }

    .btn-gradient {
      background: linear-gradient(45deg, #1a73e8, #0d9488);
      background-size: 200% auto;
      color: white;
      border: none;
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }

    .btn-gradient:hover {
      background-position: right center;
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(26, 115, 232, 0.3);
    }

    .btn-gradient::after {
      content: '';
      position: absolute;
      top: 0;
      left: -200%;
      width: 200%;
      height: 100%;
      background: linear-gradient(
        to right,
        rgba(255,255,255,0) 0%,
        rgba(255,255,255,0.3) 50%,
        rgba(255,255,255,0) 100%
      );
      transform: skewX(-30deg);
      transition: left 0.6s;
    }

    .btn-gradient:hover::after {
      left: 200%;
    }

    .qr-container {
      transition: transform 0.3s ease;
    }

    .qr-container:hover {
      transform: scale(1.05);
    }

    .link-hover {
      transition: color 0.3s ease;
      position: relative;
    }

    .link-hover::after {
      content: '';
      position: absolute;
      bottom: -2px;
      left: 0;
      width: 0;
      height: 2px;
      background: #1a73e8;
      transition: width 0.3s ease;
    }

    .link-hover:hover::after {
      width: 100%;
    }

    .download-badge {
      position: relative;
      padding: 8px 15px;
      border-radius: 25px;
      font-size: 0.9rem;
      transition: all 0.3s ease;
    }
    /* New styles for contact info */
    .contact-info {
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #eee;
        text-align: center;
    }
    .contact-info a {
        margin: 0 10px;
    }
    .signature {
        margin-top: 20px;
        text-align: center;
        font-size: 0.8rem;
        color: #777;
    }
    .app-icon { /* Nouveau style pour l'icône */
        width: 100px; /* Ajustez la taille selon vos préférences */
        height: 100px; /* Gardez la même valeur que la largeur pour un cercle/carré */
        margin-bottom: 20px;
        border-radius: 20%; /* Peut être '50%' pour un cercle */
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
  </style>
</head>
<body class='p-3'>
  <div class='card p-4' style='max-width:420px'>
    <img src="{{ url_for('pwa_bp.pwa_icon', filename='icon-512.png') }}" alt="EasyMedicalink Icon" class="app-icon mx-auto d-block">

    <h3 class='text-center mb-4 fw-bold' style="color: #1a73e8;">
      <i class='fas fa-user-lock me-2'></i>Connexion
    </h3>

    {% if win64_filename or win32_filename %}
    <div class="alert alert-info small text-center mb-3" role="alert">
      <i class="fas fa-desktop me-2"></i>
      Pour une expérience optimale et un travail collaboratif en mode local avec vos équipes,
      en toute tranquillité, pensez à télécharger notre application pour Windows.
      <br>
      <small>Les liens de téléchargement (32 et 64 bits) se trouvent plus bas sur cette page.</small>
    </div>
    {% endif %}
    {% with m=get_flashed_messages(with_categories=true) %}
      {% for c,msg in m %}
      <div class='alert alert-{{c}} small animate__animated animate__fadeIn'>{{msg}}</div>
      {% endfor %}
    {% endwith %}

    <form method='POST' class='animate__animated animate__fadeIn animate__delay-1s'>
      <div class='mb-3'>
        <label class='form-label small text-muted'><i class='fas fa-users-cog me-1'></i>Rôle</label>
        <select name='role_select' class='form-select form-select-lg shadow-sm'>
          <option value='admin'>Admin</option>
          <option value='medecin'>Médecin</option>
          <option value='assistante'>Assistante</option>
        </select>
      </div>

      <div class='mb-3'>
        <label class='form-label small text-muted'><i class='fas fa-envelope me-1'></i>Email</label>
        <input name='email' type='email' class='form-control form-control-lg shadow-sm'>
      </div>

      <div class='mb-4'>
        <label class='form-label small text-muted'><i class='fas fa-key me-1'></i>Mot de passe</label>
        <input name='password' type='password' class='form-control form-control-lg shadow-sm'>
      </div>

      <button class='btn btn-gradient btn-lg w-100 py-3 fw-bold'>
        Se connecter
      </button>
    </form>

    <div class='d-flex gap-3 my-4 flex-column flex-md-row'>
      <div class='text-center flex-fill qr-container'>
        <canvas id='qrLocal' width='120' height='120'></canvas>
        <div class='small mt-2 text-muted'>Accès Web</div>
      </div>
      <div class='text-center flex-fill qr-container'>
        <canvas id='qrLan' width='120' height='120'></canvas>
        <div class='small mt-2 text-muted'>Réseau local</div>
      </div>
    </div>

    <div class='d-flex flex-column gap-2 mt-3'>
      <div class='d-flex flex-sm-row gap-2'>
        <a href='{{ url_for("login.register") }}'
           class='btn btn-gradient flex-fill py-2'>
          <i class='fas fa-user-plus me-1'></i>Créer un compte
        </a>
        <a href='{{ url_for("login.forgot_password") }}'
           class='btn btn-gradient flex-fill py-2'>
          <i class='fas fa-unlock-alt me-1'></i>Récupération
        </a>
      </div>

      {% if win64_filename or win32_filename %}
      <div class='text-center mt-3'>
        <div class='d-flex gap-2 justify-content-center'>
          {% if win64_filename %}
          <a href="{{ url_for('static', filename=win64_filename) }}"
             class='download-badge btn-gradient text-white text-decoration-none'>
             <i class='fas fa-download me-1'></i>Windows 64-bit
          </a>
          {% endif %}
          {% if win32_filename %}
          <a href="{{ url_for('static', filename=win32_filename) }}"
             class='download-badge btn-gradient text-white text-decoration-none'>
             <i class='fas fa-download me-1'></i>Windows 32-bit
          </a>
          {% endif %}
        </div>
      </div>
      {% endif %}
    </div>

    <div class='contact-info'>
        <p>N'hésitez pas à nous contacter par e-mail à sastoukadigital@gmail.com ou par téléphone au +212-652-084735. :</p>
        <a href='mailto:sastoukadigital@gmail.com' class='btn btn-outline-info'><i class='fas fa-envelope'></i> Email</a>
        <a href='https://wa.me/212652084735' class='btn btn-outline-success' target='_blank'><i class='fab fa-whatsapp'></i> WhatsApp</a>
    </div>

  </div>
  <div class="signature">
    Développé par SastoukaDigital
  </div>

  <script src='https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'></script>
  <script src='https://cdnjs.cloudflare.com/ajax/libs/qrious/4.0.2/qrious.min.js'></script>
  <script>
    // Animation au chargement
    document.addEventListener('DOMContentLoaded', () => {
      document.querySelectorAll('.animate__animated').forEach(el => {
        el.style.opacity = '0';
        setTimeout(() => el.style.opacity = '1', 100);
      });
    });

    // Génération des QR codes
    new QRious({
      element: document.getElementById('qrLocal'),
      value: 'https://easymedicalink-demo.onrender.com/',
      size: 120,
      foreground: '#1a73e8'
    });

    new QRious({
      element: document.getElementById('qrLan'),
      value: '{{ url_lan }}',
      size: 120,
      foreground: '#0d9488'
    });
  </script>
</body>
</html>
"""

register_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enregistrement</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body {
        background:#f0fafe;
        display: flex; /* Added for centering */
        flex-direction: column; /* Added for stacking */
        align-items: center; /* Added for centering */
        justify-content: center; /* Added for centering */
        min-height: 100vh; /* Added for full viewport height */
    }
    /* New styles for contact info */
    .contact-info {
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #eee;
        text-align: center;
    }
    .contact-info a {
        margin: 0 10px;
    }
    .signature {
        margin-top: 20px;
        text-align: center;
        font-size: 0.8rem;
        color: #777;
    }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 480px;">
    <h3 class="text-center mb-3"><i class="fas fa-user-plus"></i> Enregistrement</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form id="registerForm" method="POST">
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-envelope me-2"></i>Email</label>
        <input type="email" name="email" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-key me-2"></i>Mot de passe</label>
          <input type="password" name="password" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-key me-2"></i>Confirmer</label>
          <input type="password" name="confirm" class="form-control form-control-lg" required>
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-users-cog me-2"></i>Rôle</label>
        <select name="role" class="form-select form-select-lg" required>
          <option value="admin">Admin</option>
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-hospital-symbol me-2"></i>Nom Clinique/Cabinet</label>
        <input type="text" name="clinic" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-calendar-alt me-2"></i>Date de création</label>
          <input type="date" name="creation_date" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small"><i class="fas fa-map-marker-alt me-2"></i>Adresse</label>
          <input type="text" name="address" class="form-control form-control-lg" required>
        </div>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">S'enregistrer</button>
    </form>
    <div class="text-center mt-3">
      <a href="{{ url_for('login.login') }}" class="btn btn-outline-secondary d-inline-flex align-items-center">
        <i class="fas fa-arrow-left me-1"></i> Retour Connexion
      </a>
    </div>
    <div class='contact-info'>
        <p>Besoin d'aide ? Contactez-nous :</p>
        <a href='mailto:sastoukadigital@gmail.com' class='btn btn-outline-info'><i class='fas fa-envelope'></i> Email</a>
        <a href='https://wa.me/212652084735' class='btn btn-outline-success' target='_blank'><i class='fab fa-whatsapp'></i> WhatsApp</a>
    </div>
  </div>
  <div class="signature">
    Développé par SastoukaDigital
  </div>
  <script>
    document.getElementById('registerForm').addEventListener('submit', function(e) {
      e.preventDefault();
      Swal.fire({
        title: 'Important',
        text: 'Veuillez conserver précieusement votre email, le nom de la clinique, la date de création et l’adresse. Ces informations seront nécessaires pour récupérer votre mot de passe.',
        icon: 'info',
        confirmButtonText: 'OK'
      }).then((result) => {
        if (result.isConfirmed) {
          this.submit();
        }
      });
    });
  </script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

reset_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Réinitialiser mot de passe</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body {
        background:#f0fafe;
        display: flex; /* Added for centering */
        flex-direction: column; /* Added for stacking */
        align-items: center; /* Added for centering */
        justify-content: center; /* Added for centering */
        min-height: 100vh; /* Added for full viewport height */
    }
    /* New styles for contact info */
    .contact-info {
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #eee;
        text-align: center;
    }
    .contact-info a {
        margin: 0 10px;
    }
    .signature {
        margin-top: 20px;
        text-align: center;
        font-size: 0.8rem;
        color: #777;
    }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 400px;">
    <h3 class="text-center mb-3"><i class="fas fa-redo-alt"></i> Réinitialiser mot de passe</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form method="POST">
      <div class="mb-3 row g-2">
        <div class="col-12 col-md-6">
          <label class="form-label small">Nouveau mot de passe</label>
          <input type="password" name="password" class="form-control form-control-lg" required>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small">Confirmer</label>
          <input type="password" name="confirm" class="form-control form-control-lg" required>
        </div>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">Mettre à jour</button>
    </form>
    <div class='contact-info'>
        <p>Besoin d'aide ? Contactez-nous :</p>
        <a href='mailto:sastoukadigital@gmail.com' class='btn btn-outline-info'><i class='fas fa-envelope'></i> Email</a>
        <a href='https://wa.me/212652084735' class='btn btn-outline-success' target='_blank'><i class='fab fa-whatsapp'></i> WhatsApp</a>
    </div>
  </div>
  <div class="signature">
    Développé par SastoukaDigital
  </div>
</body>
</html>
'''

forgot_template = '''
<!DOCTYPE html>
<html lang="fr">
{{ pwa_head()|safe }}
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Récupération mot de passe</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    .btn-medical { background: linear-gradient(45deg,#1a73e8,#0d9488); color:white; }
    body {
        background:#f0fafe;
        display: flex; /* Added for centering */
        flex-direction: column; /* Added for stacking */
        align-items: center; /* Added for centering */
        justify-content: center; /* Added for centering */
        min-height: 100vh; /* Added for full viewport height */
    }
    /* New styles for contact info */
    .contact-info {
        margin-top: 20px;
        padding-top: 15px;
        border-top: 1px solid #eee;
        text-align: center;
    }
    .contact-info a {
        margin: 0 10px;
    }
    .signature {
        margin-top: 20px;
        text-align: center;
        font-size: 0.8rem;
        color: #777;
    }
  </style>
</head>
<body class="d-flex align-items-center justify-content-center min-vh-100 p-3">
  <div class="card p-4 shadow w-100" style="max-width: 400px;">
    <h3 class="text-center mb-3"><i class="fas fa-unlock-alt"></i>Récupération</h3>
    {% with msgs = get_flashed_messages(with_categories=true) %}
      {% for cat,msg in msgs %}<div class="alert alert-{{cat}} small">{{msg}}</div>{% endfor %}
    {% endwith %}
    <form method="POST">
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-envelope me-2"></i>Email</label>
        <input type="email" name="email" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-hospital me-2"></i>Nom Clinique</label>
        <input type="text" name="clinic" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-calendar-alt me-2"></i>Date de création</label>
        <input type="date" name="creation_date" class="form-control form-control-lg" required>
      </div>
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-map-marker-alt me-2"></i>Adresse</label>
        <input type="text" name="address" class="form-control form-control-lg" required>
      </div>
      <button type="submit" class="btn btn-medical btn-lg w-100">Valider</button>
    </form>
    <div class='contact-info'>
        <p>Besoin d'aide ? Contactez-nous :</p>
        <a href='mailto:sastoukadigital@gmail.com' class='btn btn-outline-info'><i class='fas fa-envelope'></i> Email</a>
        <a href='https://wa.me/212652084735' class='btn btn-outline-success' target='_blank'><i class='fab fa-whatsapp'></i> WhatsApp</a>
    </div>
  </div>
  <div class="signature">
    Développé par SastoukaDigital
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

# ───────── 4. Routes
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    local = is_localhost(request)

    # Nouveau code pour détection des exécutables
    static_folder = current_app.static_folder
    contents = os.listdir(static_folder) if os.path.exists(static_folder) else []
    win64_filename = next((f for f in contents if f.startswith('EasyMedicaLink-Win64.exe')), None)
    win32_filename = next((f for f in contents if f.startswith('EasyMedicaLink-Win32.exe')), None)

    if request.method == "POST":
        role  = request.form["role_select"]
        email = request.form["email"].lower().strip()
        pwd   = request.form["password"]

        users = load_users()
        u = users.get(email)
        if u and u["password"] == hash_password(pwd) and u.get("role", "admin") == role:
            session["email"]  = email
            session["role"]   = role
            session.permanent = True

            if role in ("medecin", "assistante"):
                return redirect(url_for("accueil.accueil"))
            return redirect(url_for("activation"))

        flash("Identifiants ou rôle invalides.", "danger")

    return render_template_string(
        login_template,
        url_lan = f"http://{lan_ip()}:3000",
        win64_filename=win64_filename,
        win32_filename=win32_filename
    )

@login_bp.route("/register", methods=["GET","POST"])
def register():
    f = request.form
    if request.method == "POST":
        users = load_users()
        email = f["email"].lower()
        if email in users:
            flash("Email déjà enregistré.","danger")
        elif f["password"] != f["confirm"]:
            flash("Les mots de passe ne correspondent pas.","danger")
        else:
            users[email] = {
                "password":      hash_password(f["password"]),
                "role":          f["role"],
                "clinic":        f["clinic"],
                "creation_date": f["creation_date"],
                "address":       f["address"]
            }
            save_users(users)
            flash("Compte créé.","success")
            return redirect(url_for("login.login"))
    return render_template_string(register_template)

@login_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    local = is_localhost(request)

    if request.method == 'POST':
        email         = request.form['email'].strip().lower()
        clinic        = request.form['clinic']
        creation_date = request.form['creation_date']
        address       = request.form['address']
        users         = load_users()
        user          = users.get(email)

        if (user
            and user.get('clinic') == clinic
            and user.get('creation_date') == creation_date
            and user.get('address') == address):
            token  = generate_reset_token()
            expiry = (datetime.now() + timedelta(hours=1)).isoformat()

            user['reset_token']  = token
            user['reset_expiry'] = expiry
            save_users(users)

            return redirect(url_for('login.reset_password', token=token))

        flash('Données non reconnues, veuillez réessayer.', 'danger')

    return render_template_string(
        forgot_template,
        local=local
    )

@login_bp.route('/change_password', methods=['GET', 'POST'])
def change_password():
    email = session.get('email')
    if not email:
        flash('Vous devez être connecté pour changer votre mot de passe.', 'warning')
        return redirect(url_for('login.login'))

    users = load_users()
    user  = users.get(email)

    if request.method == 'POST':
        pwd     = request.form['password']
        confirm = request.form['confirm']
        if pwd != confirm:
            flash('Les mots de passe ne correspondent pas', 'warning')
        else:
            user['password'] = hash_password(pwd)
            save_users(users)
            flash('Mot de passe mis à jour', 'success')
            return redirect(url_for('login.login'))

    return render_template_string(reset_template)

@login_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    users = load_users()
    for email, user in users.items():
        if user.get('reset_token') == token:
            expiry = datetime.fromisoformat(user.get('reset_expiry'))
            if datetime.now() > expiry:
                flash('Le lien a expiré', 'danger')
                return redirect(url_for('login.forgot_password'))
            if request.method == 'POST':
                pwd     = request.form['password']
                confirm = request.form['confirm']
                if pwd != confirm:
                    flash('Les mots de passe ne correspondent pas', 'warning')
                else:
                    user['password']     = hash_password(pwd)
                    user['reset_token']  = ''
                    user['reset_expiry'] = ''
                    save_users(users)
                    flash('Mot de passe mis à jour', 'success')
                    return redirect(url_for('login.login'))
            return render_template_string(reset_template)
    flash('Lien invalide', 'danger')
    return redirect(url_for('login.forgot_password'))

@login_bp.route('/logout')
def logout():
    session.pop('email', None)
    session.pop('role',  None)
    return redirect(url_for('login.login'))