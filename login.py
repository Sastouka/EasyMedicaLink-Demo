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
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Dict

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

import utils # Import utils for dynamic base directory management
from activation import TRIAL_DAYS # Import TRIAL_DAYS from activation module

def generate_reset_token(length: int = 32) -> str:
    """
    Génère un token URL-safe pour la réinitialisation de mot de passe.
    """
    return secrets.token_urlsafe(length)

# Global variables for dynamic paths
USERS_FILE: Optional[Path] = None
# This HMAC_KEY should be truly secret and ideally loaded from an environment variable
# or a more secure configuration management system in a production environment.
HMAC_KEY = b"votre_cle_secrete_interne" # modifiez par une vraie clé

def _set_login_paths(admin_email: str = None):
    """
    Sets the dynamic directory paths for login module based on admin_email.
    If admin_email is None, it attempts to use a default or assume anonymous.
    """
    global USERS_FILE

    # Ensure utils.set_dynamic_base_dir has been called
    # This function should be called first to ensure DYNAMIC_BASE_DIR is established.
    if admin_email:
        utils.set_dynamic_base_dir(admin_email)
    elif utils.DYNAMIC_BASE_DIR is None:
        # Fallback if admin_email not provided and DYNAMIC_BASE_DIR is not set
        # This might happen on initial load before any login.
        utils.set_dynamic_base_dir("default_admin@example.com") # Using a generic default

    # Now that DYNAMIC_BASE_DIR is guaranteed to be set
    hidden_dir = Path(utils.DYNAMIC_BASE_DIR)
    hidden_dir.mkdir(parents=True, exist_ok=True)

    # Windows : attribuer l’attribut caché au dossier
    if platform.system() == "Windows":
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(hidden_dir), 0x02)
        except Exception as e:
            print(f"WARNING: Could not set hidden attribute on {hidden_dir}: {e}")

    USERS_FILE = hidden_dir / ".users.json" # préfixe point → cache sous *nix
    print(f"DEBUG: Login USERS_FILE path set to: {USERS_FILE}")


# ── Calcul du HMAC d’un contenu bytes ───────────────────────────────────────
def _sign(data: bytes) -> str:
    return hmac.new(HMAC_KEY, data, hashlib.sha256).hexdigest()

# ── Lecture sécurisée ───────────────────────────────────────────────────────
def load_users() -> dict:
    # We call _set_login_paths() here without an argument to allow
    # it to use the session's admin_email (if set) or a default.
    # This is important for scenarios where admin_email is already
    # established (e.g., subsequent requests after initial login).
    _set_login_paths(session.get('admin_email'))

    if USERS_FILE is None:
        print("ERROR: USERS_FILE is not set. Cannot load users.")
        return {}

    if not USERS_FILE.exists():
        return {}
    raw = USERS_FILE.read_bytes()
    try:
        payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
    except ValueError:
        # sys.exit("users.json endommagé : signature manquante.")
        print("ERROR: users.json endommagé : signature manquante.")
        return {} # Return empty dict instead of exiting
    if not hmac.compare_digest(_sign(payload), sig.decode()):
        # sys.exit("users.json corrompu : intégrité compromise.")
        print("ERROR: users.json corrompu : intégrité compromise.")
        return {} # Return empty dict instead of exiting
    return json.loads(payload.decode("utf-8"))

# ── Écriture sécurisée ──────────────────────────────────────────────────────
def save_users(users: dict):
    # Ensure paths are set before saving users.
    # This ensures we save to the currently active admin's folder.
    _set_login_paths(session.get('admin_email'))

    if USERS_FILE is None:
        print("ERROR: USERS_FILE is not set. Cannot save users.")
        return
            
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

# Ajout d'une nouvelle fonction helper pour chercher l'utilisateur dans tous les dossiers d'administrateurs
def _find_user_in_all_admin_folders(target_email: str, target_password_hash: str, target_role: str) -> Optional[Dict]:
    """
    Cherche un utilisateur dans tous les fichiers .users.json de tous les administrateurs
    pour trouver l'email de l'administrateur propriétaire.
    """
    medicalink_data_base = Path(utils.application_path) / "MEDICALINK_DATA"
    if not medicalink_data_base.exists():
        print("DEBUG: MEDICALINK_DATA folder not found.")
        return None

    # Iterate over all admin sub-folders within MEDICALINK_DATA
    for admin_folder_name in os.listdir(medicalink_data_base):
        admin_folder_path = medicalink_data_base / admin_folder_name
        if admin_folder_path.is_dir():
            temp_users_file = admin_folder_path / ".users.json"
            if temp_users_file.exists():
                try:
                    raw = temp_users_file.read_bytes()
                    payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
                    if hmac.compare_digest(_sign(payload), sig.decode()):
                        users_data_from_this_admin = json.loads(payload.decode("utf-8"))
                        
                        user_found = users_data_from_this_admin.get(target_email)
                        if user_found and \
                           user_found.get("password") == target_password_hash and \
                           user_found.get("role", "admin") == target_role:
                            # User found, now identify the owner.
                            # For admins, owner is themselves. For others, it's explicitly set.
                            owner_email = user_found.get("owner", target_email) # owner will be current_admin_email when admin created the user
                            return {
                                "user_data": user_found,
                                "admin_owner_email": owner_email # This is the email to use for session['admin_email']
                            }
                except (ValueError, json.JSONDecodeError, FileNotFoundError) as e:
                    print(f"WARNING: Error reading or verifying {temp_users_file}: {e}")
    return None

# NEW: Function to check if an email is globally unique across all admin folders
def _is_email_globally_unique(email_to_check: str) -> bool:
    """
    Checks if an email exists in any admin's users.json file.
    Returns True if unique (not found), False if already exists.
    """
    medicalink_data_base = Path(utils.application_path) / "MEDICALINK_DATA"
    if not medicalink_data_base.exists():
        # If no data folders exist, email is unique
        return True

    for admin_folder_name in os.listdir(medicalink_data_base):
        admin_folder_path = medicalink_data_base / admin_folder_name
        if admin_folder_path.is_dir():
            temp_users_file = admin_folder_path / ".users.json"
            if temp_users_file.exists():
                try:
                    raw = temp_users_file.read_bytes()
                    payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
                    if hmac.compare_digest(_sign(payload), sig.decode()):
                        users_data_from_this_admin = json.loads(payload.decode("utf-8"))
                        if email_to_check in users_data_from_this_admin:
                            return False # Email found, not unique
                except (ValueError, json.JSONDecodeError, FileNotFoundError) as e:
                    print(f"WARNING: Error reading or verifying {temp_users_file} during global uniqueness check: {e}")
    return True # Email not found in any admin folder, so it's unique

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
      <!-- Bouton de téléchargement du guide utilisateur pour la page de connexion -->
      <div class='text-center mt-3'>
        <a href="{{ url_for('static', filename='Guide_Utilisateur_EasyMedicaLink.pdf') }}"
           class='btn btn-outline-info' download>
          <i class='fas fa-file-alt me-1'></i> Télécharger le Guide Utilisateur
        </a>
      </div>
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
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-phone me-2"></i>Téléphone</label>
        <input type="tel" name="phone" class="form-control form-control-lg" placeholder="+212XXXXXXXXX" required pattern="^\\+\\d{9,}$">
        <div class="form-text text-muted">Le numéro de téléphone doit commencer par un '+' et contenir au moins 9 chiffres.</div>
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
      <div class="mb-3">
        <label class="form-label small"><i class="fas fa-phone me-2"></i>Téléphone</label>
        <input type="tel" name="phone" class="form-control form-control-lg" placeholder="+212XXXXXXXXX" required pattern="^\\+\\d{9,}$">
        <div class="form-text text-muted">Le numéro de téléphone doit commencer par un '+' et contenir au moins 9 chiffres.</div>
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
</body>
</html>
'''

# ───────── 4. Routes
@login_bp.route("/login", methods=["GET", "POST"])
def login():
    # On login page, admin_email might not be in session yet.
    # We will pass the email entered in the form for path initialization AFTER successful login.
    # For initial load, we assume a default or anonymous state, which _set_login_paths handles.
    # We call _set_login_paths without an argument first, so it defaults to the session's
    # admin_email (if present from a previous admin login) or 'default_admin@example.com'.
    _set_login_paths(session.get('admin_email'))

    local = is_localhost(request)

    # Nouveau code pour détection des exécutables
    static_folder = current_app.static_folder
    contents = os.listdir(static_folder) if os.path.exists(static_folder) else []
    win64_filename = next((f for f in contents if f.startswith('EasyMedicaLink-Win64.exe')), None)
    win32_filename = next((f for f in contents if f.startswith('EasyMedicaLink-Win32.exe')), None)

    if request.method == "POST":
        role_selected = request.form["role_select"] # Renommé pour éviter conflit avec 'role' de l'utilisateur réel
        email = request.form["email"].lower().strip()
        pwd = request.form["password"]
        pwd_hash = hash_password(pwd) # Hash the password for lookup

        # --- Global user search ---
        # This function will search in all admin folders for the user
        found_user_info = _find_user_in_all_admin_folders(email, pwd_hash, role_selected)

        if found_user_info:
            # user_data = found_user_info["user_data"] # Not directly used after this point, but kept for clarity
            admin_owner_email = found_user_info["admin_owner_email"]

            # Authentication successful. Set session variables.
            session["email"] = email
            session["role"] = role_selected
            session["admin_email"] = admin_owner_email # CRUCIAL: Set admin_email to the owner!
            session.permanent = True

            # Now that session['admin_email'] is set, re-initialize paths correctly
            # This ensures subsequent operations (e.g., loading config, patient data)
            # go to the correct admin's folder.
            _set_login_paths(session['admin_email'])

            if role_selected in ("medecin", "assistante"):
                return redirect(url_for("accueil.accueil"))
            return redirect(url_for("activation.activation")) # Corrected redirect for activation.
        
        flash("Identifiants ou rôle invalides.", "danger")

    return render_template_string(
        login_template,
        url_lan = f"http://{lan_ip()}:3000",
        win64_filename=win64_filename,
        win32_filename=win32_filename
    )

@login_bp.route("/register", methods=["GET","POST"])
def register():
    # Registration is primarily for admin accounts, so set paths based on the registering email.
    # This assumes that the *first* admin registers and creates their base folder.
    # For subsequent registrations of non-admin users, they are created by an admin
    # via the admin dashboard, where their 'owner' field is set.
    if request.method == "POST":
        email_to_register = request.form["email"].lower().strip()
        _set_login_paths(email_to_register) # Set paths for the registering email's potential new folder

        f = request.form
        users = load_users() # Load users from the context of `email_to_register`
        email = f["email"].lower()
        phone = f["phone"].strip() # Récupérer le numéro de téléphone

        if email in users:
            flash("Email déjà enregistré.","danger")
        elif f["password"] != f["confirm"]:
            flash("Les mots de passe ne correspondent pas.","danger")
        elif not phone.startswith('+') or len(phone) < 10: # Validation du numéro de téléphone
            flash("Le numéro de téléphone doit commencer par '+' et contenir au moins 9 chiffres.","danger")
        else:
            users[email] = {
                "password":      hash_password(f["password"]),
                "role":          f["role"], # This will always be 'admin' from the current form
                "clinic":        f["clinic"],
                "creation_date": f["creation_date"],
                "address":       f["address"],
                "phone":         phone, # Sauvegarder le numéro de téléphone
                "active":        True, # New accounts are active by default
                "owner":         email, # For an admin, they own themselves
                # Initialiser l'activation pour une période d'essai de 7 jours
                "activation": {
                    "plan": f"essai_{TRIAL_DAYS}jours", # Plan d'essai
                    "activation_date": date.today().isoformat(), # Date d'aujourd'hui
                    "activation_code": "0000-0000-0000-0000" # Clé d'essai spécifique
                }
            }
            save_users(users)
            flash("Compte créé.","success")
            return redirect(url_for("login.login"))
    else:
        # For GET request, set paths to a default if no admin is logged in
        _set_login_paths()

    return render_template_string(register_template)

@login_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    # Do not call _set_login_paths() here initially.
    local = is_localhost(request)

    if request.method == 'POST':
        email_form = request.form['email'].strip().lower()
        clinic_form = request.form['clinic']
        creation_date_form = request.form['creation_date']
        address_form = request.form['address']
        phone_form = request.form['phone'].strip()

        # We need to find the user in *any* admin's users.json based on provided recovery details.
        medicalink_data_base = Path(utils.application_path) / "MEDICALINK_DATA"
        user_found_globally = None
        admin_owner_email_found = None

        if medicalink_data_base.exists():
            for admin_folder_name in os.listdir(medicalink_data_base):
                admin_folder_path = medicalink_data_base / admin_folder_name
                if admin_folder_path.is_dir():
                    temp_users_file = admin_folder_path / ".users.json"
                    if temp_users_file.exists():
                        try:
                            raw = temp_users_file.read_bytes()
                            payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
                            if hmac.compare_digest(_sign(payload), sig.decode()):
                                users_data_from_this_admin = json.loads(payload.decode("utf-8"))
                                user_candidate = users_data_from_this_admin.get(email_form)
                                
                                if (user_candidate
                                    and user_candidate.get('clinic') == clinic_form
                                    and user_candidate.get('creation_date') == creation_date_form
                                    and user_candidate.get('address') == address_form
                                    and user_candidate.get('phone') == phone_form):
                                    user_found_globally = user_candidate
                                    admin_owner_email_found = user_candidate.get("owner", email_form) # Admins own themselves
                                    # Temporarily set session['email'] for this user, needed by load_users/save_users in next step
                                    session['email'] = email_form
                                    break # User found, stop searching
                        except (ValueError, json.JSONDecodeError, FileNotFoundError) as e:
                            print(f"WARNING: Error reading or verifying {temp_users_file} during forgot_password search: {e}")

        if user_found_globally and admin_owner_email_found:
            # User found and validated. Now set paths to the correct admin's folder
            _set_login_paths(admin_owner_email_found)
            # Reload users from the correct path (this will use the admin_owner_email_found path)
            users = load_users() # This will load users from the admin_owner_email_found's folder
            user = users.get(email_form) # Get the user object again from the correct reloaded users dict
            
            if user: # Double-check user exists in the reloaded dict
                token  = generate_reset_token()
                expiry = (datetime.now() + timedelta(hours=1)).isoformat()

                user['reset_token']  = token
                user['reset_expiry'] = expiry
                save_users(users) # Save to the correct admin's users.json

                flash('Un lien de réinitialisation a été envoyé à votre email.', 'info') # Inform the user
                return redirect(url_for('login.reset_password', token=token))

        flash('Données non reconnues, veuillez réessayer.', 'danger')
    else:
        # For GET request, set paths to a default if no admin is logged in
        _set_login_paths()

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

    # Ensure paths are set based on the logged-in user's admin_email
    _set_login_paths(session.get('admin_email'))

    users = load_users() # This will load from the correct admin's folder
    user  = users.get(email)

    if request.method == 'POST':
        pwd     = request.form['password']
        confirm = request.form['confirm']
        if pwd != confirm:
            flash('Les mots de passe ne correspondent pas', 'warning')
        else:
            user['password'] = hash_password(pwd)
            save_users(users) # Save to the correct admin's users.json
            flash('Mot de passe mis à jour', 'success')
            return redirect(url_for('login.login'))

    return render_template_string(reset_template)

@login_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # We need to find the user associated with this token.
    # This requires searching through all possible admin users.json files.
    user_to_reset_data = None
    admin_owner_email_for_reset = None
    user_email_for_reset = None

    medicalink_data_base = Path(utils.application_path) / "MEDICALINK_DATA"
    if medicalink_data_base.exists():
        for admin_folder_name in os.listdir(medicalink_data_base):
            admin_folder_path = medicalink_data_base / admin_folder_name
            if admin_folder_path.is_dir():
                temp_users_file = admin_folder_path / ".users.json"
                if temp_users_file.exists():
                    try:
                        raw = temp_users_file.read_bytes()
                        payload, sig = raw.rsplit(b"\n---SIGNATURE---\n", 1)
                        if hmac.compare_digest(_sign(payload), sig.decode()):
                            users_data_from_this_admin = json.loads(payload.decode("utf-8"))
                            for email_candidate, user_candidate in users_data_from_this_admin.items():
                                if user_candidate.get('reset_token') == token:
                                    user_to_reset_data = user_candidate
                                    user_email_for_reset = email_candidate # Store the actual user email
                                    admin_owner_email_for_reset = user_candidate.get("owner", email_candidate) # Admins own themselves
                                    break # Token and user found, stop searching
                            if user_to_reset_data:
                                break # Token found, stop searching admin folders
                    except (ValueError, json.JSONDecodeError, FileNotFoundError) as e:
                        print(f"WARNING: Error reading or verifying {temp_users_file} during reset_password search: {e}")

    if user_to_reset_data and admin_owner_email_for_reset and user_email_for_reset:
        # Token found, set paths to the correct admin's folder
        _set_login_paths(admin_owner_email_for_reset)
        # Reload users from the correct path
        users = load_users() # This loads from the admin_owner_email_for_reset's folder
        user = users.get(user_email_for_reset) # Get the updated user object from the reloaded dict

        if user is None: # Should not happen if token was just found, but safety check
            flash('Lien invalide ou utilisateur introuvable après rechargement.', 'danger')
            return redirect(url_for('login.forgot_password'))

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
                save_users(users) # Save to the correct admin's users.json
                flash('Mot de passe mis à jour', 'success')
                return redirect(url_for('login.login'))
        return render_template_string(reset_template)
    flash('Lien invalide', 'danger')
    return redirect(url_for('login.forgot_password'))

@login_bp.route('/logout')
def logout():
    session.pop('email', None)
    session.pop('role',  None)
    session.pop('admin_email', None) # Clear admin_email on logout
    return redirect(url_for('login.login'))